import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const cli = path.resolve(here, '../src/shard-qa.mjs');
const sha = (n) => n.toString(16).padStart(64, '0');

function observation(sourceId, overrides = {}) {
  return {
    paperSourceId: sourceId,
    title: `synthetic-${sourceId}`,
    subject: 'xingce',
    area: '测试区',
    year: 2026,
    variant: 'C类',
    version: 'recall-v1',
    questionCount: 3,
    contentStatus: 'observed',
    route: { kind: 'existing_practice', urlObserved: true, contentStatus: 'observed', questionCount: 3, imageContentOnly: false },
    rights: { category: 'observed_ui', license: null, redistribution: 'local_only', evidence: [] },
    images: [{ ref: 'img-1', sourceUrl: null, sha256: sha(1) }, { ref: 'img-2', sourceUrl: null, sha256: sha(2) }],
    permissions: { browserProfile: false, cookies: false, tokens: false },
    ...overrides,
  };
}

function matchedRow(n) {
  return {
    sourceId: `q-${n}`,
    sourceNumber: n,
    repositoryId: `r-${n}`,
    repositoryNumber: n,
    matchMethod: 'explicit-number-and-content',
    status: 'matched',
    dimensions: {
      qid: { status: 'not_compared', reason: 'question-id-namespaces-incompatible' },
      number: { status: 'same', reason: 'explicit-number-comparison' },
      stem: { status: 'same', reason: 'normalized-text-equal' },
      options: { status: 'same', reason: 'all-options-equal' },
      materials: { status: 'same', reason: 'material-count-and-content-equal' },
      answer: { status: 'unknown', reason: 'source-content-not-observed' },
      explanation: { status: 'unknown', reason: 'source-content-not-observed' },
      images: { status: 'not_compared', reason: 'no-image-references' },
    },
  };
}

function paperSpec(sourceId, perQuestionFile) {
  return {
    sourceId,
    area: '测试区',
    year: 2026,
    variant: 'C类',
    subject: 'xingce',
    positions: 3,
    textUsable: 3,
    imagePositions: 0,
    placeholders: 0,
    verified: 3,
    remaining: 0,
    weak: 0,
    perQuestion: perQuestionFile ? {
      file: perQuestionFile,
      key: 'rows',
      expectedMatched: 3,
      expectedUnmatchedSourceNumbers: [],
    } : null,
  };
}

async function fixture({ papers, observations, rowsByPaper = {}, verify = 3 }) {
  const dir = await mkdtemp(path.join(tmpdir(), 'shard-qa-'));
  const alignments = {};
  for (const [sourceId, rows] of Object.entries(rowsByPaper)) {
    const name = `align-${sourceId}.json`;
    const file = path.join(dir, name);
    await writeFile(file, JSON.stringify({ rows }, null, 2));
    alignments[sourceId] = file;
  }
  const spec = {
    schemaVersion: 1,
    kind: 'gwy-zhenti-shard-spec',
    batch: 'test',
    papers: papers.map((p) => {
      if (p.perQuestion === false) return paperSpec(p.sourceId, null);
      const s = paperSpec(p.sourceId, alignments[p.sourceId] || null);
      s.verified = verify;
      s.remaining = p.remaining ?? Math.max(0, 3 - verify);
      s.weak = p.weak ?? 0;
      return s;
    }),
  };
  await writeFile(path.join(dir, 'spec.json'), JSON.stringify(spec, null, 2));
  await writeFile(path.join(dir, 'inbox.json'), JSON.stringify({ observations }, null, 2));
  return { dir, spec: path.join(dir, 'spec.json'), inbox: path.join(dir, 'inbox.json') };
}

function run(fx, extra = []) {
  const out = path.join(fx.dir, 'result.json');
  const md = path.join(fx.dir, 'report.md');
  const r = spawnSync(process.execPath, [cli, '--spec', fx.spec, '--inbox', fx.inbox, '--out', out, '--md', md, ...extra], { encoding: 'utf8' });
  return { status: r.status, stderr: r.stderr, out, md };
}

test('full per-question shard passes with exit 0', async () => {
  const fx = await fixture({
    papers: [{ sourceId: '9001', perQuestion: true }, { sourceId: '9002', perQuestion: true }],
    observations: [observation('9001'), observation('9002')],
    rowsByPaper: { 9001: [1, 2, 3].map(matchedRow), 9002: [1, 2, 3].map(matchedRow) },
  });
  const r = run(fx);
  assert.equal(r.status, 0, r.stderr);
  const result = JSON.parse(await readFile(r.out, 'utf8'));
  assert.equal(result.exitCode, 0);
  assert.equal(result.summary.verified, 2);
  assert.equal(result.summary.perQuestionRows, 6);
  const md = await readFile(r.md, 'utf8');
  assert.match(md, /exit: \*\*0\*\*/);
  await rm(fx.dir, { recursive: true, force: true });
});

test('missing per-question shard is blocked, exit 2, token BLOCKED_HOFF_OWNERS', async () => {
  const fx = await fixture({
    papers: [{ sourceId: '9001', perQuestion: true }, { sourceId: '9002', perQuestion: false }],
    observations: [observation('9001'), observation('9002')],
    rowsByPaper: { 9001: [1, 2, 3].map(matchedRow) },
  });
  const r = run(fx);
  assert.equal(r.status, 2, r.stderr);
  const result = JSON.parse(await readFile(r.out, 'utf8'));
  assert.equal(result.summary.blocked, 1);
  assert.ok(result.papers.find((p) => p.sourceId === '9002').reasons.includes('BLOCKED_HOFF_OWNERS:per-question-shard-absent'));
  await rm(fx.dir, { recursive: true, force: true });
});

test('identity mismatch is invalid, exit 1', async () => {
  const fx = await fixture({
    papers: [{ sourceId: '9001', perQuestion: true }],
    observations: [observation('9001', { area: '别的区' })],
    rowsByPaper: { 9001: [1, 2, 3].map(matchedRow) },
  });
  const r = run(fx);
  assert.equal(r.status, 1, r.stderr);
  const result = JSON.parse(await readFile(r.out, 'utf8'));
  assert.ok(result.papers[0].reasons.includes('identity-mismatch'));
  await rm(fx.dir, { recursive: true, force: true });
});

test('duplicate image sha is invalid, exit 1', async () => {
  const obs = observation('9001');
  obs.images = [{ ref: 'a', sourceUrl: null, sha256: sha(1) }, { ref: 'b', sourceUrl: null, sha256: sha(1) }];
  const fx = await fixture({
    papers: [{ sourceId: '9001', perQuestion: true }],
    observations: [obs],
    rowsByPaper: { 9001: [1, 2, 3].map(matchedRow) },
  });
  const r = run(fx);
  assert.equal(r.status, 1, r.stderr);
  const result = JSON.parse(await readFile(r.out, 'utf8'));
  assert.ok(result.papers[0].reasons.some((x) => x.startsWith('duplicate-image-sha')));
  await rm(fx.dir, { recursive: true, force: true });
});

test('per-question vs PR72 caliber conflict is needs_review, exit 2', async () => {
  const fx = await fixture({
    papers: [{ sourceId: '9001', perQuestion: true }],
    observations: [observation('9001')],
    rowsByPaper: { 9001: [1, 2, 3].map(matchedRow) },
    verify: 2,
  });
  const r = run(fx);
  assert.equal(r.status, 2, r.stderr);
  const result = JSON.parse(await readFile(r.out, 'utf8'));
  const p = result.papers[0];
  assert.equal(p.status, 'needs_review');
  assert.ok(p.warnings.some((x) => x.startsWith('caliber_conflict')));
  await rm(fx.dir, { recursive: true, force: true });
});

test('closed counts are enforced, exit 1', async () => {
  const fx = await fixture({
    papers: [{ sourceId: '9001', perQuestion: true }],
    observations: [observation('9001')],
    rowsByPaper: { 9001: [1, 2, 3].map(matchedRow) },
    verify: 3,
  });
  const spec = JSON.parse(await readFile(fx.spec, 'utf8'));
  spec.papers[0].weak = 1;
  await writeFile(fx.spec, JSON.stringify(spec, null, 2));
  const r = run(fx);
  assert.equal(r.status, 1, r.stderr);
  const result = JSON.parse(await readFile(r.out, 'utf8'));
  assert.ok(result.papers[0].reasons.includes('closure:textUsable'));
  await rm(fx.dir, { recursive: true, force: true });
});
