#!/usr/bin/env node
/**
 * Content-only projection: copy a small, explicitly allowlisted set of audited papers
 * from a mixed integration branch onto a fresh origin/main commit.
 *
 * The projection never checks out or copies the source branch tree. It reads only the
 * allowlisted paper blobs, their referenced in-repo images, and the manifest rows for
 * those papers, then builds a new tree on top of origin/main with git plumbing.
 *
 * Fail closed on:
 *  - missing / forged QA or rights evidence (trusted root, real file, sha256 bytes);
 *  - missing sourceId or blob sha binding;
 *  - duplicate sourceId or duplicate area/year/subject/variant among the selection;
 *  - a path already on main whose blob differs from the credential's baseBlobSha256;
 *  - symlinked, escaping, external or cross-directory images;
 *  - any non-content path in the projected tree;
 *  - origin/main moving away from expectedMainSha;
 *  - zero eligible papers (no empty commit is ever created).
 *
 * `apply: true` only writes a local ref. Pushing is left to auto-main-content.mjs and is
 * itself disabled unless AUTO_MAIN_CONTENT=1 and the user settings allow it.
 */
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { parsePaperMarkdown } from './content-gate.mjs';
import { loadCredentials, verifyTrustedFile } from './auto-main-content.mjs';

const CONTENT = /^(?:国考|省考|图片)\//u;
const MANIFEST = 'catalog/manifest.jsonl';
const PAPER = /^(?:国考|省考)\/.+\.md$/u;
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function git (repo, args, opts = {}) {
  return execFileSync('git', ['-C', repo, ...args], {encoding: opts.encoding ?? 'utf8', ...opts});
}

function blobInfo (repo, ref, file) {
  let out;
  try { out = git(repo, ['ls-tree', ref, '--', file]); } catch { return null; }
  if (!out) return null;
  const [meta] = out.split('\n');
  const [mode, type, oid] = meta.split(/\s+/u);
  return {mode, type, oid};
}

function readBlob (repo, ref, file) {
  return execFileSync('git', ['-C', repo, 'cat-file', 'blob', `${ref}:${file}`], {encoding: null});
}

function writeBlob (repo, bytes) {
  return git(repo, ['hash-object', '-w', '--stdin'], {input: bytes, encoding: 'utf8'}).trim();
}

function parseRows (text) {
  return text.split(/\r?\n/u).filter(Boolean).map((line, i) => {
    try { return JSON.parse(line); } catch { throw Object.assign(new Error(`manifest-unparsable:${i + 1}`), {code: 'manifest-unparsable'}); }
  });
}

/** Validate one allowlisted paper and return the parts needed for projection. */
async function inspectPaper ({sourceRepo, sourceHead, paperPath, grant, trustedRoot, mainBlobSha}) {
  const reasons = [];
  if (!PAPER.test(paperPath) || paperPath.split('/').includes('..')) return {reasons: ['paper-path-invalid:' + paperPath]};
  const info = blobInfo(sourceRepo, sourceHead, paperPath);
  if (!info) return {reasons: ['paper-missing-in-source:' + paperPath]};
  if (info.mode === '120000') return {reasons: ['paper-is-symlink:' + paperPath]};
  if (info.type !== 'blob' || !/^100644$|^100755$/u.test(info.mode)) return {reasons: ['paper-not-regular-file:' + paperPath]};
  if (!grant) return {reasons: ['rights-credential-missing:' + paperPath]};
  const bytes = readBlob(sourceRepo, sourceHead, paperPath);
  const blobSha = sha(bytes);
  if (grant.paperPath !== paperPath) reasons.push('rights-path-mismatch:' + paperPath);
  if (grant.blobSha256 !== blobSha) reasons.push('rights-blobsha-mismatch:' + paperPath);
  if (grant.qa?.verdict !== 'pass') reasons.push('qa-not-passed:' + paperPath);
  if (typeof grant.qa?.reviewedAt !== 'string' || !grant.qa.reviewedAt) reasons.push('qa-review-date-missing:' + paperPath);
  reasons.push(...await verifyTrustedFile(trustedRoot, grant.qa?.reportPath, grant.qa?.reportSha256, 'qa-report', paperPath));
  const basis = grant.rights?.basis;
  if (['user-self-authorization', 'private-repo-preference', 'user-chose-a'].includes(basis)) reasons.push('rights-basis-forbidden:' + paperPath);
  if (!['copyright-holder-license', 'copyright-holder-written-permission', 'official-public-release', 'public-domain'].includes(basis)) reasons.push('rights-basis-missing:' + paperPath);
  reasons.push(...await verifyTrustedFile(trustedRoot, grant.rights?.evidencePath, grant.rights?.evidenceSha256, 'rights-evidence', paperPath));
  if (mainBlobSha && grant.baseBlobSha256 !== mainBlobSha) reasons.push('base-content-conflict:' + paperPath);
  const parsed = parsePaperMarkdown(bytes.toString('utf8'), {isXingce: /行测/u.test(paperPath), row: {}});
  reasons.push(...parsed.reasons.map(r => `${r}:${paperPath}`));
  return {reasons, info, bytes, blobSha, parsed};
}

async function collectAssets ({sourceRepo, sourceHead, paperPath, md}) {
  const reasons = [], assets = [];
  const paperDir = path.posix.dirname(paperPath);
  const re = /!\[[^\]]*\]\(([^)\s]+)\)|<img\b[^>]*\bsrc=["']([^"']+)["']/giu;
  for (const m of md.matchAll(re)) {
    let ref;
    try { ref = decodeURIComponent(m[1] || m[2]); } catch { reasons.push('image-ref-invalid:' + paperPath); continue; }
    if (/^[a-z][a-z0-9+.-]*:/iu.test(ref) || ref.startsWith('//') || ref.startsWith('/') || ref.split(/[\\/]/u).includes('..')) {
      reasons.push('image-external-or-absolute:' + paperPath); continue;
    }
    const resolved = path.posix.normalize(path.posix.join(paperDir, ref));
    const inPaperDir = resolved.startsWith(paperDir + '/');
    const inImageRoot = resolved.startsWith('图片/');
    if (!inPaperDir && !inImageRoot) { reasons.push('image-cross-directory:' + paperPath); continue; }
    if (!CONTENT.test(resolved)) { reasons.push('image-non-content:' + paperPath); continue; }
    const info = blobInfo(sourceRepo, sourceHead, resolved);
    if (!info) { reasons.push('missing-image:' + paperPath + ':' + ref); continue; }
    if (info.mode === '120000') { reasons.push('image-is-symlink:' + resolved); continue; }
    if (info.type !== 'blob') { reasons.push('image-not-blob:' + resolved); continue; }
    const bytes = readBlob(sourceRepo, sourceHead, resolved);
    assets.push({path: resolved, bytes, oid: info.oid});
  }
  return {reasons, assets};
}

/**
 * Build a content-only commit on top of origin/main from allowlisted papers.
 * Returns {ok, eligible, rejected, commit, files, reasons}. Writes nothing unless apply.
 */
export async function buildProjection ({
  repo, sourceRepo = repo, sourceHead, expectedMainSha,
  papers = [], credentialsPath, trustedRoot, apply = false, env = process.env
}) {
  const reasons = [];
  const rejected = [];
  if (env.AUTO_MAIN_CONTENT !== '1') return {ok: false, stage: 'disabled', reasons: ['auto-main-disabled'], eligible: 0, rejected};
  if (!Array.isArray(papers) || papers.length === 0) return {ok: false, stage: 'selection', reasons: ['no-allowlisted-papers'], eligible: 0, rejected};
  try { git(repo, ['fetch', '-q', 'origin', 'main:refs/remotes/origin/main']); } catch (e) { return {ok: false, stage: 'remote', reasons: ['origin-main-unreadable:' + (e.code || e.message)], eligible: 0, rejected}; }
  let mainSha;
  try { mainSha = git(repo, ['rev-parse', 'refs/remotes/origin/main']).trim(); } catch { return {ok: false, stage: 'remote', reasons: ['origin-main-missing'], eligible: 0, rejected}; }
  if (!expectedMainSha || mainSha !== expectedMainSha) return {ok: false, stage: 'race', reasons: ['main-moved'], eligible: 0, rejected};
  if (sourceHead && /\s|\.\./u.test(sourceHead)) return {ok: false, stage: 'source', reasons: ['source-head-invalid'], eligible: 0, rejected};
  try { git(sourceRepo, ['rev-parse', '--verify', `${sourceHead}^{commit}`]); } catch { return {ok: false, stage: 'source', reasons: ['source-head-missing'], eligible: 0, rejected}; }
  const credentials = await loadCredentials(credentialsPath);
  if (!credentials.ok) return {ok: false, stage: 'rights', reasons: [credentials.reason], eligible: 0, rejected};

  const sourceManifestText = (() => {
    try { return readBlob(sourceRepo, sourceHead, MANIFEST).toString('utf8'); } catch { return ''; }
  })();
  const sourceRows = sourceManifestText ? parseRows(sourceManifestText) : [];
  const sourceRowByPath = new Map(sourceRows.filter(r => typeof r?.path === 'string').map(r => [r.path, r]));
  let mainRows = [];
  try { mainRows = parseRows(readBlob(repo, mainSha, MANIFEST).toString('utf8')); } catch { mainRows = []; }
  const mainRowByPath = new Map(mainRows.filter(r => typeof r?.path === 'string').map(r => [r.path, r]));

  const seenIdentity = new Map(), seenSourceId = new Map();
  const eligible = [], assetsByPath = new Map();
  for (const entry of papers) {
    const paperPath = typeof entry === 'string' ? entry : entry?.path;
    if (!paperPath) { rejected.push({path: null, reasons: ['paper-path-missing']}); continue; }
    const grant = credentials.grants.find(g => g?.paperPath === paperPath);
    const mainInfo = blobInfo(repo, mainSha, paperPath);
    const mainBlobSha = mainInfo && mainInfo.type === 'blob' ? mainInfo.oid : null;
    let inspected;
    try { inspected = await inspectPaper({sourceRepo, sourceHead, paperPath, grant, trustedRoot, mainBlobSha}); }
    catch (e) { rejected.push({path: paperPath, reasons: ['inspect-failed:' + (e.code || e.message)]}); continue; }
    if (inspected.reasons.length) { rejected.push({path: paperPath, reasons: inspected.reasons}); continue; }

    const row = sourceRowByPath.get(paperPath);
    if (!row?.sourceId) { rejected.push({path: paperPath, reasons: ['manifest-row-missing-or-no-sourceid']}); continue; }
    if (row.sourceId !== grant.sourceId) { rejected.push({path: paperPath, reasons: ['rights-sourceid-mismatch']}); continue; }
    if (row.sha256 !== inspected.blobSha || row.bytes !== inspected.bytes.length) {
      rejected.push({path: paperPath, reasons: ['manifest-sha256-or-bytes-mismatch']}); continue;
    }
    const identity = [row.area, row.year, row.subject, row.variant ?? row.paper_type].join('\u0000');
    const identityKey = identity + '\u0000' + row.sourceId;
    if (seenIdentity.has(identity)) rejected.push({path: paperPath, reasons: ['duplicate-paper-identity:' + seenIdentity.get(identity)]});
    if (seenSourceId.has(row.sourceId)) rejected.push({path: paperPath, reasons: ['duplicate-source-id:' + seenSourceId.get(row.sourceId)]});
    if (seenIdentity.has(identity) || seenSourceId.has(row.sourceId)) continue;
    seenIdentity.set(identity, paperPath); seenSourceId.set(row.sourceId, paperPath);

    const collected = await collectAssets({sourceRepo, sourceHead, paperPath, md: inspected.bytes.toString('utf8')});
    if (collected.reasons.length) { rejected.push({path: paperPath, reasons: collected.reasons}); continue; }
    for (const asset of collected.assets) assetsByPath.set(asset.path, asset);
    eligible.push({path: paperPath, row, bytes: inspected.bytes, blobSha: inspected.blobSha, grant, mainBlobSha});
  }

  const duplicates = rejected.filter(r => r.reasons.some(x => x.startsWith('duplicate-')));
  if (duplicates.length) {
    return {ok: false, stage: 'conflict', reasons: ['duplicate-selection'], eligible: 0, rejected};
  }
  if (eligible.length === 0) return {ok: false, stage: 'selection', reasons: ['no-eligible-papers'], eligible: 0, rejected};

  // Existing main content may only be replaced with an explicit base blob binding.
  for (const item of eligible) {
    if (item.mainBlobSha && item.grant.baseBlobSha256 !== item.mainBlobSha) {
      rejected.push({path: item.path, reasons: ['base-content-conflict']});
    }
  }
  const blocked = new Set(rejected.map(r => r.path));
  const finalEligible = eligible.filter(item => !blocked.has(item.path));
  if (finalEligible.length === 0) return {ok: false, stage: 'conflict', reasons: ['no-eligible-papers-after-conflicts'], eligible: 0, rejected};

  // Merge manifest: keep all main rows; replace only the selected paths.
  const projectedRows = new Map();
  for (const item of finalEligible) {
    const row = {...item.row, path: item.path, sha256: item.blobSha, bytes: item.bytes.length};
    projectedRows.set(item.path, row);
  }
  const mergedRows = [];
  const emitted = new Set();
  for (const row of mainRows) {
    if (typeof row?.path === 'string' && projectedRows.has(row.path)) {
      mergedRows.push(projectedRows.get(row.path)); emitted.add(row.path);
    } else mergedRows.push(row);
  }
  for (const [p, row] of projectedRows) if (!emitted.has(p)) mergedRows.push(row);
  const manifestBytes = Buffer.from(mergedRows.map(r => JSON.stringify(r)).join('\n') + '\n');
  for (const row of mergedRows) {
    if (typeof row?.path !== 'string' || (!CONTENT.test(row.path) && row.path !== MANIFEST)) {
      return {ok: false, stage: 'manifest', reasons: ['manifest-non-content-row:' + row?.path], eligible: 0, rejected};
    }
  }

  const files = new Map();
  for (const item of finalEligible) files.set(item.path, item.bytes);
  for (const [assetPath, asset] of assetsByPath) files.set(assetPath, asset.bytes);
  files.set(MANIFEST, manifestBytes);
  for (const file of files.keys()) {
    if (file !== MANIFEST && !CONTENT.test(file)) {
      return {ok: false, stage: 'projection', reasons: ['non-content-projection-path:' + file], eligible: 0, rejected};
    }
  }

  // Build an isolated index and commit; never touch the caller's index or worktree.
  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'content-project-'));
  const indexFile = path.join(tmp, 'index');
  const envWithIndex = {...process.env, GIT_INDEX_FILE: indexFile};
  try {
    git(repo, ['read-tree', mainSha], {env: envWithIndex});
    for (const [file, bytes] of files) {
      const oid = writeBlob(repo, bytes);
      git(repo, ['update-index', '--add', '--cacheinfo', `100644,${oid},${file}`], {env: envWithIndex});
    }
    const tree = git(repo, ['write-tree'], {env: envWithIndex}).trim();
    const baseTree = git(repo, ['rev-parse', `${mainSha}^{tree}`]).trim();
    if (tree === baseTree) return {ok: false, stage: 'projection', reasons: ['empty-projection'], eligible: 0, rejected};
    const commit = git(repo, ['commit-tree', tree, '-p', mainSha, '-m', 'project(fenbi): audited content-only projection'], {env: envWithIndex}).trim();
    if (apply) git(repo, ['update-ref', 'refs/heads/s3/content-projection', commit]);
    return {
      ok: true, stage: apply ? 'committed' : 'dry-run', base: mainSha, commit,
      eligible: finalEligible.length, papers: finalEligible.map(x => x.path),
      files: [...files.keys()].sort(), rejected
    };
  } finally {
    await fs.rm(tmp, {recursive: true, force: true});
  }
}
