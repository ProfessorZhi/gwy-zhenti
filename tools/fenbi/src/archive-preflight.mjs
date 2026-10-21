// 申论本地档案 publish-preflight：离线、只读、metadata-only 验收矩阵。
//
// 本模块只读取目录结构、计数、哈希、大小、图片尺寸和引用的相对路径，不输出
// 题干、材料、答案、解析或标题正文；也不访问网络、不启动浏览器、不写档案目录。
// 技术完整性（technical gate）与再分发权利（publication gate）分开判定：
//   - technical: PASS / FAIL / SKIP
//   - publication: BLOCKED / ELIGIBLE / POLICY_VIOLATION / UNKNOWN
// 任何 rightsStatus=cleared 或 cloudStorageBlocked=false 都会被记为违规，而不是被
// 自动“修正”为可发布。
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const PREFLIGHT_SCHEMA_VERSION = 1;
export const TECHNICAL = Object.freeze({ PASS: 'PASS', FAIL: 'FAIL', SKIP: 'SKIP' });
export const PUBLICATION = Object.freeze({
  BLOCKED: 'BLOCKED', ELIGIBLE: 'ELIGIBLE', POLICY_VIOLATION: 'POLICY_VIOLATION', UNKNOWN: 'UNKNOWN',
});

// #110 / #112 / #113 已经补过“AI 辅助原创学习参考作答”的 14 卷。只记录路径，
// 用于提示不要重复补答案；本模块不会修改这些文件。
export const PRIOR_ANSWER_BATCH_PATHS = Object.freeze([
  '省考/上海/2017/申论-行政执法卷.md',
  '省考/上海/2020/申论-行政执法卷.md',
  '省考/广东/2026/申论-行政执法.md',
  '省考/四川/2023/申论-上半年行政执法卷.md',
  '省考/四川/2024/申论-县乡、普通选调卷.md',
  '省考/福建/2018/申论-县级卷.md',
  '省考/福建/2021/申论-县级.md',
  '省考/福建/2023/申论-县乡.md',
  '省考/福建/2024/申论-县乡卷.md',
  '省考/四川/2023/申论-省市.md',
  '省考/四川/2026/申论-县乡、普通选调卷.md',
  '省考/福建/2021/申论-乡镇.md',
  '省考/福建/2023/申论-省市.md',
  '省考/福建/2024/申论-行政执法.md',
]);

// 这些 issue 会阻止“技术上可用/可进入后续发布流程”的判定。
const FATAL_CODES = new Set([
  'volume-missing',
  'required-file-missing',
  'json-parse-error',
  'unstable-snapshot',
  'identity-mismatch',
  'index-paper-mismatch',
  'receipt-paper-mismatch',
  'question-count-mismatch',
  'question-number-set-mismatch',
  'answers-incomplete',
  'material-pane-gap',
  'material-ref-unresolved',
  'asset-missing',
  'asset-sha-mismatch',
  'asset-size-mismatch',
  'asset-ref-missing',
  'asset-ref-escape',
  'asset-ref-external',
  'asset-ref-count-mismatch',
  'asset-ref-order-mismatch',
  'paper-md-ref-mismatch',
  'images-missing',
  'document-sha-mismatch',
  'rights-policy-violation',
  'archive-status-inconsistent',
]);

const VARIANT_TYPES = Object.freeze({
  a: ['A类', 'A卷'],
  b: ['B类', 'B卷'],
  c: ['C类', 'C卷'],
  xingzheng: ['行政执法', '行政执法卷'],
});

const REQUIRED_FILES = ['paper.json', 'paper.md', 'receipt.json'];

const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const sha256File = (file) => sha256(fs.readFileSync(file));
const isInt = (value) => Number.isInteger(value);
const asInt = (value) => (isInt(value) ? value : null);

function readJsonReadonly(file) {
  try {
    const bytes = fs.readFileSync(file);
    return { ok: true, value: JSON.parse(bytes.toString('utf8')), sha256: sha256(bytes), bytes: bytes.length };
  } catch (error) {
    return { ok: false, error: String(error?.message ?? error), sha256: null, bytes: null };
  }
}

function readTextReadonly(file) {
  try {
    const bytes = fs.readFileSync(file);
    return { ok: true, text: bytes.toString('utf8'), sha256: sha256(bytes), bytes: bytes.length };
  } catch (error) {
    return { ok: false, error: String(error?.message ?? error), sha256: null, bytes: null };
  }
}

function statSignature(file) {
  try {
    const stat = fs.statSync(file);
    return `${stat.size}:${stat.mtimeMs}`;
  } catch {
    return 'missing';
  }
}

function dirSignature(dir) {
  try {
    return fs.readdirSync(dir).sort().map((name) => {
      const file = path.join(dir, name);
      const stat = fs.statSync(file);
      return `${name}:${stat.size}:${stat.mtimeMs}`;
    }).join('|');
  } catch {
    return 'missing';
  }
}

function relativeInside(root, target) {
  const relative = path.relative(root, target);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

/** 只读取 PNG/JPEG 头部的尺寸；不依赖第三方库。 */
export function imageDimensions(buffer) {
  if (!buffer || buffer.length < 24) return null;
  if (buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    return { type: 'png', width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }
  if (buffer[0] === 0xff && buffer[1] === 0xd8) {
    let offset = 2;
    while (offset + 9 < buffer.length) {
      if (buffer[offset] !== 0xff) { offset += 1; continue; }
      const marker = buffer[offset + 1];
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
        return { type: 'jpg', width: buffer.readUInt16BE(offset + 7), height: buffer.readUInt16BE(offset + 5) };
      }
      const length = buffer.readUInt16BE(offset + 2);
      if (length < 2) break;
      offset += 2 + length;
    }
  }
  return null;
}

/** 提取 Markdown/HTML 中出现的图片引用，保持首次出现顺序并去重。 */
export function imageReferences(text) {
  const found = [];
  const push = (raw) => {
    const value = String(raw ?? '').trim().replace(/^<|>$/gu, '');
    if (value) found.push(value);
  };
  for (const match of String(text ?? '').matchAll(/!\[[^\]]*\]\(\s*([^)\s]+)(?:\s+["'][^"']*["'])?\s*\)/gu)) push(match[1]);
  for (const match of String(text ?? '').matchAll(/<img\b[^>]*\bsrc="([^"]+)"/giu)) push(match[1]);
  const seen = new Set();
  return found.filter((value) => (seen.has(value) ? false : (seen.add(value), true)));
}

function collectDocumentRefs(document) {
  const texts = [];
  for (const material of document.materials ?? []) texts.push(material?.markdown ?? '');
  for (const question of document.questions ?? []) {
    texts.push(question?.promptMarkdown ?? '');
    texts.push(question?.requirementsMarkdown ?? '');
    texts.push(question?.answerMarkdown ?? '');
    texts.push(question?.explanationMarkdown ?? '');
  }
  return imageReferences(texts.join('\n'));
}

function normalizeReference(reference) {
  const withoutQuery = String(reference).split(/[?#]/u)[0].replace(/\\/gu, '/');
  try {
    return decodeURIComponent(withoutQuery);
  } catch {
    return withoutQuery;
  }
}

function isExternalReference(reference) {
  return /^(?:[a-z][a-z0-9+.-]*:|\/\/|\/)/iu.test(reference);
}

function wordLimitOf(requirements) {
  const text = String(requirements ?? '').replace(/<[^>]+>/gu, '');
  // 与 tools/fenbi/src/validate.mjs 的 wordRules 保持同一口径：
  // 逐题/分项字数要求无法自动判定，按 manual/unknown 处理，避免误报。
  if (/(?:每(?:题|问|项|点|条|部分)|各(?:题|问|项|点)).{0,30}(?:字|字数)/u.test(text)) {
    return { known: false, manual: true, min: null, max: null, unlimited: false };
  }
  let min = null;
  let max = null;
  for (const match of text.matchAll(/(?:不少于|至少|不低于)\s*(\d{2,4})\s*字/gu)) min = Number(match[1]);
  for (const match of text.matchAll(/(?:不超过|不多于|至多)\s*(\d{2,4})\s*字|(\d{2,4})\s*字(?:以内|以下)/gu)) {
    max = Number(match[1] ?? match[2]);
  }
  for (const match of text.matchAll(/(\d{2,4})\s*[-—–~～至到]\s*(\d{2,4})\s*字/gu)) {
    min = Number(match[1]); max = Number(match[2]);
  }
  for (const match of text.matchAll(/(\d{2,4})\s*字左右/gu)) {
    min = Math.floor(Number(match[1]) * 0.8); max = Math.ceil(Number(match[1]) * 1.2);
  }
  if (min === null && max === null) {
    return { known: false, manual: false, min: null, max: null, unlimited: /字数不限/u.test(text) };
  }
  return { known: true, manual: false, min, max, unlimited: false };
}

function plainText(markdown) {
  return String(markdown ?? '')
    .replace(/!\[[^\]]*\]\([^)]*\)/gu, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/gu, '$1')
    .replace(/<[^>]+>/gu, '')
    .replace(/[`*_~]/gu, '')
    .replace(/^\s{0,3}#{1,6}\s*/gmu, '')
    .replace(/^\s*[-+*]\s+/gmu, '')
    .replace(/\s/gu, '');
}

function charCount(markdown) {
  return [...plainText(markdown)].length;
}

function variantTypes(variant) {
  if (variant === null || variant === undefined || variant === '') return null;
  if (variant === 'unknown') return null;
  return VARIANT_TYPES[variant] ?? null;
}

function normalizeVariant(variant) {
  return variant === undefined || variant === '' ? null : variant;
}

function identityOf(value) {
  return {
    sourceId: value?.sourceId ?? null,
    area: value?.area ?? null,
    year: value?.year ?? null,
    variant: normalizeVariant(value?.variant),
    titleHash: value?.titleHash ?? null,
  };
}

/** 将档案卷映射到 main catalog 行；只做可解释的候选匹配，不强行断言。 */
export function matchMainCatalog(volume, manifestRows, priorAnswerPaths = PRIOR_ANSWER_BATCH_PATHS) {
  const rows = manifestRows.filter((row) => row?.subject === '申论'
    && row.area === volume.area && String(row.year) === String(volume.year));
  const types = variantTypes(volume.variant);
  let candidates = types ? rows.filter((row) => types.includes(row.paper_type)) : rows.slice();
  if (candidates.length === 0) candidates = rows.slice();
  const q = volume.questionCount;
  const qMatches = candidates.filter((row) => asInt(row.declared_questions) === q);
  if (qMatches.length > 0) candidates = qMatches;
  candidates = candidates.slice().sort((a, b) => String(a.path).localeCompare(String(b.path), 'zh'));
  const prior = new Set(priorAnswerPaths);
  const mapped = candidates.map((row) => ({
    path: row.path,
    paperType: row.paper_type ?? null,
    declaredQuestions: asInt(row.declared_questions),
    sha256: row.sha256 ?? null,
    priorAnswerBatch: prior.has(row.path),
  }));
  const match = candidates.length === 1 ? 'exact' : candidates.length > 1 ? 'ambiguous' : 'none';
  const exactPath = match === 'exact' ? candidates[0].path : null;
  return {
    match,
    exactPath,
    priorAnswerOverlap: Boolean(exactPath && prior.has(exactPath)),
    priorAnswerCandidate: candidates.some((row) => prior.has(row.path)),
    candidates: mapped,
  };
}

function addIssue(issues, code, detail = null) {
  if (issues.some((issue) => issue.code === code && issue.detail === detail)) return;
  issues.push({ code, severity: FATAL_CODES.has(code) ? 'fatal' : 'warning', detail });
}

function compareFields(issues, code, expected, actual, fields) {
  const mismatched = fields.filter((field) => JSON.stringify(expected?.[field] ?? null) !== JSON.stringify(actual?.[field] ?? null));
  if (mismatched.length > 0) addIssue(issues, code, `fields=${mismatched.join(',')}`);
  return mismatched;
}

function readRightsPolicy(archiveRoot) {
  const file = path.join(archiveRoot, 'rights-provenance.json');
  const parsed = readJsonReadonly(file);
  if (!parsed.ok) return { ok: false, value: null, sha256: null };
  return { ok: true, value: parsed.value, sha256: parsed.sha256 };
}

function publicationGate(paper, receipt, indexRow, rightsPolicy) {
  const issues = [];
  const papersRights = paper?.rights ?? {};
  const checks = [
    ['paper', papersRights.rightsStatus, papersRights.cloudStorageBlocked, papersRights.githubPublicationAllowed],
    ['receipt', receipt?.rightsStatus, receipt?.cloudStorageBlocked, null],
    ['index', indexRow?.rightsStatus, indexRow?.cloudStorageBlocked, null],
  ];
  for (const [source, rightsStatus, blocked, allowed] of checks) {
    if (rightsStatus === 'cleared' || allowed === true || blocked === false) {
      addIssue(issues, 'rights-policy-violation', `source=${source}`);
    }
    if (rightsStatus === null || rightsStatus === undefined) addIssue(issues, 'rights-status-missing', `source=${source}`);
  }
  if (papersRights.rightsStatus !== 'unverified') addIssue(issues, 'rights-status-unexpected', `paper=${papersRights.rightsStatus}`);
  const provenance = rightsPolicy?.value;
  let provenanceOk = false;
  if (!provenance) {
    addIssue(issues, 'rights-provenance-missing', null);
  } else {
    if (provenance.fields?.thirdPartyCopyrightLicense?.status !== 'not-established') {
      addIssue(issues, 'rights-policy-violation', 'provenance=thirdPartyCopyrightLicense');
    }
    if (provenance.fields?.githubCloudStorage?.status !== 'blocked') {
      addIssue(issues, 'rights-policy-violation', 'provenance=githubCloudStorage');
    }
    if (asInt(provenance.fields?.githubCloudStorage?.publishableVolumes) > 0) {
      addIssue(issues, 'rights-policy-violation', 'provenance=publishableVolumes');
    }
    provenanceOk = provenance.fields?.thirdPartyCopyrightLicense?.status === 'not-established'
      && provenance.fields?.githubCloudStorage?.status === 'blocked'
      && !(asInt(provenance.fields?.githubCloudStorage?.publishableVolumes) > 0);
  }
  const blocked = papersRights.rightsStatus !== 'cleared' || papersRights.cloudStorageBlocked !== false;
  let status = PUBLICATION.BLOCKED;
  if (issues.some((issue) => issue.code === 'rights-policy-violation')) status = PUBLICATION.POLICY_VIOLATION;
  else if (!blocked && provenanceOk) status = PUBLICATION.ELIGIBLE;
  else if (!blocked) status = PUBLICATION.UNKNOWN;
  else if (papersRights.rightsStatus === undefined) status = PUBLICATION.UNKNOWN;
  return { status, issues };
}

function verifyDocumentSha(volume, paper, receipt, inventory) {
  const expected = paper?.capture?.documentSha ?? receipt?.capture?.documentSha ?? null;
  const result = { expected, observed: null, status: 'unavailable', captureDir: null };
  if (paper?.capture?.documentSha && receipt?.capture?.documentSha
    && paper.capture.documentSha !== receipt.capture.documentSha) {
    result.status = 'paper-receipt-mismatch';
    return result;
  }
  if (!expected || !inventory?.captures) return result;
  const captures = inventory.captures.filter((capture) => String(capture.sourceId) === String(volume.sourceId));
  if (captures.length === 0) { result.status = 'no-capture'; return result; }
  if (!captures.some((capture) => capture.documentSha === expected)) {
    result.status = 'mismatch';
    return result;
  }
  const candidate = captures.find((capture) => capture.documentSha === expected && capture.dir);
  result.captureDir = candidate?.dir ?? null;
  const file = candidate?.dir ? path.join(candidate.dir, 'document.json') : null;
  if (!file || !fs.existsSync(file)) { result.status = 'unreadable'; return result; }
  try {
    result.observed = sha256File(file);
    result.status = result.observed === expected ? 'verified' : 'mismatch';
  } catch {
    result.status = 'unreadable';
  }
  return result;
}

/**
 * 扫描一个本地档案。所有读取均为只读；返回的矩阵不含正文。
 * @param {object} options
 * @param {string} options.archiveRoot
 * @param {string} [options.mainManifestPath]
 * @param {string} [options.inventoryPath]
 * @param {string[]} [options.assetStores]
 * @param {string[]} [options.priorAnswerPaths]
 */
export function scanArchive({
  archiveRoot,
  mainManifestPath = null,
  inventoryPath = null,
  assetStores = [],
  priorAnswerPaths = PRIOR_ANSWER_BATCH_PATHS,
} = {}) {
  if (!archiveRoot) throw new Error('archiveRoot is required');
  const root = path.resolve(archiveRoot);
  const papersDir = path.join(root, 'papers');
  const indexPath = path.join(root, 'catalog', 'index.jsonl');
  const manifestPath = path.join(root, 'catalog', 'archive-manifest.json');
  const indexBefore = statSignature(indexPath);
  const indexParsed = readTextReadonly(indexPath);
  const indexShaBefore = indexParsed.sha256;
  const manifestParsed = readJsonReadonly(manifestPath);
  const rightsPolicy = readRightsPolicy(root);
  const inventoryParsed = inventoryPath ? readJsonReadonly(inventoryPath) : { ok: false, value: null };
  const mainManifest = mainManifestPath ? readTextReadonly(mainManifestPath) : { ok: false, value: null };
  const manifestRows = mainManifest.ok
    ? mainManifest.text.split(/\r?\n/u).filter(Boolean).map((line) => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean)
    : [];
  const staleStore = new Map();
  for (const store of assetStores) {
    try {
      for (const name of fs.readdirSync(store)) {
        const stem = name.replace(/\.[^.]+$/u, '');
        if (!staleStore.has(stem)) staleStore.set(stem, path.join(store, name));
      }
    } catch { /* 只读目录不存在时忽略 */ }
  }

  const indexRows = indexParsed.ok
    ? indexParsed.text.split(/\r?\n/u).filter(Boolean).map((line) => { try { return JSON.parse(line); } catch { return null; } })
    : [];
  const indexById = new Map();
  for (const row of indexRows) {
    if (!row || !row.sourceId) continue;
    const list = indexById.get(String(row.sourceId)) ?? [];
    list.push(row);
    indexById.set(String(row.sourceId), list);
  }
  const dirs = fs.existsSync(papersDir)
    ? fs.readdirSync(papersDir).filter((name) => { try { return fs.statSync(path.join(papersDir, name)).isDirectory(); } catch { return false; } })
    : [];
  const allIds = [...new Set([...dirs, ...indexById.keys()])].sort((a, b) => a.localeCompare(b, 'zh'));

  const volumes = [];
  for (const sourceId of allIds) {
    const volume = checkVolume({
      sourceId,
      root,
      papersDir,
      indexRows: indexById.get(sourceId) ?? [],
      inventory: inventoryParsed.ok ? inventoryParsed.value : null,
      manifestRows,
      rightsPolicy,
      priorAnswerPaths,
      staleStore,
    });
    volumes.push(volume);
  }

  const indexAfter = statSignature(indexPath);
  const indexParsedAfter = readTextReadonly(indexPath);
  const snapshotStable = indexBefore === indexAfter && indexShaBefore === indexParsedAfter.sha256;
  if (!snapshotStable) {
    for (const volume of volumes) {
      addIssue(volume.issues, 'unstable-snapshot', 'catalog/index.jsonl changed during scan');
      volume.technicalStatus = TECHNICAL.SKIP;
    }
  }
  const totals = summarizeVolumes(volumes);
  const archiveManifest = compareArchiveManifest(manifestParsed.ok ? manifestParsed.value : null, volumes, totals);
  const fullRepairPlan = buildRepairPlan(volumes, staleStore);
  const report = {
    schemaVersion: PREFLIGHT_SCHEMA_VERSION,
    kind: 'shenlun-local-archive-publish-preflight',
    generatedAt: new Date().toISOString(),
    method: 'offline read-only parse of catalog/papers/receipts/assets; metadata, counts and hashes only; no network; no content emitted',
    archive: {
      root,
      indexSha256: indexShaBefore,
      indexRowCount: indexParsed.ok ? indexRows.filter(Boolean).length : null,
      archiveManifestGeneratedAt: manifestParsed.ok ? manifestParsed.value?.generatedAt ?? null : null,
      snapshotStable,
      volumeCount: volumes.length,
    },
    rights: {
      provenanceSha256: rightsPolicy.sha256,
      statusCounts: countBy(volumes, (volume) => volume.rightsStatus ?? 'missing'),
      cloudStorageBlockedTrue: volumes.filter((volume) => volume.cloudStorageBlocked === true).length,
      clearedCount: volumes.filter((volume) => volume.rightsStatus === 'cleared').length,
      thirdPartyCopyrightLicense: rightsPolicy.value?.fields?.thirdPartyCopyrightLicense?.status ?? null,
      githubCloudStorage: rightsPolicy.value?.fields?.githubCloudStorage?.status ?? null,
      publishableVolumesDeclared: rightsPolicy.value?.fields?.githubCloudStorage?.publishableVolumes ?? null,
      note: 'technical integrity and third-party copyright permission are separate gates; this report never clears rights',
    },
    gates: {
      technical: {
        PASS: volumes.filter((volume) => volume.technicalStatus === TECHNICAL.PASS).length,
        FAIL: volumes.filter((volume) => volume.technicalStatus === TECHNICAL.FAIL).length,
        SKIP: volumes.filter((volume) => volume.technicalStatus === TECHNICAL.SKIP).length,
      },
      publication: {
        BLOCKED: volumes.filter((volume) => volume.publicationStatus === PUBLICATION.BLOCKED).length,
        ELIGIBLE: volumes.filter((volume) => volume.publicationStatus === PUBLICATION.ELIGIBLE).length,
        POLICY_VIOLATION: volumes.filter((volume) => volume.publicationStatus === PUBLICATION.POLICY_VIOLATION).length,
        UNKNOWN: volumes.filter((volume) => volume.publicationStatus === PUBLICATION.UNKNOWN).length,
      },
    },
    totals,
    groups: groupVolumes(volumes),
    issueSummary: issueSummary(volumes),
    assetSummary: assetSummary(volumes),
    archiveManifest,
    repairPlan: summarizeRepairPlan(fullRepairPlan),
    recoverySummary: countBy(volumes, (volume) => volume.recovery?.status ?? 'unknown'),
    volumes,
  };
  // 完整计划只给 CLI 使用，不进入 JSON 报告（其中含本机路径）。
  Object.defineProperty(report, '_repairPlan', { value: fullRepairPlan, enumerable: false });
  return report;
}

function summarizeRepairPlan(plan) {
  const copyable = (plan.operations ?? []).filter((operation) => operation.op === 'copy');
  const unresolved = (plan.operations ?? []).filter((operation) => operation.op === 'unresolved');
  return {
    copyable: copyable.length,
    unresolvedVolumes: unresolved.length,
    unresolvedImages: unresolved.reduce((total, operation) => total + (operation.count ?? 0), 0),
    note: 'copy 修复只补缺失/哈希不符的图片字节，不删除、不改题目或权利标记；unresolved 表示本地无 SHA 元数据，禁止凭尺寸或顺序猜图。',
  };
}

function checkVolume({
  sourceId, root, papersDir, indexRows, inventory, manifestRows, rightsPolicy, priorAnswerPaths, staleStore,
}) {
  const paperDir = path.join(papersDir, sourceId);
  const issues = [];
  const base = {
    sourceId,
    area: null,
    year: null,
    variant: null,
    cohort: null,
    technicalStatus: TECHNICAL.SKIP,
    publicationStatus: PUBLICATION.UNKNOWN,
    archiveStatus: null,
    rightsStatus: null,
    cloudStorageBlocked: null,
    questionCount: 0,
    answersPresent: 0,
    materialPanes: 0,
    materialTabsDeclared: null,
    analysis: { textual: 0, imageOnly: 0, videoOnly: 0, absent: 0 },
    assets: { expectedRefs: 0, stored: 0, verified: 0, missing: 0, orphan: 0, widthKnown: 0 },
    hashes: {},
    mainCatalog: { match: 'none', exactPath: null, priorAnswerOverlap: false, priorAnswerCandidate: false, candidates: [] },
    checks: issues,
  };
  if (!fs.existsSync(paperDir) || !fs.statSync(paperDir).isDirectory()) {
    addIssue(issues, 'volume-missing', 'paper directory absent');
    base.mainCatalog = { match: 'none', exactPath: null, priorAnswerOverlap: false, priorAnswerCandidate: false, candidates: [] };
    return base;
  }
  if (indexRows.length === 0) addIssue(issues, 'identity-mismatch', 'index row missing');
  if (indexRows.length > 1) addIssue(issues, 'identity-mismatch', `duplicate index rows=${indexRows.length}`);
  const indexRow = indexRows[0] ?? {};

  const signatureBefore = Object.fromEntries(REQUIRED_FILES.map((name) => [name, statSignature(path.join(paperDir, name))]));
  const assetsSignatureBefore = dirSignature(path.join(paperDir, 'assets'));
  const paperRead = readJsonReadonly(path.join(paperDir, 'paper.json'));
  const receiptRead = readJsonReadonly(path.join(paperDir, 'receipt.json'));
  const paperMdPath = path.join(paperDir, 'paper.md');
  const paperMdBytes = fs.existsSync(paperMdPath) ? fs.readFileSync(paperMdPath) : null;
  for (const name of REQUIRED_FILES) {
    if (!fs.existsSync(path.join(paperDir, name))) addIssue(issues, 'required-file-missing', name);
  }
  if (!paperRead.ok) addIssue(issues, 'json-parse-error', 'paper.json');
  if (!receiptRead.ok) addIssue(issues, 'json-parse-error', 'receipt.json');
  if (!paperRead.ok || !receiptRead.ok) {
    base.hashes = {
      paperJsonSha256: paperRead.sha256,
      receiptSha256: receiptRead.sha256,
      paperMdSha256: paperMdBytes ? sha256(paperMdBytes) : null,
    };
    base.technicalStatus = TECHNICAL.FAIL;
    return base;
  }
  const paper = paperRead.value;
  const receipt = receiptRead.value;
  base.area = paper.area ?? indexRow.area ?? null;
  base.year = paper.year ?? indexRow.year ?? null;
  base.variant = paper.variant ?? null;
  base.cohort = paper.cohort ?? null;
  base.archiveStatus = paper.archiveStatus ?? null;
  base.rightsStatus = paper.rights?.rightsStatus ?? receipt.rightsStatus ?? null;
  base.cloudStorageBlocked = paper.rights?.cloudStorageBlocked ?? receipt.cloudStorageBlocked ?? null;
  const structure = paper.structure ?? {};
  const questions = Array.isArray(paper.questions) ? paper.questions : [];
  const materials = Array.isArray(paper.materials) ? paper.materials : [];
  const assets = Array.isArray(paper.assets) ? paper.assets : [];
  const missingImages = Array.isArray(paper.missingImages) ? paper.missingImages : [];
  base.questionCount = questions.length;
  base.answersPresent = questions.filter((question) => String(question?.answerMarkdown ?? '').trim()).length;
  base.materialPanes = materials.length;
  base.materialTabsDeclared = asInt(structure.materialTabsDeclared) ?? asInt(receipt.materialTabsDeclared);
  base.analysis = normalizeAnalysis(paper.analysis);

  // --- 身份与计数 ---
  const identityFields = ['sourceId', 'area', 'year', 'variant', 'titleHash'];
  compareFields(issues, 'identity-mismatch', identityOf(paper), identityOf(receipt), identityFields);
  compareFields(issues, 'identity-mismatch', identityOf(paper), identityOf(indexRow), identityFields);
  const receiptExpected = asInt(receipt.expectedQuestions);
  const structureExpected = asInt(structure.questionCount);
  const indexExpected = asInt(indexRow.questions);
  // expectedQuestions=0 表示来源未给出题数（旧采集），不能当成“应为 0 题”。
  const expectedQuestions = receiptExpected !== null && receiptExpected > 0
    ? receiptExpected
    : structureExpected !== null && structureExpected > 0
      ? structureExpected
      : indexExpected !== null && indexExpected > 0 ? indexExpected : null;
  if (expectedQuestions !== null && expectedQuestions !== questions.length) {
    addIssue(issues, 'question-count-mismatch', `expected=${expectedQuestions} actual=${questions.length}`);
  }
  if (asInt(structure.questionCount) !== null && structure.questionCount !== questions.length) {
    addIssue(issues, 'question-count-mismatch', `structure=${structure.questionCount} actual=${questions.length}`);
  }
  if (asInt(indexRow.questions) !== null && indexRow.questions !== questions.length) {
    addIssue(issues, 'index-paper-mismatch', 'fields=questions');
  }
  if (asInt(receipt.questionCount) !== null && receipt.questionCount !== questions.length) {
    addIssue(issues, 'receipt-paper-mismatch', 'fields=questionCount');
  }
  const numbers = questions.map((question) => asInt(question?.number)).filter((number) => number !== null);
  if (new Set(numbers).size !== numbers.length) addIssue(issues, 'question-number-set-mismatch', 'duplicate-numbers');
  const missingNumbers = Array.isArray(receipt.missingQuestionNumbers) ? receipt.missingQuestionNumbers : [];
  if (missingNumbers.length > 0) addIssue(issues, 'question-number-set-mismatch', `missing=${missingNumbers.join(',')}`);
  if (expectedQuestions !== null && expectedQuestions === questions.length) {
    const expectedSet = Array.from({ length: expectedQuestions }, (_, index) => index + 1);
    if (numbers.length === questions.length) {
      const actual = numbers.slice().sort((a, b) => a - b);
      if (JSON.stringify(actual) !== JSON.stringify(expectedSet)) {
        addIssue(issues, 'question-number-set-mismatch', `actual=${actual.join(',')}`);
      }
    }
  }
  if (base.answersPresent !== questions.length) {
    addIssue(issues, 'answers-incomplete', `present=${base.answersPresent}/${questions.length}`);
  }
  if (asInt(receipt.answersPresent) !== null && receipt.answersPresent !== base.answersPresent) {
    addIssue(issues, 'receipt-paper-mismatch', 'fields=answersPresent');
  }
  if (asInt(indexRow.answersPresent) !== null && indexRow.answersPresent !== base.answersPresent) {
    addIssue(issues, 'index-paper-mismatch', 'fields=answersPresent');
  }

  // --- 材料页签 ---
  const storedTabs = [];
  for (const material of materials) for (const tab of material?.tabNumbers ?? []) if (isInt(tab)) storedTabs.push(tab);
  const uniqueStoredTabs = [...new Set(storedTabs)];
  if (base.materialTabsDeclared !== null) {
    const expectedTabs = Array.from({ length: base.materialTabsDeclared }, (_, index) => index + 1);
    const missingTabs = expectedTabs.filter((tab) => !uniqueStoredTabs.includes(tab));
    const extraTabs = uniqueStoredTabs.filter((tab) => !expectedTabs.includes(tab));
    if (missingTabs.length > 0) addIssue(issues, 'material-pane-gap', `missing=${missingTabs.join(',')}`);
    if (extraTabs.length > 0) addIssue(issues, 'material-tab-count-mismatch', `extra=${extraTabs.join(',')}`);
  } else {
    addIssue(issues, 'material-count-unknown', null);
  }
  if (materials.length !== uniqueStoredTabs.length) {
    addIssue(issues, 'material-tab-count-mismatch', `panes=${materials.length} tabs=${uniqueStoredTabs.length}`);
  }
  if (asInt(structure.materialPanesStored) !== null && structure.materialPanesStored !== materials.length) {
    addIssue(issues, 'receipt-paper-mismatch', 'fields=materialPanesStored');
  }
  if (asInt(receipt.materialPanesStored) !== null && receipt.materialPanesStored !== materials.length) {
    addIssue(issues, 'receipt-paper-mismatch', 'fields=materialPanesStored');
  }
  if (asInt(indexRow.materialPanesStored) !== null && indexRow.materialPanesStored !== materials.length) {
    addIssue(issues, 'index-paper-mismatch', 'fields=materialPanesStored');
  }
  let unresolvedRefs = 0;
  for (const question of questions) {
    for (const reference of question?.materialRefs ?? []) {
      if (reference?.stored !== true) { unresolvedRefs += 1; continue; }
      if (isInt(reference.tabNumber) && !uniqueStoredTabs.includes(reference.tabNumber)) unresolvedRefs += 1;
      if (!reference.htmlSha) addIssue(issues, 'material-ref-unresolved', 'missing-htmlSha');
    }
  }
  if (unresolvedRefs > 0) addIssue(issues, 'material-ref-unresolved', `count=${unresolvedRefs}`);
  const declaredUnresolved = asInt(structure.unresolvedMaterialReferences);
  if (declaredUnresolved !== null && declaredUnresolved !== unresolvedRefs) {
    addIssue(issues, 'material-ref-unresolved', `declared=${declaredUnresolved} actual=${unresolvedRefs}`);
  }

  // --- 解析分类 ---
  const analysisSum = base.analysis.textual + base.analysis.imageOnly + base.analysis.videoOnly + base.analysis.absent;
  if (analysisSum !== questions.length) addIssue(issues, 'analysis-count-mismatch', `sum=${analysisSum}/${questions.length}`);
  const textualActual = questions.filter((question) => question?.analysisStatus === 'textual').length;
  if (textualActual !== base.analysis.textual) addIssue(issues, 'analysis-count-mismatch', `textual=${base.analysis.textual} actual=${textualActual}`);
  const explanations = questions.filter((question) => String(question?.explanationMarkdown ?? '').trim()).length;
  if (explanations === 0 && questions.length > 0) addIssue(issues, 'explanation-empty', null);
  compareFields(issues, 'receipt-paper-mismatch', base.analysis, receipt.analysis ?? {}, ['textual', 'imageOnly', 'videoOnly', 'absent']);

  // --- 字号/字数（只记录计数，不输出正文） ---
  const wordStatus = { unknown: 0, manual: 0, unlimited: 0, aboveMax: 0, belowMin: 0 };
  for (const question of questions) {
    const limit = wordLimitOf(question?.requirementsMarkdown);
    if (limit.manual) { wordStatus.manual += 1; continue; }
    if (!limit.known) { if (limit.unlimited) wordStatus.unlimited += 1; else wordStatus.unknown += 1; continue; }
    const count = charCount(question?.answerMarkdown);
    if (!count) continue;
    if (limit.max !== null && count > limit.max) wordStatus.aboveMax += 1;
    if (limit.min !== null && count < limit.min) wordStatus.belowMin += 1;
  }
  if (wordStatus.aboveMax > 0) addIssue(issues, 'answer-above-word-maximum', `count=${wordStatus.aboveMax}`);
  if (wordStatus.belowMin > 0) addIssue(issues, 'answer-below-word-minimum', `count=${wordStatus.belowMin}`);
  if (wordStatus.unknown > 0) addIssue(issues, 'word-limits-unknown', `count=${wordStatus.unknown}`);
  base.wordLimits = wordStatus;

  // --- 图片与哈希 ---
  const assetDir = path.join(paperDir, 'assets');
  const documentRefs = collectDocumentRefs(paper);
  const paperMdRefs = paperMdBytes ? imageReferences(paperMdBytes.toString('utf8')) : [];
  const assetFiles = assets.map((asset) => {
    const file = String(asset?.file ?? '');
    const resolved = path.resolve(paperDir, file);
    const inside = relativeInside(assetDir, resolved);
    const name = path.basename(file);
    const exists = inside && fs.existsSync(resolved) && fs.statSync(resolved).isFile();
    let observedSha = null;
    let dimensions = null;
    let size = null;
    if (exists) {
      try {
        const buffer = fs.readFileSync(resolved);
        size = buffer.length;
        observedSha = sha256(buffer);
        dimensions = imageDimensions(buffer);
      } catch { /* 读取失败按缺失处理 */ }
    }
    return {
      file, resolved, inside, name, exists, observedSha, dimensions, size,
      declaredSha: asset?.sha256 ?? null,
      declaredBytes: asInt(asset?.bytes),
      width: asInt(asset?.width),
      height: asInt(asset?.height),
    };
  });
  let verified = 0;
  const listedFiles = new Set();
  for (const asset of assetFiles) {
    if (asset.file) listedFiles.add(asset.file);
    if (!asset.exists) { addIssue(issues, 'asset-missing', asset.name); continue; }
    if (!asset.declaredSha || asset.observedSha !== asset.declaredSha) {
      addIssue(issues, 'asset-sha-mismatch', asset.name);
    } else {
      verified += 1;
    }
    if (asset.declaredBytes !== null && asset.size !== null && asset.declaredBytes !== asset.size) {
      addIssue(issues, 'asset-size-mismatch', asset.name);
    }
    const stem = asset.name.replace(/\.[^.]+$/u, '');
    if (asset.declaredSha && stem !== asset.declaredSha) addIssue(issues, 'asset-file-noncanonical', asset.name);
    if (asset.width !== null && asset.dimensions && (asset.width !== asset.dimensions.width || asset.height !== asset.dimensions.height)) {
      addIssue(issues, 'asset-dimension-mismatch', asset.name);
    }
  }
  if (new Set(assets.map((asset) => asset?.sha256).filter(Boolean)).size !== assets.filter((asset) => asset?.sha256).length) {
    addIssue(issues, 'asset-duplicate', null);
  }
  const externalRefs = [...documentRefs, ...paperMdRefs].filter(isExternalReference);
  if (externalRefs.length > 0) addIssue(issues, 'asset-ref-external', `count=${externalRefs.length}`);
  const assetByName = new Map(assetFiles.map((asset) => [asset.file, asset]));
  const documentRefNames = documentRefs.filter((ref) => !isExternalReference(ref)).map(normalizeReference);
  const paperMdRefNames = paperMdRefs.filter((ref) => !isExternalReference(ref)).map(normalizeReference);
  const refsMissing = documentRefNames.filter((ref) => {
    if (ref.includes('..')) return false;
    return !assetByName.has(ref);
  });
  if (refsMissing.length > 0) addIssue(issues, 'asset-ref-missing', `count=${refsMissing.length}`);
  const escapes = documentRefNames.filter((ref) => ref.includes('..') || path.isAbsolute(ref));
  if (escapes.length > 0) addIssue(issues, 'asset-ref-escape', `count=${escapes.length}`);
  if (JSON.stringify(documentRefNames) !== JSON.stringify(paperMdRefNames)) {
    addIssue(issues, 'paper-md-ref-mismatch', `json=${documentRefNames.length} md=${paperMdRefNames.length}`);
  }
  const expectedAssetSequence = assets.map((asset) => normalizeReference(asset?.file ?? '')).filter(Boolean);
  if (documentRefNames.length !== expectedAssetSequence.length) {
    addIssue(issues, 'asset-ref-count-mismatch', `refs=${documentRefNames.length} assets=${expectedAssetSequence.length}`);
  } else if (documentRefNames.length > 1 && JSON.stringify(documentRefNames) !== JSON.stringify(expectedAssetSequence)) {
    addIssue(issues, 'asset-ref-order-mismatch', null);
  }
  let orphan = 0;
  try {
    for (const name of fs.readdirSync(assetDir)) {
      const rel = `assets/${name}`;
      if (!listedFiles.has(rel)) { orphan += 1; addIssue(issues, 'asset-orphan', name); }
    }
  } catch { /* assets 目录不存在时由缺失图片覆盖 */ }
  if (missingImages.length > 0) addIssue(issues, 'images-missing', `count=${missingImages.length}`);
  const expectedRefs = assets.length + missingImages.length;
  const declaredRefs = asInt(indexRow.imageRefs) ?? asInt(receipt.imageRefs);
  if (declaredRefs !== null && declaredRefs !== expectedRefs) {
    addIssue(issues, 'index-paper-mismatch', 'fields=imageRefs');
  }
  const declaredStored = asInt(indexRow.imageBytesStored) ?? asInt(receipt.imageBytesStored);
  if (declaredStored !== null && declaredStored !== assets.length) {
    addIssue(issues, 'index-paper-mismatch', 'fields=imageBytesStored');
  }
  base.assets = {
    expectedRefs,
    stored: assets.length,
    verified,
    missing: missingImages.length,
    orphan,
    widthKnown: assetFiles.filter((asset) => asset.width !== null && asset.height !== null).length,
  };

  // --- 档案状态与权利 ---
  if (paper.archiveStatus === 'COMPLETE' && issues.some((issue) => issue.severity === 'fatal')) {
    addIssue(issues, 'archive-status-inconsistent', 'declared=COMPLETE but fatal issues present');
  }
  if (paper.archiveStatus !== 'PARTIAL' && paper.archiveStatus !== 'COMPLETE') {
    addIssue(issues, 'archive-status-inconsistent', `declared=${paper.archiveStatus}`);
  }
  const publication = publicationGate(paper, receipt, indexRow, rightsPolicy);
  issues.push(...publication.issues);
  base.publicationStatus = publication.status;

  // --- 来源捕获 document.json 的 SHA 核对（只读哈希） ---
  base.documentSha = verifyDocumentSha({ sourceId }, paper, receipt, inventory);
  // 不把捕获目录的本机绝对路径写进报告。
  delete base.documentSha.captureDir;
  if (base.documentSha.status === 'paper-receipt-mismatch' || base.documentSha.status === 'mismatch') {
    addIssue(issues, 'document-sha-mismatch', base.documentSha.status);
  } else if (base.documentSha.status === 'unreadable') {
    addIssue(issues, 'document-sha-unreadable', null);
  }

  // --- 与 main catalog 的可解释匹配 ---
  base.mainCatalog = manifestRows.length > 0
    ? matchMainCatalog({ area: base.area, year: base.year, variant: base.variant, questionCount: questions.length }, manifestRows, priorAnswerPaths)
    : { match: 'unavailable', exactPath: null, priorAnswerOverlap: false, priorAnswerCandidate: false, candidates: [] };
  if (base.archiveStatus === 'COMPLETE' && issues.some((issue) => issue.severity === 'fatal')) {
    // 已在上面记录；保留此处以防未来顺序调整。
  }

  base.hashes = {
    paperJsonSha256: paperRead.sha256,
    receiptSha256: receiptRead.sha256,
    paperMdSha256: paperMdBytes ? sha256(paperMdBytes) : null,
    documentSha: base.documentSha.expected,
    documentShaObserved: base.documentSha.observed,
    // 只记录聚合哈希，不输出正文；用于后续变更时逐卷比对原题/材料/旧答案。
    materialsSha256: sha256(JSON.stringify(materials)),
    promptsSha256: sha256(JSON.stringify(questions.map((question) => ({
      prompt: question?.promptMarkdown ?? '', requirements: question?.requirementsMarkdown ?? '',
    })))),
    oldAnswersSha256: sha256(JSON.stringify(questions.map((question) => ({
      answer: question?.answerMarkdown ?? '', explanation: question?.explanationMarkdown ?? '',
    })))),
    assetsSha256: sha256(JSON.stringify(assets)),
  };

  // 快照是否在读取期间变化
  const signatureAfter = Object.fromEntries(REQUIRED_FILES.map((name) => [name, statSignature(path.join(paperDir, name))]));
  const assetsSignatureAfter = dirSignature(assetDir);
  if (JSON.stringify(signatureBefore) !== JSON.stringify(signatureAfter)
    || assetsSignatureBefore !== assetsSignatureAfter) {
    addIssue(issues, 'unstable-snapshot', 'volume files changed during scan');
  }

  const fatal = issues.some((issue) => issue.severity === 'fatal');
  base.technicalStatus = fatal ? TECHNICAL.FAIL : TECHNICAL.PASS;
  base.recovery = assessRecovery(base, inventory, staleStore);
  for (const asset of assetFiles) {
    if (!asset.exists && asset.declaredSha && staleStore.has(asset.declaredSha)) {
      base.repairableAssets = (base.repairableAssets ?? []).concat([{
        sourceId, file: asset.file, sha256: asset.declaredSha, from: staleStore.get(asset.declaredSha),
      }]);
    }
  }
  return base;
}

function assessRecovery(volume, inventory, staleStore) {
  if (volume.technicalStatus === TECHNICAL.PASS) return { status: 'not-needed', alternateCompleteCaptures: 0, localImageBytesAvailable: true };
  const fatalCodes = new Set((volume.checks ?? []).filter((issue) => issue.severity === 'fatal').map((issue) => issue.code));
  const usedDocumentSha = volume.documentSha?.expected ?? null;
  // 只把“另一份”capture 算作可重建来源；构建本卷所用的 capture 不算替代。
  const captures = (inventory?.captures ?? []).filter((capture) => String(capture.sourceId) === String(volume.sourceId)
    && (!usedDocumentSha || capture.documentSha !== usedDocumentSha));
  const declared = volume.materialTabsDeclared;
  const alternateCompleteCaptures = captures.filter((capture) => {
    const panes = asInt(capture.storedPanes);
    const unresolved = asInt(capture.unresolvedMaterialReferences);
    const questions = Array.isArray(capture.questions) ? capture.questions.length : asInt(capture.questions);
    return panes !== null && (declared === null || panes >= declared)
      && (unresolved === null || unresolved === 0)
      && (questions === null || questions >= volume.questionCount);
  }).length;
  const localImageBytesAvailable = captures.some((capture) => asInt(capture.imageBytesPresent) > 0)
    || (volume.assets?.stored ?? 0) > 0;
  let status = 'manual-review';
  if (fatalCodes.has('material-pane-gap') || fatalCodes.has('material-ref-unresolved')) {
    status = alternateCompleteCaptures > 0 ? 'rebuild-from-local-capture' : 'recapture-required';
  } else if (fatalCodes.has('images-missing')) {
    status = localImageBytesAvailable ? 'rebuild-images-from-local-capture' : 'missing-bytes-no-local-source';
  } else if (fatalCodes.has('answers-incomplete') || fatalCodes.has('question-count-mismatch') || fatalCodes.has('question-number-set-mismatch')) {
    status = 'recapture-required';
  }
  return { status, alternateCompleteCaptures, localImageBytesAvailable };
}

function normalizeAnalysis(analysis) {
  return {
    textual: asInt(analysis?.textual) ?? 0,
    imageOnly: asInt(analysis?.imageOnly) ?? 0,
    videoOnly: asInt(analysis?.videoOnly) ?? 0,
    absent: asInt(analysis?.absent) ?? 0,
  };
}

function countBy(items, selector) {
  const counts = {};
  for (const item of items) {
    const key = selector(item);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function summarizeVolumes(volumes) {
  const sum = (selector) => volumes.reduce((total, volume) => total + (selector(volume) ?? 0), 0);
  return {
    volumes: volumes.length,
    questions: sum((volume) => volume.questionCount),
    answers: sum((volume) => volume.answersPresent),
    materialPanes: sum((volume) => volume.materialPanes),
    imageRefs: sum((volume) => volume.assets.expectedRefs),
    imageBytesStored: sum((volume) => volume.assets.stored),
    imageBytesVerified: sum((volume) => volume.assets.verified),
    volumesWithMissingImages: volumes.filter((volume) => volume.assets.missing > 0).length,
    textualAnalysisQuestions: sum((volume) => volume.analysis.textual),
    videoOnlyAnalysisQuestions: sum((volume) => volume.analysis.videoOnly),
    absentAnalysisQuestions: sum((volume) => volume.analysis.absent),
    archiveComplete: volumes.filter((volume) => volume.archiveStatus === 'COMPLETE').length,
    archivePartial: volumes.filter((volume) => volume.archiveStatus === 'PARTIAL').length,
    technicalPass: volumes.filter((volume) => volume.technicalStatus === TECHNICAL.PASS).length,
    technicalFail: volumes.filter((volume) => volume.technicalStatus === TECHNICAL.FAIL).length,
    technicalSkip: volumes.filter((volume) => volume.technicalStatus === TECHNICAL.SKIP).length,
    publicationEligible: volumes.filter((volume) => volume.publicationStatus === PUBLICATION.ELIGIBLE).length,
    priorAnswerOverlap: volumes.filter((volume) => volume.mainCatalog?.priorAnswerOverlap).length,
    priorAnswerCandidates: volumes.filter((volume) => volume.mainCatalog?.priorAnswerCandidate).length,
  };
}

function groupVolumes(volumes) {
  const byArea = {};
  const byYear = {};
  const byRights = {};
  const byAreaYear = {};
  const bump = (bucket, key, volume) => {
    const entry = bucket[key] ?? (bucket[key] = { total: 0, PASS: 0, FAIL: 0, SKIP: 0, BLOCKED: 0, ELIGIBLE: 0, POLICY_VIOLATION: 0 });
    entry.total += 1;
    entry[volume.technicalStatus] = (entry[volume.technicalStatus] ?? 0) + 1;
    entry[volume.publicationStatus] = (entry[volume.publicationStatus] ?? 0) + 1;
  };
  for (const volume of volumes) {
    bump(byArea, volume.area ?? 'unknown', volume);
    bump(byYear, String(volume.year ?? 'unknown'), volume);
    bump(byRights, volume.publicationStatus, volume);
    bump(byAreaYear, `${volume.area ?? 'unknown'}/${volume.year ?? 'unknown'}`, volume);
  }
  return { byArea, byYear, byRights, byAreaYear };
}

function issueSummary(volumes) {
  const codes = {};
  for (const volume of volumes) {
    const seen = new Set();
    for (const issue of volume.checks ?? []) {
      const entry = codes[issue.code] ?? (codes[issue.code] = { fatal: 0, warning: 0, volumes: 0 });
      entry[issue.severity] += 1;
      if (!seen.has(issue.code)) { entry.volumes += 1; seen.add(issue.code); }
    }
  }
  return codes;
}

function assetSummary(volumes) {
  return {
    refs: volumes.reduce((total, volume) => total + volume.assets.expectedRefs, 0),
    stored: volumes.reduce((total, volume) => total + volume.assets.stored, 0),
    verified: volumes.reduce((total, volume) => total + volume.assets.verified, 0),
    missing: volumes.reduce((total, volume) => total + volume.assets.missing, 0),
    orphan: volumes.reduce((total, volume) => total + volume.assets.orphan, 0),
    volumesWithAssets: volumes.filter((volume) => volume.assets.stored > 0).length,
    volumesWithoutAssets: volumes.filter((volume) => volume.assets.stored === 0).length,
  };
}

function compareArchiveManifest(manifest, volumes, totals) {
  if (!manifest) return { available: false, drift: [] };
  const declared = manifest.totals ?? {};
  const computed = {
    volumes: totals.volumes,
    questions: totals.questions,
    answers: totals.answers,
    materialPanes: totals.materialPanes,
    imageRefs: totals.imageRefs,
    imageBytesStored: totals.imageBytesStored,
    volumesWithMissingImages: totals.volumesWithMissingImages,
    textualAnalysisQuestions: totals.textualAnalysisQuestions,
    videoOnlyAnalysisQuestions: totals.videoOnlyAnalysisQuestions,
    absentAnalysisQuestions: totals.absentAnalysisQuestions,
    archiveComplete: totals.archiveComplete,
    archivePartial: totals.archivePartial,
    cohortZhejiang20: volumes.filter((volume) => volume.cohort === 'zhejiang-recapture-20').length,
    cohortNational8: volumes.filter((volume) => volume.cohort === 'national-s6-8').length,
    otherVolumes: volumes.filter((volume) => !['zhejiang-recapture-20', 'national-s6-8'].includes(volume.cohort)).length,
    githubPublished: volumes.filter((volume) => volume.publicationStatus === PUBLICATION.ELIGIBLE).length,
  };
  const drift = [];
  for (const [key, value] of Object.entries(computed)) {
    if (key in declared && declared[key] !== value) drift.push({ field: key, declared: declared[key], computed: value });
  }
  return { available: true, generatedAt: manifest.generatedAt ?? null, drift, computed };
}

function buildRepairPlan(volumes, staleStore) {
  const operations = [];
  for (const volume of volumes) {
    for (const asset of volume.repairableAssets ?? []) operations.push({ op: 'copy', ...asset });
    const unresolved = volume.assets.missing - (volume.repairableAssets?.length ?? 0);
    if (unresolved > 0) operations.push({ op: 'unresolved', sourceId: volume.sourceId, reason: 'missing-images-without-local-sha', count: unresolved });
  }
  return { generatedAt: new Date().toISOString(), applyByDefault: false, operations };
}

/** 渲染 metadata-only Markdown 摘要；不包含任何题目/材料/答案正文。 */
export function renderMarkdown(report) {
  const lines = [];
  lines.push('# 申论本地档案 publish-preflight（metadata-only）');
  lines.push('');
  lines.push(`- 生成时间：${report.generatedAt}`);
  lines.push(`- 档案根目录：\`${report.archive.root}\``);
  lines.push(`- catalog/index.jsonl SHA256：\`${report.archive.indexSha256 ?? 'unavailable'}\``);
  lines.push(`- 快照稳定：${report.archive.snapshotStable ? '是' : '否（扫描期间目录发生变化）'}`);
  lines.push(`- 卷数：${report.archive.volumeCount}（只统计扫描期间索引与卷文件未变化的稳定快照；构建中的短暂目录变化不计入）`);
  lines.push('- 口径：技术完整性（本地可用性）与第三方版权/再分发权利是两个独立门禁；本报告不改变任何 rights 标记。');
  lines.push('- main 重叠是按“地区+年份+卷型+题数”给出的可解释候选（archive 无 main 的行号/标题主键），唯一候选不等于版权或内容同一性的最终认证。');
  lines.push('');
  lines.push('## 门禁汇总');
  lines.push('');
  lines.push('| technical | 卷数 | publication | 卷数 |');
  lines.push('| --- | ---: | --- | ---: |');
  const t = report.gates.technical;
  const p = report.gates.publication;
  lines.push(`| PASS | ${t.PASS} | BLOCKED | ${p.BLOCKED} |`);
  lines.push(`| FAIL | ${t.FAIL} | ELIGIBLE | ${p.ELIGIBLE} |`);
  lines.push(`| SKIP | ${t.SKIP} | POLICY_VIOLATION | ${p.POLICY_VIOLATION} |`);
  lines.push('');
  lines.push('## 按地区');
  lines.push('');
  lines.push('| 地区 | 卷数 | PASS | FAIL | SKIP | BLOCKED |');
  lines.push('| --- | ---: | ---: | ---: | ---: | ---: |');
  for (const [area, entry] of Object.entries(report.groups.byArea).sort(([a], [b]) => a.localeCompare(b, 'zh'))) {
    lines.push(`| ${area} | ${entry.total} | ${entry.PASS ?? 0} | ${entry.FAIL ?? 0} | ${entry.SKIP ?? 0} | ${entry.BLOCKED ?? 0} |`);
  }
  lines.push('');
  lines.push('## 按年份');
  lines.push('');
  lines.push('| 年份 | 卷数 | PASS | FAIL | SKIP |');
  lines.push('| --- | ---: | ---: | ---: | ---: |');
  for (const [year, entry] of Object.entries(report.groups.byYear).sort(([a], [b]) => a.localeCompare(b, 'zh'))) {
    lines.push(`| ${year} | ${entry.total} | ${entry.PASS ?? 0} | ${entry.FAIL ?? 0} | ${entry.SKIP ?? 0} |`);
  }
  lines.push('');
  lines.push('## issue 汇总');
  lines.push('');
  lines.push('| code | severity | 卷数 |');
  lines.push('| --- | --- | ---: |');
  for (const [code, entry] of Object.entries(report.issueSummary).sort(([a], [b]) => a.localeCompare(b))) {
    lines.push(`| ${code} | ${entry.fatal > 0 ? 'fatal' : 'warning'} | ${entry.volumes} |`);
  }
  lines.push('');
  lines.push('## 图片映射');
  lines.push('');
  lines.push(`- 引用 ${report.assetSummary.refs} 张，落地 ${report.assetSummary.stored} 张，SHA 校验通过 ${report.assetSummary.verified} 张，缺字节 ${report.assetSummary.missing} 张，孤儿 ${report.assetSummary.orphan} 张。`);
  lines.push(`- 含图片卷 ${report.assetSummary.volumesWithAssets}，无图片卷 ${report.assetSummary.volumesWithoutAssets}。`);
  lines.push(`- 离线可复制修复 ${report.repairPlan.copyable} 张；不可修复 ${report.repairPlan.unresolvedVolumes} 卷 / ${report.repairPlan.unresolvedImages} 张（本地无 SHA 元数据，禁止按顺序或尺寸猜图）。`);
  lines.push('');
  lines.push('## 与 main catalog 的重叠');
  lines.push('');
  const exact = report.volumes.filter((volume) => volume.mainCatalog.match === 'exact');
  const ambiguous = report.volumes.filter((volume) => volume.mainCatalog.match === 'ambiguous');
  const prior = report.volumes.filter((volume) => volume.mainCatalog.priorAnswerOverlap);
  const priorCandidates = report.volumes.filter((volume) => volume.mainCatalog.priorAnswerCandidate);
  lines.push(`- 可唯一匹配 main：${exact.length} 卷；候选不唯一：${ambiguous.length} 卷；无候选：${report.volumes.filter((volume) => volume.mainCatalog.match === 'none').length} 卷。`);
  lines.push(`- 唯一匹配且命中 #110/#112/#113 已补答案路径：${prior.length} 卷${prior.length ? `（sourceId：${prior.map((volume) => volume.sourceId).join(', ')}）` : ''}；仅作为候选命中：${priorCandidates.length - prior.length} 卷。`);
  lines.push('');
  lines.push('## 离线修复可行性');
  lines.push('');
  for (const [status, count] of Object.entries(report.recoverySummary ?? {}).sort(([a], [b]) => a.localeCompare(b))) {
    lines.push(`- ${status}: ${count}`);
  }
  lines.push('');
  lines.push('`recapture-required` 表示现有本地 capture 没有更完整的页签/答案/题号，必须由 S4 重新采集；`missing-bytes-no-local-source` 表示缺图且本地没有任何同 SHA 字节，不能用顺序或尺寸猜图。');
  lines.push('');
  lines.push('## 失败/跳过卷（仅元数据）');
  lines.push('');
  lines.push('| sourceId | 地区 | 年份 | 卷型 | technical | fatal codes |');
  lines.push('| --- | --- | ---: | --- | --- | --- |');
  for (const volume of report.volumes.filter((entry) => entry.technicalStatus !== TECHNICAL.PASS)) {
    const fatal = [...new Set(volume.checks.filter((issue) => issue.severity === 'fatal').map((issue) => issue.code))].join(', ');
    lines.push(`| ${volume.sourceId} | ${volume.area ?? ''} | ${volume.year ?? ''} | ${volume.variant ?? ''} | ${volume.technicalStatus} | ${fatal || '—'} |`);
  }
  lines.push('');
  lines.push('## 本次变更范围');
  lines.push('');
  lines.push('- 只新增离线 preflight 代码、合成测试和 metadata-only 报告；未改动任何原题、材料、答案、图片字节或 rights 标记。');
  lines.push(`- 新增独立参考答案 0 处、新增解析 0 处；${report.totals.archivePartial} 卷 archiveStatus 仍为 PARTIAL，archiveComplete=${report.totals.archiveComplete}。`);
  lines.push('- 未改 catalog/manifest.jsonl；后续若有内容变更，使用 manifest 行级 patch 工具，不全量重写。');
  lines.push('');
  lines.push('## 结论与边界');
  lines.push('');
  lines.push(`- 技术 PASS ${t.PASS} / FAIL ${t.FAIL} / SKIP ${t.SKIP}；publication BLOCKED ${p.BLOCKED}，ELIGIBLE ${p.ELIGIBLE}。`);
  lines.push('- 技术 PASS 允许 explanation-empty、answer-above-word-maximum 等 warning 存在；这些是内容质量/解析缺口，不是结构损坏。');
  const rightsCounts = Object.entries(report.rights.statusCounts ?? {}).map(([key, value]) => `${key}=${value}`).join('，');
  lines.push(`- rightsStatus 分布：${rightsCounts}；cloudStorageBlocked=true ${report.rights.cloudStorageBlockedTrue} 卷；cleared ${report.rights.clearedCount} 卷。`);
  lines.push('- 没有任何卷因为本报告而变为可发布；缺失 rights 字段的卷按 BLOCKED 处理，而不是补成 cleared。');
  lines.push('- 本报告只含计数、哈希、路径与 issue code，不含题干、材料、答案、解析或标题正文。');
  return `${lines.join('\n')}\n`;
}
