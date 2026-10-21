import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { riskDecision } from '../driver/service-risk.mjs';

const pexec = promisify(execFile);
const PHASEB2 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../driver/t2-phaseb2.mjs');

// Runs the real t2-phaseb2 with a stand-in capture child that prints the given risk counters,
// then feeds its last JSON line to the service decision, as fenbi-service does.
async function runBatch(t, childRisk) {
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'phaseb2-'));
  t.after(() => fs.rm(base, { recursive: true, force: true }));
  const work = path.join(base, 'work/fenbi');
  await fs.mkdir(path.join(work, 'papers'), { recursive: true });
  await fs.mkdir(path.join(work, 't2-20261019'), { recursive: true });
  await fs.writeFile(path.join(work, 't2-20261019/ledger.json'), JSON.stringify({ papers: {} }));
  const cand = path.join(work, 'candidates.json');
  await fs.writeFile(cand, JSON.stringify({ candidates: [
    { id: '901', title: '2025年国考行测（地市级）', year: 2025, area: '国考', region: '国考' },
    { id: '902', title: '2025年国考行测（副省级）', year: 2025, area: '国考', region: '国考' }] }));
  const fake = path.join(base, 'fake-capture.mjs');
  await fs.writeFile(fake, `console.log(JSON.stringify({ ok: true, counts: { questions: 130 }, risk: ${JSON.stringify(childRisk)} }));\n`);
  const { stdout } = await pexec(process.execPath, [PHASEB2], { env: { ...process.env, FENBI_BASE: base,
    FENBI_WORK_DIR: work, CANDIDATES_FILE: cand, PHASEB2_CAPTURE_SCRIPT: fake, PHASEB2_MAX: '5' } });
  const last = stdout.trim().split('\n').reverse().find(l => l.trim().startsWith('{'));
  return JSON.parse(last);
}

test('a 403 inside one paper ends the batch and makes the service back off', async t => {
  const summary = await runBatch(t, { captcha: 0, loginLost: 0, http403: 1, http429: 0 });
  assert.equal(summary.stopReason, 'risk');
  assert.equal(summary.ok, 1, 'stops after the first paper, does not continue the batch');
  assert.equal(summary.risk.http403, 1);
  assert.equal(riskDecision(summary, [], Date.now(), 0).action, 'backoff');
});

test('a lost login inside one paper makes the service stop', async t => {
  const summary = await runBatch(t, { captcha: 0, loginLost: 1, http403: 0, http429: 0 });
  assert.equal(summary.stopReason, 'risk');
  assert.equal(riskDecision(summary, [], Date.now(), 0).action, 'stop');
});

test('a clean batch processes every paper and is ok', async t => {
  const summary = await runBatch(t, { captcha: 0, loginLost: 0, http403: 0, http429: 0 });
  assert.deepEqual([summary.ok, summary.stopReason], [2, 'done']);
  assert.equal(riskDecision(summary, [], Date.now(), 0).action, 'ok');
});

test('a child with no receipt and a non-zero exit is not a clean round', () => {
  assert.equal(riskDecision(null, [], Date.now(), 1).action, 'backoff');
});

test('asset-pass 401 is a hard stop, 403 is soft', () => {
  assert.equal(riskDecision({ risk: { s401: 1, s403: 0, s429_503: 0 }, stopReason: 'unauthorized' }, []).action, 'stop');
  assert.equal(riskDecision({ risk: { s401: 0, s403: 1, s429_503: 0 } }, []).action, 'backoff');
});
