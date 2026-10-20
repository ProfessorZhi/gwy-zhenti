#!/usr/bin/env node
/**
 * Content-only projection: copy a small, explicitly allowlisted set of audited papers
 * from a fixed integration commit onto a fresh origin/main commit.
 *
 * Reads only the allowlisted paper blobs, their referenced in-repo images and the
 * manifest rows for those papers, then builds a new tree on top of origin/main with
 * git plumbing. It never checks out or copies the source tree.
 *
 * Fail closed on:
 *  - missing / forged QA or rights evidence (trusted root, real file, sha256 bytes);
 *  - missing sourceId or blob sha binding, or manifest counts not matching the paper;
 *  - duplicate sourceId or duplicate area/year/subject/variant within the selection;
 *  - a path already on main whose blob differs from the credential's baseBlobSha256;
 *  - symlinked, escaping, external or cross-directory images;
 *  - non-content paths, unreadable main manifest, origin/main race, zero eligible papers.
 *
 * dry-run (apply=false) reads and validates only; it writes no Git objects and no refs.
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
const SHA = /^[0-9a-f]{40}$/u;
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

async function inspectPaper ({sourceRepo, sourceHead, paperPath, grant, trustedRoot, mainBlobSha, sourceRow}) {
  const reasons = [];
  if (!PAPER.test(paperPath) || paperPath.split('/').includes('..')) return {reasons: ['paper-path-invalid:' + paperPath]};
  const info = blobInfo(sourceRepo, sourceHead, paperPath);
  if (!info) return {reasons: ['paper-missing-in-source:' + paperPath]};
  if (info.mode === '120000') return {reasons: ['paper-is-symlink:' + paperPath]};
  if (info.type !== 'blob' || !/^100644$|^100755$/u.test(info.mode)) return {reasons: ['paper-not-regular-file:' + paperPath]};
  if (!grant) return {reasons: ['rights-credential-missing:' + paperPath]};
  if (!sourceRow) return {reasons: ['manifest-row-missing:' + paperPath]};
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
  // Manifest counts are part of the evidence: a mismatch rejects the paper.
  const parsed = parsePaperMarkdown(bytes.toString('utf8'), {isXingce: /行测/u.test(paperPath), row: sourceRow});
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
 * Returns {ok, eligible, rejected, commit, files, reasons}. dry-run writes nothing.
 */
export async function buildProjection ({
  repo, sourceRepo = repo, sourceHead, expectedMainSha,
  papers = [], credentialsPath, trustedRoot, apply = false, env = process.env
}) {
  const rejected = [];
  if (env.AUTO_MAIN_CONTENT !== '1') return {ok: false, stage: 'disabled', reasons: ['auto-main-disabled'], eligible: 0, rejected};
  if (typeof sourceHead !== 'string' || !SHA.test(sourceHead)) return {ok: false, stage: 'source', reasons: ['source-head-not-pinned-sha'], eligible: 0, rejected};
  if (!Array.isArray(papers) || papers.length === 0) return {ok: false, stage: 'selection', reasons: ['no-allowlisted-papers'], eligible: 0, rejected};
  try { git(repo, ['fetch', '-q', 'origin', 'main:refs/remotes/origin/main']); } catch (e) { return {ok: false, stage: 'remote', reasons: ['origin-main-unreadable:' + (e.code || e.message)], eligible: 0, rejected}; }
  let mainSha;
  try { mainSha = git(repo, ['rev-parse', 'refs/remotes/origin/main']).trim(); } catch { return {ok: false, stage: 'remote', reasons: ['origin-main-missing'], eligible: 0, rejected}; }
  if (!expectedMainSha || mainSha !== expectedMainSha) return {ok: false, stage: 'race', reasons: ['main-moved'], eligible: 0, rejected};
  // The source must be the exact commit the caller pinned, not a moving branch name.
  let resolvedSource;
  try { resolvedSource = git(sourceRepo, ['rev-parse', '--verify', `${sourceHead}^{commit}`]).trim(); } catch { return {ok: false, stage: 'source', reasons: ['source-head-missing'], eligible: 0, rejected}; }
  if (resolvedSource !== sourceHead) return {ok: false, stage: 'source', reasons: ['source-head-not-exact'], eligible: 0, rejected};
  const credentials = await loadCredentials(credentialsPath);
  if (!credentials.ok) return {ok: false, stage: 'rights', reasons: [credentials.reason], eligible: 0, rejected};

  let sourceRows = [];
  try { sourceRows = parseRows(readBlob(sourceRepo, sourceHead, MANIFEST).toString('utf8')); }
  catch (e) { return {ok: false, stage: 'manifest', reasons: ['source-manifest-unreadable:' + (e.code || e.message)], eligible: 0, rejected}; }
  const sourceRowByPath = new Map(sourceRows.filter(r => typeof r?.path === 'string').map(r => [r.path, r]));

  // An absent main manifest is allowed as an explicit empty base; an unreadable/corrupt one is not.
  let mainRows = [];
  const mainManifestInfo = blobInfo(repo, mainSha, MANIFEST);
  if (mainManifestInfo) {
    try { mainRows = parseRows(readBlob(repo, mainSha, MANIFEST).toString('utf8')); }
    catch (e) { return {ok: false, stage: 'manifest', reasons: ['main-manifest-unreadable:' + (e.code || e.message)], eligible: 0, rejected}; }
  }

  const seenIdentity = new Map(), seenSourceId = new Map();
  let eligible = [];
  for (const entry of papers) {
    const paperPath = typeof entry === 'string' ? entry : entry?.path;
    if (!paperPath) { rejected.push({path: null, reasons: ['paper-path-missing']}); continue; }
    const grant = credentials.grants.find(g => g?.paperPath === paperPath);
    const mainInfo = blobInfo(repo, mainSha, paperPath);
    const mainBlobSha = mainInfo && mainInfo.type === 'blob' ? mainInfo.oid : null;
    const sourceRow = sourceRowByPath.get(paperPath);
    let inspected;
    try { inspected = await inspectPaper({sourceRepo, sourceHead, paperPath, grant, trustedRoot, mainBlobSha, sourceRow}); }
    catch (e) { rejected.push({path: paperPath, reasons: ['inspect-failed:' + (e.code || e.message)]}); continue; }
    if (inspected.reasons.length) { rejected.push({path: paperPath, reasons: inspected.reasons}); continue; }
    const row = sourceRow;
    if (!row.sourceId) { rejected.push({path: paperPath, reasons: ['manifest-row-no-sourceid']}); continue; }
    if (row.sourceId !== grant.sourceId) { rejected.push({path: paperPath, reasons: ['rights-sourceid-mismatch']}); continue; }
    if (row.sha256 !== inspected.blobSha || row.bytes !== inspected.bytes.length) {
      rejected.push({path: paperPath, reasons: ['manifest-sha256-or-bytes-mismatch']}); continue;
    }
    const identity = [row.area, row.year, row.subject, row.variant ?? row.paper_type].join('\u0000');
    if (seenIdentity.has(identity)) { rejected.push({path: paperPath, reasons: ['duplicate-paper-identity:' + seenIdentity.get(identity)]}); continue; }
    if (seenSourceId.has(row.sourceId)) { rejected.push({path: paperPath, reasons: ['duplicate-source-id:' + seenSourceId.get(row.sourceId)]}); continue; }
    seenIdentity.set(identity, paperPath); seenSourceId.set(row.sourceId, paperPath);
    const collected = await collectAssets({sourceRepo, sourceHead, paperPath, md: inspected.bytes.toString('utf8')});
    if (collected.reasons.length) { rejected.push({path: paperPath, reasons: collected.reasons}); continue; }
    eligible.push({path: paperPath, row, bytes: inspected.bytes, blobSha: inspected.blobSha, grant, mainBlobSha, assets: collected.assets});
  }

  if (rejected.some(r => r.reasons.some(x => x.startsWith('duplicate-')))) {
    return {ok: false, stage: 'conflict', reasons: ['duplicate-selection'], eligible: 0, rejected};
  }
  if (eligible.length === 0) return {ok: false, stage: 'selection', reasons: ['no-eligible-papers'], eligible: 0, rejected};

  // Drop anything that would overwrite existing main content without an explicit base blob.
  eligible = eligible.filter(item => {
    if (item.mainBlobSha && item.grant.baseBlobSha256 !== item.mainBlobSha) {
      rejected.push({path: item.path, reasons: ['base-content-conflict']});
      return false;
    }
    return true;
  });
  if (eligible.length === 0) return {ok: false, stage: 'conflict', reasons: ['no-eligible-papers-after-conflicts'], eligible: 0, rejected};

  // Assets are collected only from papers that survived conflict filtering.
  const assetsByPath = new Map();
  for (const item of eligible) {
    for (const asset of item.assets) {
      const prior = assetsByPath.get(asset.path);
      if (prior && prior.oid !== asset.oid) {
        return {ok: false, stage: 'conflict', reasons: ['asset-conflict:' + asset.path], eligible: 0, rejected};
      }
      assetsByPath.set(asset.path, asset);
    }
  }

  const projectedRows = new Map();
  for (const item of eligible) {
    projectedRows.set(item.path, {...item.row, path: item.path, sha256: item.blobSha, bytes: item.bytes.length});
  }
  const mergedRows = [];
  const emitted = new Set();
  for (const row of mainRows) {
    if (typeof row?.path === 'string' && projectedRows.has(row.path)) {
      mergedRows.push(projectedRows.get(row.path)); emitted.add(row.path);
    } else mergedRows.push(row);
  }
  for (const [p, row] of projectedRows) if (!emitted.has(p)) mergedRows.push(row);
  for (const row of mergedRows) {
    if (typeof row?.path !== 'string' || (!CONTENT.test(row.path) && row.path !== MANIFEST)) {
      return {ok: false, stage: 'manifest', reasons: ['manifest-non-content-row:' + row?.path], eligible: 0, rejected};
    }
  }
  const manifestBytes = Buffer.from(mergedRows.map(r => JSON.stringify(r)).join('\n') + '\n');

  const files = new Map();
  for (const item of eligible) files.set(item.path, item.bytes);
  for (const [assetPath, asset] of assetsByPath) files.set(assetPath, asset.bytes);
  files.set(MANIFEST, manifestBytes);
  for (const file of files.keys()) {
    if (file !== MANIFEST && !CONTENT.test(file)) {
      return {ok: false, stage: 'projection', reasons: ['non-content-projection-path:' + file], eligible: 0, rejected};
    }
  }

  const summary = {
    base: mainSha, eligible: eligible.length, papers: eligible.map(x => x.path),
    files: [...files.keys()].sort(), rejected
  };
  // dry-run: no objects, no refs, no commit.
  if (!apply) return {ok: true, stage: 'dry-run', ...summary};

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
    // Per-commit ref with a zero-old-value CAS; never clobber another batch's ref.
    const ref = `refs/heads/s3/content-projection-${commit.slice(0, 12)}`;
    try { git(repo, ['update-ref', ref, commit, '0'.repeat(40)]); }
    catch { return {ok: false, stage: 'ref', reasons: ['projection-ref-exists'], eligible: 0, rejected}; }
    return {ok: true, stage: 'committed', commit, ref, ...summary};
  } finally {
    await fs.rm(tmp, {recursive: true, force: true});
  }
}
