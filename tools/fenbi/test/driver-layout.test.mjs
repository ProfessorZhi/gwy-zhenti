import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const drivers = [
  'fenbi-service.mjs',
  'p0-discover-regions.mjs',
  'build-candidates-live.mjs',
  'capture-new-generic.mjs',
  't2-phaseb2.mjs',
  't2-collector.mjs',
  't2-backfill-json.mjs',
  't2-asset-pass.mjs',
];

test('all stateful collector processes resolve one absolute runtime work directory', () => {
  for (const name of drivers) {
    const source = read('tools/fenbi/driver/' + name);
    assert.ok(source.includes("const B = path.resolve(process.env.FENBI_BASE ||"), name + ' base');
    assert.ok(source.includes("const WORK = path.resolve(process.env.FENBI_WORK_DIR || path.join(B, 'work/fenbi'));"), name + ' work');
  }
});

test('systemd examples require explicit absolute checkout paths', () => {
  for (const name of ['fenbi-pipeline', 'fenbi-publisher']) {
    const unit = read('deploy/systemd/' + name + '.service.example');
    assert.ok(unit.includes('WorkingDirectory=REPO_ABSOLUTE_PATH'), name);
    assert.ok(!unit.includes('%h/REPO_PLACEHOLDER'), name);
  }
  const collector = read('deploy/systemd/fenbi-pipeline.service.example');
  assert.ok(collector.includes('ExecStart=NODE_ABSOLUTE_PATH REPO_ABSOLUTE_PATH/'));
});
