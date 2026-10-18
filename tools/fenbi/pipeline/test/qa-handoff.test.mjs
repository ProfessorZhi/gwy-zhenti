import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { newQueue, enqueueInput } from './helpers.mjs';
import { sha256File } from '../src/fsutil.mjs';
import { importQaHandoff } from '../src/qa-handoff.mjs';
import { buildStageManifest, writeStageManifest } from '../src/manifest.mjs';

const SHA = (char) => char.repeat(64);

async function privateDir(t, prefix = 'qa-handoff-') {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  await fs.chmod(dir, 0o700);
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  return dir;
}

async function writePrivate(file, body) {
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  await fs.writeFile(file, body, { mode: 0o600 });
  await fs.chmod(file, 0o600);
}

async function packageFor(t, { id = '9000001', title = '合成QA样卷', mutate = null, bodies = {} } = {}) {
  const dir = await privateDir(t);
  const artDir = path.join(dir, 'artifacts');
  await fs.mkdir(artDir, { recursive: true, mode: 0o700 });
  const summaryBody = bodies.summary ?? JSON.stringify({ questions: [{ number: 1, status: 'metadata_only' }, { number: 2, status: 'metadata_only' }] }) + '\n';
  const indexBody = bodies.index ?? JSON.stringify({ index: [{ number: 1, unknown: false }, { number: 2, unknown: false }] }) + '\n';
  const assetBody = bodies.asset ?? JSON.stringify({ images: [{ ref: 'material/q1.png', sha256: SHA('a') }] }) + '\n';
  const files = [
    { name: 'summary.json', kind: 'summary', body: summaryBody },
    { name: 'index.json', kind: 'question_index', body: indexBody },
    { name: 'asset-manifest.json', kind: 'asset_manifest', body: assetBody },
  ];
  const artifacts = [];
  for (const file of files) {
    const filename = path.join(artDir, file.name);
    await writePrivate(filename, file.body);
    const hashed = await sha256File(filename);
    artifacts.push({ path: `artifacts/${file.name}`, kind: file.kind, sha256: hashed.sha256, bytes: hashed.bytes });
  }
  const handoff = {
    schemaVersion: 1,
    kind: 'gwy-zhenti-staged-qa-handoff',
    producer: { agent: 'synthetic-browser-owner', at: '2026-10-18T00:00:00.000Z' },
    permissions: { browserProfile: false, cookies: false, tokens: false, rawSiteTextIncluded: false, imageBytesIncluded: false },
    identity: { paperSourceId: id, version: 'qa-v1', title, subject: 'xingce', area: '浙江', year: 2026, variant: 'C类' },
    source: {
      category: 'observed_ui', license: null, redistribution: 'local_only',
      evidence: [{ type: 'observed_ui', ref: 'synthetic owner metadata package' }],
    },
    summary: {
      questionCount: 2, questionNumbers: [1, 2], materialCount: 0,
      placeholderNumbers: [], unknownNumbers: [], imageCount: 1,
    },
    artifacts,
    assets: [{ ref: 'material/q1.png', sha256: SHA('a'), bytes: 12 }],
  };
  if (mutate) mutate(handoff);
  const handoffFile = path.join(dir, 'qa-handoff.json');
  await writePrivate(handoffFile, JSON.stringify(handoff, null, 2) + '\n');
  return { dir, handoffFile, handoff, artDir, artifacts };
}

async function allowlistFor(t, ids) {
  const dir = await privateDir(t, 'qa-allow-');
  const file = path.join(dir, 'allowlist.json');
  await writePrivate(file, JSON.stringify({ sourceIds: ids.map((id) => ({ id })) }));
  return { dir, file, value: { source: file, missing: false, ids: new Set(ids), entries: new Map(ids.map((id) => [id, { id }])), list: ids.map((id) => ({ id })) } };
}

test('a private metadata-only QA package imports as an offline staged job without a capture lease', async (t) => {
  const { queue, config } = await newQueue(t);
  const pkg = await packageFor(t);
  const list = await allowlistFor(t, ['9000001']);
  const result = await importQaHandoff({ queue, config, filename: pkg.handoffFile, artifactRoot: pkg.dir, allowlist: list.value });
  assert.equal(result.created, true);
  assert.equal(result.captureMode, 'offline_handoff');
  const job = await queue.getJob(result.jobId);
  assert.equal(job.stages.capture_ready.status, 'done');
  assert.equal(job.stages.capture_ready.mode, 'offline_handoff');
  assert.equal(job.stages.normalized.status, 'pending');
  assert.equal(job.qaSummary.questionCount, 2);
  assert.equal(job.images.length, 1);
  assert.equal(job.allowCapture, false);
  const leases = await fs.readdir(path.join(config.dataDir, 'leases'));
  assert.equal(leases.filter((name) => name.endsWith('.json')).length, 0, 'import must not create a capture lease');
  const second = await importQaHandoff({ queue, config, filename: pkg.handoffFile, artifactRoot: pkg.dir, allowlist: list.value });
  assert.equal(second.created, false);
  assert.equal(second.duplicate, true);
  assert.equal((await queue.listJobs()).length, 1);
});

test('OS permissions, raw content, URLs, rights and hashes fail closed', async (t) => {
  const { queue, config } = await newQueue(t);
  const list = await allowlistFor(t, ['9000001']);
  const cases = [];

  const loose = await packageFor(t);
  await fs.chmod(loose.handoffFile, 0o644);
  cases.push([loose, /QA_HANDOFF_INSECURE_PERMISSIONS/]);

  const symlink = await packageFor(t);
  const link = path.join(symlink.dir, 'link.json');
  await fs.symlink(symlink.handoffFile, link);
  cases.push([{ ...symlink, handoffFile: link }, /QA_HANDOFF_INSECURE_PERMISSIONS/]);

  const looseArtifact = await packageFor(t);
  await fs.chmod(path.join(looseArtifact.artDir, 'summary.json'), 0o644);
  cases.push([looseArtifact, /QA_HANDOFF_INSECURE_PERMISSIONS/]);

  const rawFlag = await packageFor(t, { mutate: (h) => { h.permissions.rawSiteTextIncluded = true; } });
  cases.push([rawFlag, /QA_HANDOFF_RAW_CONTENT/]);
  const urlField = await packageFor(t, { mutate: (h) => { h.identity.url = 'https://www.fenbi.com/spa/tiku/exam/1'; } });
  cases.push([urlField, /QA_HANDOFF_URL_NOT_ALLOWED/]);
  const allowed = await packageFor(t, { mutate: (h) => { h.source.redistribution = 'allowed'; } });
  cases.push([allowed, /QA_HANDOFF_REDISTRIBUTION/]);
  const noEvidence = await packageFor(t, { mutate: (h) => { h.source.evidence = [{ type: 'metadata-handoff', ref: 'synthetic' }]; } });
  cases.push([noEvidence, /QA_HANDOFF_OBSERVATION_EVIDENCE/]);
  const unknownKey = await packageFor(t, { mutate: (h) => { h.summary.contentHtml = '<p>raw</p>'; } });
  cases.push([unknownKey, /QA_HANDOFF_RAW_CONTENT/]);
  const rawHtml = await packageFor(t, { bodies: { summary: '<html><body>raw site text</body></html>' } });
  cases.push([rawHtml, /QA_HANDOFF_RAW_CONTENT|QA_HANDOFF_SCHEMA/]);
  const png = await packageFor(t, { bodies: { summary: Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a,0,0,0,0]) } });
  cases.push([png, /QA_HANDOFF_RAW_CONTENT|QA_HANDOFF_SCHEMA/]);
  const badKind = await packageFor(t, { mutate: (h) => { h.artifacts[0].kind = 'raw_html'; } });
  cases.push([badKind, /QA_HANDOFF_RAW_CONTENT/]);
  const artifactUrl = await packageFor(t, { mutate: (h) => { h.artifacts[0].path = 'https://evil.test/summary.json'; } });
  cases.push([artifactUrl, /UNSAFE_ASSET_REF/]);
  const assetUrl = await packageFor(t, { mutate: (h) => { h.assets[0].ref = 'file:/etc/passwd'; } });
  cases.push([assetUrl, /UNSAFE_ASSET_REF/]);
  const assetData = await packageFor(t, { mutate: (h) => { h.assets[0].ref = 'data:image/png;base64,AAAA'; } });
  cases.push([assetData, /UNSAFE_ASSET_REF/]);
  const badSha = await packageFor(t, { mutate: (h) => { h.assets[0].sha256 = SHA('0'); } });
  cases.push([badSha, /QA_HANDOFF_HASH_MISMATCH|QA_HANDOFF_SCHEMA/]);
  const unauthorized = await packageFor(t, { id: '9999999', title: '未授权合成QA样卷' });
  for (const [pkg, expected] of cases) {
    await assert.rejects(
      importQaHandoff({ queue, config, filename: pkg.handoffFile, artifactRoot: pkg.dir, allowlist: list.value }),
      expected,
    );
  }
  await assert.rejects(
    importQaHandoff({ queue, config, filename: unauthorized.handoffFile, artifactRoot: unauthorized.dir, allowlist: list.value }),
    /QA_HANDOFF_NOT_AUTHORIZED/,
  );
  assert.equal((await queue.listJobs()).length, 0, 'no rejected package creates a job');
});

test('the read-only work manifest exposes range, owner and paths but no raw content or URL', async (t) => {
  const { queue, config } = await newQueue(t);
  const pkg = await packageFor(t);
  const list = await allowlistFor(t, ['9000001']);
  const imported = await importQaHandoff({ queue, config, filename: pkg.handoffFile, artifactRoot: pkg.dir, allowlist: list.value });
  const manifest = buildStageManifest({ jobs: await queue.listJobs(), stage: 'normalized', config });
  assert.equal(manifest.tasks.length, 1);
  const task = manifest.tasks[0];
  assert.equal(task.jobId, imported.jobId);
  assert.deepEqual(task.range.questionNumbers, [1, 2]);
  assert.equal(task.range.questionCount, 2);
  assert.equal(task.stage, 'normalized');
  assert.match(task.suggestedOwner, /^normalized-1$/);
  assert.match(task.workDir, new RegExp(`artifacts/${imported.jobId}/normalized$`));
  assert.equal(task.permissions.readOnly, true);
  assert.equal(task.permissions.browserProfile, false);
  assert.equal(task.permissions.imageBytes, false);
  assert.deepEqual(task.unknownNumbers, []);
  const text = JSON.stringify(manifest);
  assert.doesNotMatch(text, /https?:\/\/|contentHtml|<html|<p>/i);
  const file = path.join(pkg.dir, 'manifest.json');
  await writeStageManifest(file, manifest);
  const stat = await fs.stat(file);
  assert.equal(stat.mode & 0o777, 0o600);
});

test('a capture_ready manifest is owner-only and is not assignable to offline workers', async (t) => {
  const { queue, config } = await newQueue(t);
  await queue.enqueue(enqueueInput({ paperSourceId: '9100001' }));
  const manifest = buildStageManifest({ jobs: await queue.listJobs(), stage: 'capture_ready', config });
  assert.equal(manifest.tasks.length, 1);
  const task = manifest.tasks[0];
  assert.equal(task.requiresBrowserOwner, true);
  assert.equal(task.assignableToOfflineWorker, false);
  assert.equal(task.suggestedOwner, 'browser-owner');
  assert.equal(task.permissions.readOnly, false);
  assert.equal(task.permissions.browserProfile, 'owner-only');
  assert.equal(manifest.requiresBrowserOwner, true);
  assert.equal(manifest.permissions.browserProfile, 'owner-only');
});
