// catalog/manifest.jsonl 的行级增量更新。
//
// 多个内容线可能同时改 manifest；本模块只替换 key（默认 path）命中的单行，
// 其余行逐字节保持不变，并在应用前校验 expectSha256，避免覆盖别人的版本。
import fs from 'node:fs';

function parseLines(manifestText) {
  const text = String(manifestText ?? '');
  const hasFinalNewline = text.endsWith('\n');
  const lines = text.split('\n');
  if (hasFinalNewline) lines.pop();
  return { lines, hasFinalNewline };
}

function indexRows(lines, key) {
  const byKey = new Map();
  const invalid = [];
  lines.forEach((line, index) => {
    if (!line.trim()) return;
    let row;
    try { row = JSON.parse(line); } catch { invalid.push({ line: index + 1, reason: 'json-parse-error' }); return; }
    const value = row?.[key];
    if (typeof value !== 'string' || !value) { invalid.push({ line: index + 1, reason: 'missing-key' }); return; }
    const entry = byKey.get(value) ?? [];
    entry.push({ line: index, row });
    byKey.set(value, entry);
  });
  return { byKey, invalid };
}

/**
 * @param {object} options
 * @param {string} options.manifestText
 * @param {Array<{path?: string, key?: string, expectSha256?: string, set?: object, unset?: string[]}>} options.updates
 * @param {string} [options.key]
 * @returns {{ok:boolean, conflicts:Array, operations:Array, changed:number, text:string}}
 */
export function planManifestPatch({ manifestText, updates = [], key = 'path' } = {}) {
  const { lines, hasFinalNewline } = parseLines(manifestText);
  const { byKey, invalid } = indexRows(lines, key);
  const conflicts = [...invalid.map((entry) => ({ ...entry, type: 'invalid-line' }))];
  const operations = [];
  const replacements = new Map();
  const changedKeys = new Set();

  for (const update of updates) {
    const targetKey = update?.key ?? update?.path;
    if (typeof targetKey !== 'string' || !targetKey) {
      conflicts.push({ type: 'missing-update-key', update });
      continue;
    }
    if (changedKeys.has(targetKey)) {
      conflicts.push({ type: 'duplicate-update', key: targetKey });
      continue;
    }
    changedKeys.add(targetKey);
    const entries = byKey.get(targetKey) ?? [];
    if (entries.length === 0) { conflicts.push({ type: 'key-not-found', key: targetKey }); continue; }
    if (entries.length > 1) { conflicts.push({ type: 'duplicate-key', key: targetKey, lines: entries.map((entry) => entry.line + 1) }); continue; }
    const [{ line, row }] = entries;
    if (update.expectSha256 && row.sha256 !== update.expectSha256) {
      conflicts.push({ type: 'sha-conflict', key: targetKey, expected: update.expectSha256, actual: row.sha256 ?? null });
      continue;
    }
    if (update.set && Object.prototype.hasOwnProperty.call(update.set, key)) {
      conflicts.push({ type: 'key-immutable', key: targetKey });
      continue;
    }
    const merged = { ...row };
    for (const [field, value] of Object.entries(update.set ?? {})) merged[field] = value;
    for (const field of update.unset ?? []) delete merged[field];
    const nextLine = JSON.stringify(merged);
    if (nextLine === lines[line]) {
      operations.push({ op: 'noop', key: targetKey, line: line + 1 });
      continue;
    }
    replacements.set(line, nextLine);
    operations.push({ op: 'update', key: targetKey, line: line + 1, beforeSha256: row.sha256 ?? null, afterSha256: merged.sha256 ?? null });
  }

  if (conflicts.length > 0) {
    return { ok: false, conflicts, operations, changed: 0, text: String(manifestText ?? '') };
  }
  const nextLines = lines.map((line, index) => (replacements.has(index) ? replacements.get(index) : line));
  const text = `${nextLines.join('\n')}${hasFinalNewline ? '\n' : ''}`;
  return {
    ok: true,
    conflicts: [],
    operations,
    changed: replacements.size,
    text,
  };
}

/** 原子应用；checkOnly=true 时不写盘。 */
export function applyManifestPatch({ manifestPath, updates, key = 'path', checkOnly = false }) {
  const beforeText = fs.readFileSync(manifestPath, 'utf8');
  const plan = planManifestPatch({ manifestText: beforeText, updates, key });
  if (!plan.ok) return { ...plan, written: false };
  if (checkOnly || plan.changed === 0) return { ...plan, written: false, unchanged: plan.changed === 0 };
  const temp = `${manifestPath}.tmp-${process.pid}`;
  fs.writeFileSync(temp, plan.text);
  fs.renameSync(temp, manifestPath);
  const afterText = fs.readFileSync(manifestPath, 'utf8');
  const beforeLines = beforeText.split('\n');
  const afterLines = afterText.split('\n');
  const untouched = beforeLines.every((line, index) => beforeLines.length !== afterLines.length
    ? false
    : (line === afterLines[index] || plan.operations.some((op) => op.op === 'update' && op.line === index + 1)));
  return { ...plan, written: true, untouched };
}

export { parseLines };
