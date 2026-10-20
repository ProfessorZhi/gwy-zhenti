#!/usr/bin/env node
/**
 * Opt-in scheduler for content-only auto-main.
 *
 * Default OFF. Runs only when AUTO_MAIN_CONTENT=1 and a user settings file says
 * {"allowAutoMain": true}. The allowlist is derived from a trusted QA+rights credential
 * file (one grant per paper); every grant must carry sourceId, exact blob sha, an
 * independent QA report path and a rights evidence path under trustedRoot.
 *
 * Projection is built from a fixed 40-hex integration commit into an isolated temporary
 * worktree based on origin/main; the running integration worktree is never checked out.
 * Pushing to main happens only through autoMerge, which itself requires the same env and
 * settings and a plain fast-forward. No --force is ever used.
 *
 * A credential field is evidence of a claim, not proof of legality; the caller is
 * responsible for the rights holder verification behind the evidence file.
 */
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { buildProjection } from './content-project.mjs';
import { autoMerge, loadCredentials, loadSettings } from './auto-main-content.mjs';

const SHA = /^[0-9a-f]{40}$/u;

function git (repo, args, opts = {}) {
  return execFileSync('git', ['-C', repo, ...args], {encoding: 'utf8', ...opts}).trim();
}

export function credentialPaperPaths (credentials) {
  return credentials.grants
    .filter(g => typeof g?.paperPath === 'string' && /^[0-9a-f]{64}$/u.test(g?.blobSha256 || '') &&
      typeof g?.sourceId === 'string' && g.sourceId)
    .map(g => g.paperPath);
}

/**
 * Run one scheduling cycle.
 * @param {object} opts
 * @param {string} opts.repo       staging repo with origin pointing at the real remote
 * @param {string} opts.sourceRepo read-only access to the integration repo
 * @param {string} opts.sourceRef  branch/tag to pin (resolved to an exact sha first)
 * @param {string} [opts.expectedMainSha] optional assertion of the remote main sha
 * @param {boolean} [opts.apply]   push on success; default false
 */
export async function runAutoMain ({
  repo, sourceRepo = repo, sourceRef = 'integ/2026-10-19', expectedMainSha = null,
  settingsPath, credentialsPath, trustedRoot, apply = false, env = process.env
}) {
  if (env.AUTO_MAIN_CONTENT !== '1') return {ok: false, stage: 'disabled', reasons: ['auto-main-disabled']};
  const settings = await loadSettings(settingsPath);
  if (!settings.ok) return {ok: false, stage: 'settings', reasons: [settings.reason]};
  const credentials = await loadCredentials(credentialsPath);
  if (!credentials.ok) return {ok: false, stage: 'rights', reasons: [credentials.reason]};
  const papers = credentialPaperPaths({grants: credentials.grants});
  if (papers.length === 0) return {ok: false, stage: 'selection', reasons: ['no-credentialed-papers'], eligible: 0};

  let sourceHead;
  try { sourceHead = git(sourceRepo, ['rev-parse', '--verify', `${sourceRef}^{commit}`]); } catch { return {ok: false, stage: 'source', reasons: ['source-ref-missing']}; }
  if (!SHA.test(sourceHead)) return {ok: false, stage: 'source', reasons: ['source-head-not-pinned-sha']};

  let remoteMain;
  try { remoteMain = execFileSync('git', ['-C', repo, 'ls-remote', 'origin', 'refs/heads/main'], {encoding: 'utf8'}).split(/\s+/u)[0]; }
  catch (e) { return {ok: false, stage: 'remote', reasons: ['origin-main-unreadable:' + (e.code || e.message)]}; }
  if (!SHA.test(remoteMain || '')) return {ok: false, stage: 'remote', reasons: ['origin-main-sha-invalid']};
  // A caller-supplied main pin is an assertion, never an override.
  if (expectedMainSha && expectedMainSha !== remoteMain) return {ok: false, stage: 'race', reasons: ['main-moved']};
  const mainSha = remoteMain;

  if (!apply) {
    const plan = await buildProjection({
      repo, sourceRepo, sourceHead, expectedMainSha: mainSha, papers,
      credentialsPath, trustedRoot, apply: false, env
    });
    return {...plan, allowedToPush: false, mainSha};
  }

  // Isolated worktree based on origin/main; the integration worktree is never checked out.
  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'auto-main-wt-'));
  let added = false;
  try {
    git(repo, ['worktree', 'add', '-q', '--detach', tmp, remoteMain]);
    added = true;
    const projection = await buildProjection({
      repo: tmp, sourceRepo, sourceHead, expectedMainSha: remoteMain, papers,
      credentialsPath, trustedRoot, apply: true, env
    });
    if (!projection.ok) return {...projection, mainSha};
    git(tmp, ['checkout', '-q', '--detach', projection.commit]);
    const merged = await autoMerge({
      repo: tmp, expectedMainSha: remoteMain, credentialsPath, settingsPath, trustedRoot,
      apply: true, env
    });
    return {...merged, projectionCommit: projection.commit, papers: projection.papers, mainShaBefore: remoteMain};
  } finally {
    if (added) git(repo, ['worktree', 'remove', '--force', tmp]);
    await fs.rm(tmp, {recursive: true, force: true});
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  const args = process.argv.slice(2);
  const opts = {apply: false};
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (key === '--apply') opts.apply = true;
    else if (['--repo', '--source-repo', '--source-ref', '--expected-main-sha', '--settings', '--credentials', '--trusted-root'].includes(key)) {
      const value = args[++i];
      if (!value) { console.error('missing-value:' + key); process.exit(1); }
      opts[key.slice(2).replaceAll('-', '_')] = value;
    } else { console.error('unknown-option:' + key); process.exit(1); }
  }
  if (!opts.repo) { console.error('usage: auto-main-run.mjs --repo DIR --settings FILE --credentials FILE --trusted-root DIR [--source-ref REF] [--apply]'); process.exitCode = 1; }
  else runAutoMain({
    repo: opts.repo, sourceRepo: opts.source_repo || opts.repo, sourceRef: opts.source_ref || 'integ/2026-10-19',
    expectedMainSha: opts.expected_main_sha || null, settingsPath: opts.settings, credentialsPath: opts.credentials,
    trustedRoot: opts.trusted_root, apply: opts.apply
  }).then(r => { console.log(JSON.stringify(r)); if (!r.ok) process.exitCode = 3; })
    .catch(e => { console.error(e.code || e.message); process.exitCode = 1; });
}
