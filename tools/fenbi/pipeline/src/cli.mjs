#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { EXIT } from './constants.mjs';
import { loadPipelineConfig } from './config.mjs';
import { openQueue } from './queue.mjs';
import { buildHandoff, copyHandoffArtifacts, readHandoff, writeHandoff } from './handoff.mjs';
import { jobIdFor } from './identity.mjs';
import { evaluateBackpressure, hostPressure, summarizeHostPressure } from './backpressure.mjs';
import { loadThrottle, resetThrottle, saveThrottle, throttleSnapshot } from './throttle.mjs';
import { loadAdapter, runAwaitedManifest, runCollector, runWorkerDrain } from './collector.mjs';
import { importObservations, importObservationDirectory, loadAllowlist } from './observation.mjs';

const HELP = `gwy-zhenti offline pipeline (bounded queue, no daemon)
  node tools/fenbi/pipeline/src/cli.mjs init [--data-dir DIR]
  node tools/fenbi/pipeline/src/cli.mjs enqueue --source-id ID --version V --title T
      --subject xingce|shenlun --area A --year 2026 --url URL --observed
      --source-category observed_ui|official|licensed_donor [--license TEXT]
      [--redistribution local_only|allowed] --evidence observed_ui:NOTE
      [--image material/q1.png:https://img.fbstatic.cn/...] [--questions N] [--materials N]
      [--variant V] [--actor NAME]
  node tools/fenbi/pipeline/src/cli.mjs enqueue-offline --handoff FILE [--artifact-root DIR]
  node tools/fenbi/pipeline/src/cli.mjs observe-import --handoff FILE [--allowlist FILE] [--dry-run]
  node tools/fenbi/pipeline/src/cli.mjs observe-import --handoff-dir DIR [--max-files 5]
      [--allowlist FILE] [--dry-run]
  node tools/fenbi/pipeline/src/cli.mjs allowlist show [--allowlist FILE]
  node tools/fenbi/pipeline/src/cli.mjs drain --role collector|normalizer|matcher|assets_qa|answer_qa|reviewer|verifier
      [--stage STAGE] [--budget N] [--owner NAME] [--adapter-module FILE]
  node tools/fenbi/pipeline/src/cli.mjs claim --role ROLE --stage STAGE --owner NAME [--job ID]
  node tools/fenbi/pipeline/src/cli.mjs put-artifact --job ID --stage STAGE --owner NAME
      --token TOKEN --generation N --file PATH --name REL [--kind KIND]
  node tools/fenbi/pipeline/src/cli.mjs complete --job ID --stage STAGE --owner NAME --token TOKEN
      --generation N --artifact REL [--artifact REL ...] [--declarations JSON]
      (use --artifact images.json#image_manifest to declare an asset manifest)
      [--answer-provenance official|source_observed|human_authored]
      [--approved --reviewer NAME] [--citations-verified]
  node tools/fenbi/pipeline/src/cli.mjs fail --job ID --stage STAGE --owner NAME --token TOKEN
      --generation N --outcome partial|skipped_placeholder|blocked_auth|blocked_rights|needs_review|dead_letter --reason TEXT
  node tools/fenbi/pipeline/src/cli.mjs reopen --job ID --stage STAGE --actor NAME --reason TEXT
  node tools/fenbi/pipeline/src/cli.mjs verify --job ID --actor NAME --receipt REL [--sha256 HASH]
  node tools/fenbi/pipeline/src/cli.mjs build-handoff --job ID --stage STAGE [--producer NAME] [--out FILE]
  node tools/fenbi/pipeline/src/cli.mjs verify-handoff FILE [--artifact-root DIR]
  node tools/fenbi/pipeline/src/cli.mjs reconcile
  node tools/fenbi/pipeline/src/cli.mjs status
  node tools/fenbi/pipeline/src/cli.mjs throttle show|reset [--host HOST]
Options: --config FILE, --data-dir DIR, --json (default output is JSON), --help
A drain is a single bounded pass. It exits 0 on queue_empty/drained, 2 on blocked/unwired,
3 on rate-limit backoff and 4 on backpressure. Nothing here starts a daemon or a browser.
`;

function parse() {
  return parseArgs({
    allowPositionals: true,
    options: {
      ...Object.fromEntries([
        'config', 'data-dir', 'source-id', 'version', 'title', 'subject', 'area', 'year', 'url',
        'source-category', 'license', 'redistribution', 'questions', 'materials', 'variant', 'actor',
        'handoff', 'artifact-root', 'role', 'stage', 'budget', 'owner', 'adapter-module', 'job',
        'token', 'generation', 'file', 'name', 'kind', 'declarations', 'answer-provenance',
        'reviewer', 'outcome', 'reason', 'receipt', 'sha256', 'producer', 'out', 'host', 'allowlist',
        'handoff-dir', 'max-files',
      ].map((name) => [name, { type: 'string' }])),
      ...Object.fromEntries(['observed', 'approved', 'citations-verified', 'json', 'help', 'dry-run', 'images-verified'].map((name) => [name, { type: 'boolean', default: false }])),
      evidence: { type: 'string', multiple: true, default: [] },
      artifact: { type: 'string', multiple: true, default: [] },
      image: { type: 'string', multiple: true, default: [] },
    },
  });
}

function requireValue(values, key, label = key) {
  const value = values[key];
  if (typeof value !== 'string' || !value.trim()) throw Object.assign(new Error(`--${label} is required`), { code: 'INVALID_INPUT' });
  return value;
}

function parseEvidence(items) {
  return items.map((item) => {
    const index = item.indexOf(':');
    if (index < 1) return { type: 'operator_note', ref: item };
    return { type: item.slice(0, index), ref: item.slice(index + 1) };
  });
}

function parseImages(items) {
  return items.map((item) => {
    const index = item.indexOf(':');
    if (index < 1) return { ref: item };
    return { ref: item.slice(0, index), sourceUrl: item.slice(index + 1) };
  });
}

function parseDeclarations(values) {
  let declarations = {};
  if (values.declarations) {
    declarations = JSON.parse(values.declarations);
    if (!declarations || typeof declarations !== 'object' || Array.isArray(declarations)) throw Object.assign(new Error('--declarations must be a JSON object'), { code: 'INVALID_INPUT' });
  }
  if (values['answer-provenance']) declarations.answerProvenance = values['answer-provenance'];
  if (values.approved) declarations.approved = true;
  if (values.reviewer) declarations.reviewer = values.reviewer;
  if (values['citations-verified']) declarations.citationsVerified = true;
  if (values['images-verified']) declarations.imagesVerified = true;
  return declarations;
}

function ok(payload, exit = EXIT.OK) { return { exit, payload: { ok: true, ...payload } }; }
function fail(code, message, exit = EXIT.INVALID) { return { exit, payload: { ok: false, error: { code, message } } }; }

async function loadQueue(configFile, dataDir) {
  let config = await loadPipelineConfig(configFile);
  if (dataDir) config = Object.freeze({ ...config, dataDir: path.resolve(dataDir) });
  return { config, queue: openQueue(config) };
}

async function readStateJson(config, name) {
  try { return JSON.parse(await fs.readFile(path.join(config.dataDir, 'state', name), 'utf8')); }
  catch { return null; }
}

async function baseStatus(queue, config) {
  const status = await queue.status();
  const pressure = hostPressure();
  const backpressure = evaluateBackpressure({ status, config });
  const catalog = await readStateJson(config, 'observed-catalog.json');
  const byClassification = {};
  for (const entry of Object.values(catalog?.entries ?? {})) {
    byClassification[entry.classification] = (byClassification[entry.classification] ?? 0) + 1;
  }
  const collectorState = await readStateJson(config, 'collector-status.json');
  return {
    status,
    collector: {
      adapterWired: collectorState?.adapterWired ?? false,
      lastRunAt: collectorState?.lastRunAt ?? null,
      lastReason: collectorState?.reason ?? null,
      note: collectorState?.adapterWired === true
        ? 'A collector adapter was recorded by the last bounded drain.'
        : 'No collector adapter is wired; drain --role collector exits 2 collector_unwired unless --adapter-module is supplied.',
    },
    observedCatalog: {
      entries: Object.keys(catalog?.entries ?? {}).length,
      byClassification,
      updatedAt: catalog?.updatedAt ?? null,
    },
    host: summarizeHostPressure(pressure),
    backpressure,
    capacity: {
      collector: backpressure.allow.collector ? (pressure.degraded ? 1 : config.maxConcurrency) : 0,
      offlineWorkers: backpressure.allow.normalizer ? (pressure.degraded ? 4 : 8) : 0,
    },
  };
}

async function main() {
  const { values, positionals } = parse();
  if (values.help || !positionals.length) return ok({ help: HELP });
  const command = positionals[0];
  const { config, queue } = await loadQueue(values.config, values['data-dir']);

  if (command === 'init') {
    const root = await queue.init();
    return ok({ dataDir: root, message: 'directories created with mode 0700' });
  }

  if (command === 'enqueue') {
    const result = await queue.enqueue({
      paperSourceId: requireValue(values, 'source-id', 'source-id'),
      version: requireValue(values, 'version'),
      title: requireValue(values, 'title'),
      subject: requireValue(values, 'subject'),
      area: requireValue(values, 'area'),
      year: Number(requireValue(values, 'year')),
      variant: values.variant,
      url: values.url,
      urlObserved: values.observed,
      sourceCategory: values['source-category'] ?? 'observed_ui',
      license: values.license,
      redistribution: values.redistribution ?? 'local_only',
      evidence: parseEvidence(values.evidence),
      images: parseImages(values.image),
      expectedQuestions: values.questions === undefined ? null : Number(values.questions),
      expectedMaterials: values.materials === undefined ? null : Number(values.materials),
      actor: values.actor ?? 'cli',
    });
    return ok({
      jobId: result.jobId, created: result.created, duplicate: result.duplicate,
      status: result.job.status, allowCapture: result.job.allowCapture,
      taskKeys: result.job.taskKeys,
    });
  }

  if (command === 'enqueue-offline') {
    const filename = requireValue(values, 'handoff', 'handoff');
    const root = values['artifact-root'] ? path.resolve(values['artifact-root']) : path.dirname(path.resolve(filename));
    const { handoff } = await readHandoff(filename, { root, config });
    if (handoff.stage !== 'capture_ready') throw Object.assign(new Error('Offline import currently accepts a capture_ready handoff'), { code: 'INVALID_STAGE' });
    const input = {
      paperSourceId: handoff.paperSourceId, version: handoff.version, title: handoff.title,
      subject: handoff.subject, area: handoff.area, year: handoff.year, variant: handoff.variant,
      url: handoff.observed?.url ?? undefined, urlObserved: Boolean(handoff.observed?.urlObserved),
      sourceCategory: handoff.source?.category, license: handoff.source?.license,
      redistribution: handoff.source?.redistribution ?? 'local_only',
      evidence: handoff.source?.evidence ?? [], offline: true, actor: values.actor ?? 'cli',
      images: (handoff.images ?? []).map((image) => ({ ref: image.ref, sourceUrl: image.sourceUrl ?? undefined, sha256: image.sha256 ?? undefined })),
    };
    const jobId = jobIdFor(input);
    if (handoff.jobId !== jobId) throw Object.assign(new Error('Handoff jobId does not match its source identity'), { code: 'HANDOFF_JOB_MISMATCH' });
    const existing = await queue.getJob(jobId);
    if (existing) return ok({ jobId, created: false, duplicate: true, status: existing.status });
    const destination = queue.paths.artifactDir(jobId, 'capture_ready');
    const artifacts = await copyHandoffArtifacts(handoff, root, destination, { config });
    const result = await queue.enqueueOffline(input, artifacts);
    return ok({ jobId: result.jobId, created: result.created, duplicate: result.duplicate, status: result.job.status });
  }

  if (command === 'observe-import') {
    const handoffFile = values.handoff ?? positionals[1];
    const handoffDir = values['handoff-dir'];
    if (handoffFile && handoffDir) return fail('INVALID_INPUT', 'Use either --handoff or --handoff-dir, not both');
    if (!handoffFile && !handoffDir) return fail('INVALID_INPUT', 'Provide --handoff FILE or --handoff-dir DIR');
    const allowlistFile = values.allowlist ?? path.join(config.dataDir, 'allowlist.json');
    const allowlist = await loadAllowlist(allowlistFile);
    const dryRun = Boolean(values['dry-run']);
    if (handoffDir) {
      const maxFiles = values['max-files'] === undefined ? 5 : Number(values['max-files']);
      const report = await importObservationDirectory({
        queue, config, directory: path.resolve(handoffDir), allowlist, maxFiles, dryRun,
      });
      return ok({ ...report, mode: 'directory', allowlistFile });
    }
    const handoff = JSON.parse(await fs.readFile(path.resolve(handoffFile), 'utf8'));
    const report = await importObservations({ queue, config, handoff, allowlist, dryRun });
    return ok({ ...report, mode: 'file', allowlistFile });
  }

  if (command === 'allowlist') {
    const action = positionals[1] ?? 'show';
    if (action !== 'show') return fail('INVALID_ALLOWLIST_ACTION', 'Use allowlist show');
    const allowlistFile = values.allowlist ?? path.join(config.dataDir, 'allowlist.json');
    const allowlist = await loadAllowlist(allowlistFile);
    return ok({
      allowlist: allowlistFile, missing: allowlist.missing, count: allowlist.ids.size,
      entries: allowlist.list.map((entry) => ({ id: entry.id, title: entry.title ?? null, note: entry.note ?? null })),
      note: 'Authorization only. The allowlist never contains URLs; URLs come from the browser owner handoff.',
    });
  }

  if (command === 'drain') {
    const role = requireValue(values, 'role');
    const budget = values.budget === undefined ? 1 : Number(values.budget);
    if (!Number.isInteger(budget) || budget < 0 || budget > 1000) return fail('INVALID_BUDGET', '--budget must be 0..1000');
    if (role === 'reviewer' || role === 'verifier') {
      const stage = role === 'reviewer' ? 'human_review' : 'candidate_ready';
      const status = await queue.status();
      const backpressure = evaluateBackpressure({ status, config });
      if (backpressure.level === 'pause_all') {
        return { exit: EXIT.BACKPRESSURE, payload: { ok: true, role, stage, reason: 'backpressure', backpressure } };
      }
      const manifest = await runAwaitedManifest({ queue, stage });
      await fs.mkdir(queue.paths.review, { recursive: true, mode: 0o700 });
      const manifestFile = path.join(queue.paths.review, `${stage}.json`);
      await fs.writeFile(manifestFile, JSON.stringify(manifest, null, 2) + '\n', { mode: 0o600 });
      return ok({ role, stage, manifest: manifestFile, count: manifest.count, exitReason: manifest.count ? 'awaiting_human' : 'queue_empty', exit: EXIT.OK });
    }
    const stage = values.stage ?? { collector: 'capture_ready', normalizer: 'normalized', matcher: 'aligned', assets_qa: 'assets_qa', answer_qa: 'answer_explanation_qa' }[role];
    if (!stage) return fail('INVALID_ROLE', `Unknown role: ${role}`);
    const adapter = values['adapter-module'] ? await loadAdapter(values['adapter-module']) : null;
    const owner = values.owner ?? `${role}-${process.pid}`;
    const status = await queue.status();
    const pressure = hostPressure();
    const backpressure = evaluateBackpressure({ status, config });
    if (role === 'collector') {
      const result = await runCollector({ queue, config, adapter, owner, budget, pressure, backpressure });
      return { exit: result.exit ?? EXIT.OK, payload: { ok: true, role, ...result, queue: result.reason === 'backpressure' ? undefined : { queueLength: status.queueLength, pendingReview: status.pendingReview } } };
    }
    if (!backpressure.allow[role]) return { exit: EXIT.BACKPRESSURE, payload: { ok: true, role, stage, reason: 'backpressure', backpressure } };
    const result = await runWorkerDrain({ queue, config, role, stage, adapter, owner, budget });
    return { exit: result.exit ?? EXIT.OK, payload: { ok: true, role, stage, ...result } };
  }

  if (command === 'claim') {
    const stage = requireValue(values, 'stage');
    const role = requireValue(values, 'role');
    const claim = await queue.claimStage(stage, { role, owner: requireValue(values, 'owner'), jobId: values.job ?? null });
    if (!claim) return ok({ claimed: false, reason: 'no_eligible_job' });
    return ok({
      claimed: true, jobId: claim.job.jobId, stage, owner: claim.lease.owner,
      lease: { token: claim.lease.token, generation: claim.lease.generation, expiresAt: claim.lease.expiresAt },
      job: {
        jobId: claim.job.jobId, title: claim.job.title, paperSourceId: claim.job.paperSourceId,
        version: claim.job.version, subject: claim.job.subject, area: claim.job.area,
        year: claim.job.year, url: claim.job.url, source: claim.job.source,
        permissions: claim.job.permissions, previousArtifacts: stage === 'normalized' ? claim.job.stages.capture_ready.artifacts : undefined,
      },
    });
  }

  if (command === 'put-artifact') {
    const manifest = await queue.putArtifact({
      jobId: requireValue(values, 'job'), stage: requireValue(values, 'stage'),
      owner: requireValue(values, 'owner'), token: requireValue(values, 'token'),
      generation: Number(requireValue(values, 'generation')),
      source: path.resolve(requireValue(values, 'file')), name: requireValue(values, 'name'),
      kind: values.kind ?? 'data',
    });
    return ok({ jobId: values.job, stage: values.stage, artifact: manifest });
  }

  if (command === 'complete') {
    const artifacts = values.artifact.map((item) => {
      const separator = item.lastIndexOf('#');
      if (separator > 0 && /^[a-z][a-z0-9_]*$/.test(item.slice(separator + 1))) {
        return { path: item.slice(0, separator), kind: item.slice(separator + 1) };
      }
      return { path: item, kind: 'data' };
    });
    if (!artifacts.length) return fail('ARTIFACT_REQUIRED', 'Provide at least one --artifact');
    const job = await queue.completeStage({
      jobId: requireValue(values, 'job'), stage: requireValue(values, 'stage'),
      owner: requireValue(values, 'owner'), token: requireValue(values, 'token'),
      generation: Number(requireValue(values, 'generation')),
      artifacts, declarations: parseDeclarations(values),
    });
    return ok({ jobId: job.jobId, stage: values.stage, status: job.status, nextStage: job.status === 'candidate_ready' ? null : undefined });
  }

  if (command === 'fail') {
    const job = await queue.failStage({
      jobId: requireValue(values, 'job'), stage: requireValue(values, 'stage'),
      owner: requireValue(values, 'owner'), token: requireValue(values, 'token'),
      generation: Number(requireValue(values, 'generation')),
      outcome: requireValue(values, 'outcome'), reason: requireValue(values, 'reason'),
    });
    return ok({ jobId: job.jobId, stage: values.stage, status: job.status, outcome: job.stages[values.stage].status, attempts: job.stages[values.stage].attempts });
  }

  if (command === 'reopen') {
    const job = await queue.reopen({
      jobId: requireValue(values, 'job'), stage: requireValue(values, 'stage'),
      actor: requireValue(values, 'actor'), reason: requireValue(values, 'reason'),
    });
    return ok({ jobId: job.jobId, stage: values.stage, status: job.status });
  }

  if (command === 'verify') {
    const job = await queue.verify({
      jobId: requireValue(values, 'job'), actor: requireValue(values, 'actor'),
      receipt: { path: requireValue(values, 'receipt'), ...(values.sha256 ? { sha256: values.sha256 } : {}) },
    });
    return ok({ jobId: job.jobId, status: job.status, verifiedAt: job.verifiedAt });
  }

  if (command === 'build-handoff') {
    const job = await queue.getJob(requireValue(values, 'job'));
    if (!job) return fail('JOB_NOT_FOUND', 'No such job');
    const stage = requireValue(values, 'stage');
    const entry = job.stages[stage];
    if (!entry || entry.status !== 'done') return fail('STAGE_NOT_DONE', 'Only a completed stage can be handed off');
    const handoff = buildHandoff({
      job: { ...job, pipelineDeclarations: entry.declarations ?? {} }, stage,
      artifacts: entry.artifacts, producer: values.producer ?? 'cli',
    });
    const filename = values.out ? path.resolve(values.out) : queue.paths.handoffFile(job.jobId, stage);
    await writeHandoff(filename, handoff);
    return ok({ jobId: job.jobId, stage, handoff: filename, reviewRequired: handoff.review.required });
  }

  if (command === 'verify-handoff') {
    const filename = path.resolve(positionals[1] ?? requireValue(values, 'handoff', 'handoff'));
    const root = values['artifact-root'] ? path.resolve(values['artifact-root']) : path.dirname(filename);
    const { handoff, verified } = await readHandoff(filename, { root, config });
    return ok({ handoff: filename, jobId: handoff.jobId, stage: handoff.stage, artifacts: verified.artifacts.length, totalBytes: verified.totalBytes, review: verified.review, credentials: 'none' });
  }

  if (command === 'reconcile') {
    const result = await queue.reconcile();
    return ok({ reconciledAt: result.reconciledAt, reclaimed: result.reclaimed, status: result.status });
  }

  if (command === 'status') {
    return ok(await baseStatus(queue, config));
  }

  if (command === 'throttle') {
    const action = positionals[1] ?? 'show';
    const state = await loadThrottle(config.dataDir, config);
    if (action === 'show') return ok({ throttle: throttleSnapshot(state) });
    if (action === 'reset') {
      resetThrottle(state, values.host ?? null);
      await saveThrottle(config.dataDir, state);
      return ok({ throttle: throttleSnapshot(state), reset: values.host ?? 'all', note: 'Only reset after a human checked the profile for an auth/captcha challenge.' });
    }
    return fail('INVALID_THROTTLE_ACTION', 'Use throttle show|reset');
  }

  return fail('UNKNOWN_COMMAND', `Unknown command: ${command}`, EXIT.INVALID);
}

try {
  const { exit, payload } = await main();
  process.stdout.write(JSON.stringify(payload, null, 2) + '\n');
  process.exitCode = exit;
} catch (error) {
  const exit = ['LEASE_HELD', 'COLLECTOR_LOCKED', 'LEASE_LOST', 'THROTTLE_BLOCKED'].includes(error.code) ? EXIT.BLOCKED : EXIT.INVALID;
  process.stdout.write(JSON.stringify({ ok: false, error: { code: error.code ?? 'ERROR', message: error.message } }, null, 2) + '\n');
  process.exitCode = exit;
}
