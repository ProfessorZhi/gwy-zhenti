import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { pickRow, collectPaperIds, bindingStatus, ambiguousTitles } from '../worker/identity.mjs';

const T = '2025年国考行测（地市级）';
const LONG = '2025年国考行测（地市级）网友回忆版';

test('the catalog row is chosen by exact title, never by the first substring match', () => {
  assert.equal(pickRow([`${LONG} 继续练习`, `${T} 130道题`], T, [LONG]), 1);
  assert.equal(pickRow([`${LONG} 继续练习`], T, [LONG]).error, 'ROW_NOT_FOUND', 'only the longer title is on this page');
  assert.equal(pickRow([`${T} 130道`, `${T} 130道`], T, []).error, 'AMBIGUOUS_ROW');
  assert.equal(pickRow([`练习 ${T}`], T, []), 0, 'title not at the start still matches when unique');
});

test('paperId values are collected from nested JSON and compared with the source id', () => {
  const ids = collectPaperIds({ sheet: { paperId: 901, name: 'x' }, list: [{ paperId: '901' }], other: { id: 5 } });
  assert.deepEqual([...ids], ['901']);
  assert.equal(bindingStatus(ids, '901'), 'verified');
  assert.equal(bindingStatus(new Set(['902']), '901'), 'mismatch');
  assert.equal(bindingStatus(new Set(['901', '902']), '901'), 'mixed');
  assert.equal(bindingStatus(new Set(), '901'), 'unobserved');
  assert.deepEqual([...ambiguousTitles([{ id: 1, title: T, area: '国考', year: 2025 }, { id: 2, title: LONG, area: '国考', year: 2025 }])], [['1', ['2']]]);
});

test('offline identity check: verified papers get evidence, mismatched and ambiguous ones are quarantined', async t => {
  const work = await fs.mkdtemp(path.join(os.tmpdir(), 'fenbi-ident-'));
  t.after(() => fs.rm(work, { recursive: true, force: true }));
  const paper = async (key, id, title, payload, pageTitle) => {
    await fs.mkdir(path.join(work, 'papers', key), { recursive: true });
    await fs.writeFile(path.join(work, 'papers', key, 'document.json'), JSON.stringify({ identity: { id, title, area: '国考', year: 2025 }, evidence: [] }));
    await fs.writeFile(path.join(work, 'papers', key, 'run-summary.json'), JSON.stringify({ sourceId: id, pageTitle }));
    if (payload) { await fs.mkdir(path.join(work, 't2-20261019/payloads', key), { recursive: true }); await fs.writeFile(path.join(work, 't2-20261019/payloads', key, 'a.json'), JSON.stringify(payload)); }
  };
  await paper('a-1', '1', T, { sheet: { paperId: 1 } }, T);
  await paper('b-2', '2', LONG, { sheet: { paperId: 3 } }, LONG);
  await paper('c-4', '4', '2024年国考行测（副省级）', null, '2024年国考行测（副省级）');
  await paper('d-5', '5', '2025年国考行测（地市级）', null, '练习');   // same title as a-1's ambiguous group, page title does not confirm
  const script = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../worker/verify-identity.mjs');
  const out = execFileSync(process.execPath, [script, '--write'], { env: { ...process.env, FENBI_WORK_DIR: work }, encoding: 'utf8' });
  const s = JSON.parse(out.trim().split('\n').pop());
  assert.deepEqual([s.papers, s.verified, s.quarantine, s.unverified, s.paperIdMismatch], [4, 1, 2, 1, 1]);
  const doc = JSON.parse(await fs.readFile(path.join(work, 'papers/a-1/document.json'), 'utf8'));
  assert.equal(doc.evidence[0].type, 'source-paper-identity');
  const q = JSON.parse(await fs.readFile(path.join(work, 't2-20261019/identity-quarantine.json'), 'utf8'));
  assert.deepEqual(Object.keys(q).sort(), ['2', '5']);
});
