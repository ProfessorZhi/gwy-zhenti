import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { runKpi } from '../src/kpi-report.mjs';

const MAIN = 'a'.repeat(40);

async function files ({catalog, papers}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'kpi-'));
  const manifestPath = path.join(root, 'manifest.jsonl');
  const papersPath = path.join(root, 'papers.json');
  await fs.writeFile(manifestPath, catalog.map(r => JSON.stringify(r)).join('\n') + '\n');
  await fs.writeFile(papersPath, JSON.stringify(papers));
  return {root, manifestPath, papersPath};
}

test('1 KPI counts only papers bound to the current main sha and QA receipt', async () => {
  const {manifestPath, papersPath} = await files({
    catalog: [
      {sourceId: '1', subject: 'xingce', area: '浙江', year: 2020},
      {sourceId: '2', subject: 'xingce', area: '浙江', year: 2020}
    ],
    papers: [
      {mainSha: MAIN, sourceId: '1', subject: 'xingce', qa: {verdict: 'pass', reportSha256: 'b'.repeat(64)}},
      {sourceId: '2', subject: 'xingce', qa: {verdict: 'pass', reportSha256: 'b'.repeat(64)}}
    ]
  });
  const r = await runKpi({manifestPath, papersPath, mainSha: MAIN});
  assert.equal(r.ok, true);
  assert.equal(r.kpi.numerator, 1);
  assert.equal(r.kpi.denominator, 2);
  assert.equal(r.kpi.value, 0.5);
});

test('2 catalog without sourceId yields UNKNOWN, never a fabricated ratio', async () => {
  const {manifestPath, papersPath} = await files({
    catalog: [{path: '省考/浙江/2020/行测-A.md', year: 2020}],
    papers: [{mainSha: MAIN, sourceId: '1', subject: 'xingce', qa: {verdict: 'pass', reportSha256: 'b'.repeat(64)}}]
  });
  const r = await runKpi({manifestPath, papersPath, mainSha: MAIN});
  assert.equal(r.kpi.status, 'UNKNOWN');
  assert.equal(r.kpi.value, null);
});

test('3 missing main sha is UNKNOWN and out-of-range catalog years are excluded', async () => {
  const {manifestPath, papersPath} = await files({
    catalog: [
      {sourceId: '1', subject: 'xingce', area: '浙江', year: 2005},
      {sourceId: '2', subject: 'xingce', area: '江苏', year: 2005}
    ],
    papers: []
  });
  const out = await runKpi({manifestPath, papersPath, mainSha: ''});
  assert.equal(out.kpi.status, 'UNKNOWN');
  const r = await runKpi({manifestPath, papersPath, mainSha: MAIN});
  assert.equal(r.kpi.status, 'UNKNOWN'); // both years below policy ranges
});
