import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { temporary } from './helpers.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(HERE, '..', 'examples', 'hourly-drain.sh');

function run(script, env) {
  return new Promise((resolve) => {
    execFile('bash', [script], { timeout: 30_000, env }, (error, stdout, stderr) => {
      resolve({ code: error?.code ?? 0, stdout, stderr });
    });
  });
}

test('the hourly example is one bounded pass and preserves exit 2 when the adapter is unwired', async (t) => {
  const dir = await temporary(t, 'hourly-');
  const data = path.join(dir, 'data');
  const config = path.join(dir, 'config.json');
  await fs.writeFile(config, JSON.stringify({ dataDir: data, authorizedSourceIds: null }));
  const result = await run(SCRIPT, { ...process.env, GWY_PIPELINE_CONFIG: config, GWY_COLLECTOR_BUDGET: '1' });
  assert.equal(result.code, 2, result.stderr);
  assert.match(result.stdout, /collector_unwired/);
  assert.match(result.stdout, /collector exit=2/);
  assert.match(result.stdout, /no capture was attempted/);
  assert.match(result.stdout, /"ok": true/);
  // No daemon behavior: the process returns after the bounded pass instead of waiting.
  assert.doesNotMatch(result.stdout, /sleep|while true/);
});
