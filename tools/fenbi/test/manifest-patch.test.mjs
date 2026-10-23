import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { planManifestPatch, applyManifestPatch } from '../src/manifest-patch.mjs';

const row = (pathValue, sha) => JSON.stringify({ path: pathValue, subject: '申论', declared_questions: 4, sha256: sha, notes: ['合成'] });
const manifest = () => [row('省考/甲/2026/申论-A卷.md', 'a'.repeat(64)), row('省考/乙/2026/申论-B卷.md', 'b'.repeat(64)), row('省考/丙/2026/申论-C卷.md', 'c'.repeat(64))].join('\n') + '\n';

test('line-level update changes only the target line byte-for-byte', () => {
  const before = manifest();
  const plan = planManifestPatch({
    manifestText: before,
    updates: [{ path: '省考/乙/2026/申论-B卷.md', expectSha256: 'b'.repeat(64), set: { declared_questions: 5, notes: ['合成', '增量'] } }],
  });
  assert.equal(plan.ok, true);
  assert.equal(plan.changed, 1);
  const beforeLines = before.split('\n');
  const afterLines = plan.text.split('\n');
  assert.equal(beforeLines[0], afterLines[0]);
  assert.equal(beforeLines[2], afterLines[2]);
  assert.notEqual(beforeLines[1], afterLines[1]);
  const updated = JSON.parse(afterLines[1]);
  assert.equal(updated.declared_questions, 5);
  assert.equal(updated.sha256, 'b'.repeat(64));
  assert.equal(afterLines.length, beforeLines.length);
});

test('SHA mismatch refuses the whole patch', () => {
  const plan = planManifestPatch({
    manifestText: manifest(),
    updates: [{ path: '省考/乙/2026/申论-B卷.md', expectSha256: 'd'.repeat(64), set: { declared_questions: 5 } }],
  });
  assert.equal(plan.ok, false);
  assert.equal(plan.conflicts[0].type, 'sha-conflict');
  assert.equal(plan.changed, 0);
  assert.equal(plan.text, manifest());
});

test('missing key and duplicate key refuse the patch', () => {
  const missing = planManifestPatch({ manifestText: manifest(), updates: [{ path: '省考/丁/2026/申论.md', set: { x: 1 } }] });
  assert.equal(missing.ok, false);
  assert.equal(missing.conflicts[0].type, 'key-not-found');
  const duplicated = [row('省考/乙/2026/申论-B卷.md', 'b'.repeat(64)), row('省考/乙/2026/申论-B卷.md', 'b'.repeat(64))].join('\n');
  const conflict = planManifestPatch({ manifestText: duplicated, updates: [{ path: '省考/乙/2026/申论-B卷.md', set: { x: 1 } }] });
  assert.equal(conflict.ok, false);
  assert.equal(conflict.conflicts[0].type, 'duplicate-key');
});

test('key cannot be rewritten and no-op leaves text identical', () => {
  const before = manifest();
  const immutable = planManifestPatch({ manifestText: before, updates: [{ path: '省考/乙/2026/申论-B卷.md', set: { path: '别的路径.md' } }] });
  assert.equal(immutable.ok, false);
  const noop = planManifestPatch({ manifestText: before, updates: [{ path: '省考/乙/2026/申论-B卷.md', set: { declared_questions: 4 } }] });
  assert.equal(noop.ok, true);
  assert.equal(noop.changed, 0);
  assert.equal(noop.text, before);
});

test('applyManifestPatch check mode does not write; apply mode writes atomically', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'manifest-patch-'));
  try {
    const file = path.join(dir, 'manifest.jsonl');
    const before = manifest();
    await writeFile(file, before);
    const updates = [{ path: '省考/乙/2026/申论-B卷.md', expectSha256: 'b'.repeat(64), set: { declared_questions: 5 } }];
    const checked = applyManifestPatch({ manifestPath: file, updates, checkOnly: true });
    assert.equal(checked.ok, true);
    assert.equal(checked.written, false);
    assert.equal(await readFile(file, 'utf8'), before);
    const applied = applyManifestPatch({ manifestPath: file, updates, checkOnly: false });
    assert.equal(applied.ok, true);
    assert.equal(applied.written, true);
    const after = await readFile(file, 'utf8');
    assert.notEqual(after, before);
    assert.equal(after.split('\n')[0], before.split('\n')[0]);
    assert.equal(after.split('\n')[2], before.split('\n')[2]);
    assert.equal(JSON.parse(after.split('\n')[1]).declared_questions, 5);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('all-or-nothing: one conflict prevents any line from changing', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'manifest-patch-'));
  try {
    const file = path.join(dir, 'manifest.jsonl');
    const before = manifest();
    await writeFile(file, before);
    const result = applyManifestPatch({
      manifestPath: file,
      updates: [
        { path: '省考/甲/2026/申论-A卷.md', set: { declared_questions: 9 } },
        { path: '不存在/申论.md', set: { declared_questions: 9 } },
      ],
      checkOnly: false,
    });
    assert.equal(result.ok, false);
    assert.equal(result.written, false);
    assert.equal(await readFile(file, 'utf8'), before);
  } finally { await rm(dir, { recursive: true, force: true }); }
});
