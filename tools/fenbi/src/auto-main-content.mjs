#!/usr/bin/env node
/**
 * Opt-in automatic fast-forward of pure content to main.
 *
 * Disabled unless ALL of:
 *   - env AUTO_MAIN_CONTENT === '1'
 *   - a user settings file explicitly says {"allowAutoMain": true}
 *   - the diff relative to origin/main is pure content (content-gate.mjs)
 *   - every changed paper has a publication credential bound to sourceId + exact blob sha
 *     + an independent QA pass + a real rights basis (not "user chose A", not repo privacy)
 *   - origin/main still equals the expected sha (otherwise stop and recompute)
 *   - the push is a plain fast-forward (never --force)
 * Any missing/failed piece fails closed. The publisher service never calls this module.
 *
 * LIMITATION (B1): this driver only fast-forwards a branch that is already pure content
 * relative to origin/main. Automatically projecting audited per-paper content out of the
 * code+content integration branch is NOT implemented; the current integration branch cannot
 * use this driver.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { checkContent, readManifest } from './content-gate.mjs';

const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const RIGHTS_BASIS = new Set([
  'copyright-holder-license',
  'copyright-holder-written-permission',
  'official-public-release',
  'public-domain'
]);
const FORBIDDEN_BASIS = new Set(['user-self-authorization', 'private-repo-preference', 'user-chose-a']);

function git (repo, args, opts = {}) {
  return execFileSync('git', ['-C', repo, ...args], {encoding: 'utf8', ...opts}).trim();
}

export async function loadSettings (settingsPath) {
  if (!settingsPath) return {ok: false, reason: 'settings-path-missing'};
  try {
    const raw = JSON.parse(await fs.readFile(settingsPath, 'utf8'));
    return {ok: raw?.allowAutoMain === true, reason: raw?.allowAutoMain === true ? null : 'user-setting-not-enabled', settings: raw};
  } catch (e) { return {ok: false, reason: 'settings-unreadable:' + (e.code || e.message)}; }
}

export async function loadCredentials (credentialsPath) {
  if (!credentialsPath) return {ok: false, reason: 'credentials-missing', grants: []};
  let raw;
  try { raw = JSON.parse(await fs.readFile(credentialsPath, 'utf8')); } catch (e) { return {ok: false, reason: 'credentials-unreadable:' + (e.code || e.message), grants: []}; }
  if (raw?.schemaVersion !== 1 || !Array.isArray(raw?.grants)) return {ok: false, reason: 'credentials-schema-invalid', grants: []};
  return {ok: true, grants: raw.grants};
}

function grantFor (grants, paperPath) {
  return grants.filter(g => g?.paperPath === paperPath);
}

async function verifyTrustedFile (trustedRoot, relPath, expectedSha, label, file) {
  if (!trustedRoot) return [`trusted-root-missing:${file}`];
  if (typeof relPath !== 'string' || relPath.startsWith('/') || relPath.split(/[\\/]/u).includes('..')) {
    return [`${label}-path-invalid:${file}`];
  }
  let rootReal, real;
  try { rootReal = await fs.realpath(trustedRoot); } catch { return [`trusted-root-unreadable:${file}`]; }
  try { real = await fs.realpath(path.resolve(rootReal, relPath)); } catch { return [`${label}-unreadable:${file}`]; }
  if (!real.startsWith(rootReal + path.sep)) return [`${label}-escape:${file}`];
  const stat = await fs.lstat(real);
  if (stat.isSymbolicLink() || !stat.isFile()) return [`${label}-not-regular-file:${file}`];
  const bytes = await fs.readFile(real);
  if (sha(bytes) !== expectedSha) return [`${label}-sha-mismatch:${file}`];
  return [];
}

async function grantReasons (grant, {file, bytes, row, trustedRoot}) {
  const reasons = [];
  if (!row?.sourceId || grant.sourceId !== row.sourceId) reasons.push(`rights-sourceid-mismatch:${file}`);
  if (grant.blobSha256 !== sha(bytes)) reasons.push(`rights-blobsha-mismatch:${file}`);
  if (grant.qa?.verdict !== 'pass') reasons.push(`qa-not-passed:${file}`);
  if (typeof grant.qa?.reviewedAt !== 'string' || !grant.qa.reviewedAt) reasons.push(`qa-review-date-missing:${file}`);
  reasons.push(...await verifyTrustedFile(trustedRoot, grant.qa?.reportPath, grant.qa?.reportSha256, 'qa-report', file));
  const basis = grant.rights?.basis;
  if (FORBIDDEN_BASIS.has(basis)) reasons.push(`rights-basis-forbidden:${file}`);
  if (!RIGHTS_BASIS.has(basis)) reasons.push(`rights-basis-missing:${file}`);
  reasons.push(...await verifyTrustedFile(trustedRoot, grant.rights?.evidencePath, grant.rights?.evidenceSha256, 'rights-evidence', file));
  return reasons;
}

/** Check that every changed paper is covered by a valid, exactly-bound credential. */
export async function checkCredentials ({repo, grants, papers, trustedRoot = null}) {
  const reasons = [];
  const {rows} = await readManifest(repo);
  const byPath = new Map(rows.filter(r => typeof r?.path === 'string').map(r => [r.path, r]));
  for (const file of papers) {
    const bytes = await fs.readFile(`${repo}/${file}`);
    const row = byPath.get(file);
    const candidates = grantFor(grants, file);
    if (candidates.length === 0) { reasons.push(`rights-credential-missing:${file}`); continue; }
    if (candidates.length > 1) { reasons.push(`rights-credential-ambiguous:${file}`); continue; }
    reasons.push(...await grantReasons(candidates[0], {file, bytes, row, trustedRoot}));
    // Existing main content must not be silently overwritten by an unrelated patch.
    let mainSha = null;
    try { mainSha = git(repo, ['rev-parse', `origin/main:${file}`]); } catch { mainSha = null; }
    if (mainSha && candidates[0].baseBlobSha256 !== mainSha) reasons.push(`base-content-conflict:${file}`);
  }
  return [...new Set(reasons)];
}

/** Identify whether the source branch diff is pure content; never materialize code. */
export async function classifyCandidate ({repo, base = 'origin/main', source = 'HEAD'}) {
  const out = git(repo, ['-c', 'core.quotepath=false', 'diff', '--name-status', '--no-renames', `${base}...${source}`]);
  const changes = out.split('\n').filter(Boolean).map(line => {
    const tab = line.indexOf('\t');
    return {status: line.slice(0, tab), file: line.slice(tab + 1)};
  });
  const reasons = [];
  const content = [];
  for (const change of changes) {
    if (change.status !== 'A' && change.status !== 'M') reasons.push(`unsupported-change:${change.status}:${change.file}`);
    if (!/^(?:国考|省考|图片)\//u.test(change.file) && change.file !== 'catalog/manifest.jsonl') reasons.push(`non-content-path:${change.file}`);
    else if (change.status === 'A' || change.status === 'M') content.push(change);
  }
  return {ok: reasons.length === 0 && changes.length > 0, content, reasons};
}

export async function autoMerge ({repo, expectedMainSha, credentialsPath, settingsPath, trustedRoot = null, apply = false, env = process.env}) {
  const base = 'origin/main';
  const reasons = [];
  if (env.AUTO_MAIN_CONTENT !== '1') return {ok: false, stage: 'disabled', reasons: ['auto-main-disabled']};
  const settings = await loadSettings(settingsPath);
  if (!settings.ok) return {ok: false, stage: 'settings', reasons: [settings.reason]};
  const credentials = await loadCredentials(credentialsPath);
  if (!credentials.ok) return {ok: false, stage: 'rights', reasons: [credentials.reason]};
  let remoteSha;
  try {
    git(repo, ['fetch', '-q', 'origin', 'main:refs/remotes/origin/main']);
    remoteSha = git(repo, ['rev-parse', 'refs/remotes/origin/main']);
  } catch (e) { return {ok: false, stage: 'remote', reasons: ['origin-main-unreadable:' + (e.code || e.message)]}; }
  if (!expectedMainSha || remoteSha !== expectedMainSha) return {ok: false, stage: 'race', reasons: ['main-moved']};
  const candidate = await classifyCandidate({repo, base});
  if (!candidate.ok) return {ok: false, stage: 'gate', reasons: candidate.reasons};
  const gate = await checkContent({repo, base});
  if (!gate.ok) return {ok: false, stage: 'gate', reasons: gate.reasons};
  const paperPaths = candidate.content.filter(c => /\.md$/u.test(c.file)).map(c => c.file);
  const rights = await checkCredentials({repo, grants: credentials.grants, papers: paperPaths, trustedRoot});
  if (rights.length) return {ok: false, stage: 'rights', reasons: rights};
  let ff;
  try { git(repo, ['merge-base', '--is-ancestor', base, 'HEAD']); ff = true; } catch { ff = false; }
  if (!ff) return {ok: false, stage: 'fast-forward', reasons: ['not-fast-forward']};
  if (!apply) return {ok: true, stage: 'dry-run', wouldPush: true, changedFiles: gate.changedFiles, papers: gate.papers};
  try { git(repo, ['push', 'origin', 'HEAD:refs/heads/main']); } catch (e) { return {ok: false, stage: 'push', reasons: ['push-rejected:' + (e.stderr?.toString().split('\n')[0] || e.message)]}; }
  const after = execFileSync('git', ['-C', repo, 'ls-remote', 'origin', 'refs/heads/main'], {encoding: 'utf8'}).split(/\s+/u)[0];
  const head = git(repo, ['rev-parse', 'HEAD']);
  if (after !== head) return {ok: false, stage: 'verify', reasons: ['push-not-confirmed']};
  return {ok: true, stage: 'pushed', mainSha: after};
}

export const __test = {sha, RIGHTS_BASIS, FORBIDDEN_BASIS};
