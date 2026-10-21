// Exercise the real diff subprocess transport with output larger than Node's
// default execFileSync maxBuffer (1 MiB). This is a synthetic Git-output fixture;
// normal content-gate tests exercise real Git repository semantics separately.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { changes } from '../src/content-gate.mjs';

test('structural diff accepts more than 1 MiB of changed filenames', async t => {
  if (process.platform === 'win32') {
    t.skip('the synthetic executable fixture requires a Unix shebang');
    return;
  }
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'fenbi-large-diff-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const fakeGit = path.join(dir, 'git');
  const code = [
    '#!' + process.execPath,
    "const items = Array.from({length: 6000}, (_, i) => 'A\\t图片/' + String(i).padStart(6, '0') + '-' + 'x'.repeat(200) + '.png\\n');",
    'process.stdout.write(items.join(\'\'));',
    ''
  ].join('\n');
  await fs.writeFile(fakeGit, code, { mode: 0o755 });
  const oldPath = process.env.PATH;
  try {
    process.env.PATH = dir + path.delimiter + (oldPath || '');
    const rows = changes(dir, 'main');
    assert.equal(rows.length, 6000);
    assert.equal(rows[0].status, 'A');
    assert.equal(rows[5999].status, 'A');
    assert.ok(rows.every(r => r.file.startsWith('图片/')));
    assert.ok(Buffer.byteLength(rows.map(r => r.status + '\t' + r.file + '\n').join('')) > 1024 * 1024);
  } finally {
    if (oldPath === undefined) delete process.env.PATH;
    else process.env.PATH = oldPath;
  }
});
