import { readFile, realpath } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { load } from 'cheerio';
import { collectAssetUrls, htmlText } from './model.mjs';

const PLACEHOLDER = /^(?:暂无(?:解析|答案)?|待(?:补充|完善|填写)|查看(?:答案|解析)|答案略|解析略|略|TODO|PLACEHOLDER|参考答案|参考解析|点击查看)$/iu;
// A paid or unauthenticated exercise view renders an entitlement notice in the answer slot.
// Such a notice is not an observed answer, so it must never satisfy the answers/explanations
// dimension. Both bounds matter: a genuine answer can mention membership or permission, so only
// a short body in which the notice is essentially the whole content is named. This is a review
// trigger, not proof that the source is paywalled.
const ACCESS_GATE = /(?:登录|登陆|开通|购买|付费|升级|充值|续费|订阅|成为)[^。；;!?！？\n]{0,20}(?:后|即可|方可|才能|才可|可)[^。；;!?！？\n]{0,6}(?:查看|阅读|浏览|解锁|获取|显示|展开)|(?:暂无|没有|无)(?:查看|访问|阅读)?(?:的)?权限|权限不足|无权(?:查看|访问)/iu;
const EVASIVE_BODY_MAX_CHARS = 120;
const EVASIVE_RESIDUE_MAX_CHARS = 40;
const accessGate = (body) => {
  if (!body || body.length > EVASIVE_BODY_MAX_CHARS || !ACCESS_GATE.test(body)) return false;
  const residue = body.replace(new RegExp(ACCESS_GATE.source, 'giu'), '').replace(/[\s。；;，,、.:：!！?？"'“”‘’()（）]/gu, '');
  return residue.length <= EVASIVE_RESIDUE_MAX_CHARS;
};
const visible = (html) => { const $ = load(String(html ?? ''), null, false); $('script,style,noscript').remove(); return $.text().replace(/\s+/gu, '').trim(); };
const meaningful = (html) => { const body = visible(html); return Boolean(body && !PLACEHOLDER.test(body)); };
const htmlImage = (html) => /<(?:img|image)\b/iu.test(String(html ?? ''));
const content = (html) => meaningful(html) || htmlImage(html);
const answerBody = (html) => { const $ = load(String(html ?? ''), null, false); $('a,script,style,noscript').remove(); return $.text().replace(/\s+/gu, '').trim(); };
const within = (root, candidate) => { const relative = path.relative(root, candidate); return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative); };

function wordRules(requirements) {
  const value = visible(requirements);
  if (/(?:每(?:题|问|项|点|条|部分)|各(?:题|问|项|点)).{0,30}(?:字|字数)/u.test(value)) return { manual: true };
  const limits = [];
  for (const match of value.matchAll(/(?:不少于|至少|不低于)(\d+)字/gu)) limits.push({ minimum: Number(match[1]) });
  for (const match of value.matchAll(/(?:不超过|不多于|至多)(\d+)字|(\d+)字(?:以内|以下)/gu)) limits.push({ maximum: Number(match[1] ?? match[2]) });
  for (const match of value.matchAll(/(\d+)[—–\-~～至到]+(\d+)字/gu)) limits.push({ minimum: Number(match[1]), maximum: Number(match[2]) });
  for (const match of value.matchAll(/(\d+)字左右/gu)) limits.push({ minimum: Math.floor(Number(match[1]) * 0.8), maximum: Math.ceil(Number(match[1]) * 1.2) });
  if (!limits.length) return /字数不限/u.test(value) ? {} : { unknown: true };
  return { minimum: Math.max(0, ...limits.map((item) => item.minimum ?? 0)), maximum: Math.min(Infinity, ...limits.map((item) => item.maximum ?? Infinity)) };
}

function imageSize(bytes) {
  if (bytes.length >= 24 && bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
  if (bytes.length >= 10 && /GIF8[79]a/u.test(bytes.subarray(0,6).toString('ascii'))) return [bytes.readUInt16LE(6), bytes.readUInt16LE(8)];
  if (bytes.length > 4 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    let offset = 2;
    while (offset + 3 < bytes.length) {
      if (bytes[offset] !== 0xff) break;
      const marker = bytes[offset + 1];
      if (marker === 0xd9 || marker === 0xda) break;
      const size = bytes.readUInt16BE(offset + 2);
      if (size < 2 || offset + 2 + size > bytes.length) break;
      if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker) && size >= 7) return [bytes.readUInt16BE(offset + 7), bytes.readUInt16BE(offset + 5)];
      offset += size + 2;
    }
  }
  return null;
}

/**
 * Per-paper provenance: which dimension's content was actually observed, from where, and whether
 * every observed dimension hangs off one verified paper binding. Descriptive only — `validateDocument`
 * remains the gate, and an unverified binding already keeps the identity dimension partial.
 */
export function paperProvenance(doc = {}) {
  const evidence = Array.isArray(doc.evidence) ? doc.evidence : [];
  const has = (type) => evidence.some((item) => item.type === type);
  const binding = has('source-paper-identity') ? 'source-paper-identity'
    : has('source-question-id-order') ? 'source-question-id-order'
      : evidence.some((item) => item.type === 'operator-verified-source' && item.verified === true) ? 'operator-verified-source'
        : 'unverified';
  const body = has('dom-question-keys') ? 'dom-adapter'
    : evidence.some((item) => item.type === 'payload' && item.extractedQuestions > 0) ? 'observed-json' : 'not-observed';
  const answers = (doc.questions ?? []).filter((q) => meaningful(q.answerHtml)).length;
  const explanations = (doc.questions ?? []).filter((q) => meaningful(q.explanationHtml)).length;
  const downloaded = (doc.assets ?? []).filter((asset) => asset?.status === 'downloaded').length;
  const routeMismatch = evidence.find((item) => item.type === 'page-route-mismatch') ?? null;
  return { binding,
    sources: { questions: body, materials: (doc.materials ?? []).length ? body : 'not-observed',
      answers: answers ? 'observed' : 'not-observed', explanations: explanations ? 'observed' : 'not-observed',
      images: downloaded ? 'downloaded' : 'not-observed' },
    answersObserved: answers, explanationsObserved: explanations, imagesDownloaded: downloaded,
    pageLanded: evidence.find((item) => item.type === 'page-landed')?.url ?? null,
    routeMismatch: routeMismatch ? routeMismatch.reason : null,
    // Answers or explanations with no verified paper binding must never be reported as verified.
    consistent: routeMismatch === null && (!(answers || explanations) || binding !== 'unverified') };
}

export async function validateDocument(doc, { assetRoot } = {}) {
  const names = ['questions', 'materials', 'answers', 'explanations', 'images', 'identity'];
  const dimensions = Object.fromEntries(names.map((name) => [name, { status: 'complete' }]));
  const issues = [];
  const add = (dimension, code, message, extra = {}, blocked = false) => {
    if (dimensions[dimension].status !== 'blocked') dimensions[dimension].status = blocked ? 'blocked' : 'partial';
    issues.push({ code, message, dimension, ...extra });
  };
  if (!doc || doc.schemaVersion !== 1 || !Array.isArray(doc.questions) || !Array.isArray(doc.materials) || !Array.isArray(doc.assets) || [...doc.questions, ...doc.materials, ...doc.assets].some((item) => !item || typeof item !== 'object')) {
    return { status: 'blocked', dimensions: Object.fromEntries(names.map((name) => [name, { status: 'blocked' }])),
      issues: [{ code: 'invalid-document', message: 'Unsupported or malformed document' }], observed: {} };
  }
  const identity = doc.identity ?? {}, expected = doc.expected ?? {};
  for (const key of ['id', 'title', 'subject', 'year', 'area', 'variant']) if (identity[key] == null || String(identity[key]).trim() === '') add('identity', 'identity-unknown', `Identity field ${key} is unknown`, { field: key });
  if (!['xingce', 'shenlun'].includes(identity.subject)) add('identity', 'subject-unknown', 'Subject must be explicitly identified');
  if (!Number.isInteger(Number(identity.year)) || Number(identity.year) < 2016 || Number(identity.year) > new Date().getFullYear()) add('identity', 'year-invalid', 'Examination year is outside the supported range');
  try { if (!['https:', 'http:'].includes(new URL(doc.source?.url).protocol)) throw new Error(); } catch { add('identity', 'source-url-unknown', 'A valid source URL is required'); }
  if (!doc.source?.capturedAt || Number.isNaN(Date.parse(doc.source.capturedAt))) add('identity', 'capture-time-unknown', 'Capture timestamp is missing or invalid');
  for (const item of doc.evidence ?? []) if (['login-required', 'authentication-required', 'captcha', 'access-denied', 'blocked'].includes(item.type) || [401,403].includes(item.status)) add('identity', 'access-blocked', 'Authentication or access challenge was observed', {}, true);
  if ((doc.conflicts ?? []).length) add('questions', 'unresolved-conflict', 'Conflicting source values require review', { count: doc.conflicts.length });
  if ((doc.evidence ?? []).some((item) => item.type === 'rejected-paper-mismatch')) add('identity', 'paper-identity-mismatch', 'Another paper response was rejected; review capture routing');
  // The page held was not on the job's route: whatever was read did not come from the paper.
  if ((doc.evidence ?? []).some((item) => item.type === 'page-route-mismatch')) add('identity', 'page-route-mismatch', 'The captured page is not the paper this job targets; nothing was read from the intended route', {}, true);
  if ((doc.evidence ?? []).some((item) => item.type === 'unmatched-answer')) add('answers', 'unmatched-answer', 'Answer responses still lack a matching captured source question');
  if (!Number.isInteger(expected.questions) || expected.questions < 1) add('questions', 'question-count-unknown', 'Source-declared total question count is unknown');
  else if (expected.questions !== doc.questions.length) add('questions', 'question-count-mismatch', 'Observed question count differs from source declaration', { expected: expected.questions, actual: doc.questions.length });
  if (!doc.questions.length) add('questions', 'no-questions', 'No full question records were captured');
  const ids = new Set(), numbers = new Set(), materials = new Map();
  for (const material of doc.materials) {
    if (!material.id || materials.has(material.id)) add('materials', 'material-id-invalid', 'Material ID is missing or duplicated', { materialId: material.id });
    materials.set(material.id, material);
    if (!content(material.contentHtml)) add('materials', 'material-body-empty', 'Material has no source content', { materialId: material.id });
  }
  if (!Number.isInteger(expected.materials) || expected.materials < 0) add('materials', 'material-count-unknown', 'Source-declared material count is unknown');
  else if (expected.materials !== doc.materials.length) add('materials', 'material-count-mismatch', 'Observed materials differ from source declaration', { expected: expected.materials, actual: doc.materials.length });
  if (identity.subject === 'shenlun' && !doc.materials.length) add('materials', 'shenlun-materials-empty', 'Shenlun source materials are missing');
  for (const q of doc.questions) {
    const ref = { questionId: q.id, questionNumber: q.number };
    if (!q.id || ids.has(q.id)) add('questions', 'question-id-invalid', 'Source question ID is missing or duplicated', ref);
    ids.add(q.id);
    if (!Number.isInteger(q.number) || q.number < 1 || numbers.has(q.number)) add('questions', 'question-number-invalid', 'Original question number is unknown or duplicated; source IDs are not question numbers', ref);
    else numbers.add(q.number);
    if (!content(q.contentHtml)) add('questions', 'question-body-empty', 'Question has no complete source body', ref);
    if (!Array.isArray(q.materialIds)) add('materials', 'material-references-invalid', 'Question material references must be an array', ref);
    else {
      if (identity.subject === 'shenlun' && !q.materialIds.length) add('materials', 'material-reference-missing', 'Shenlun question has no source-material association', ref);
      for (const id of q.materialIds) if (!materials.has(id)) add('materials', 'material-reference-broken', 'Question references a missing material', { ...ref, materialId: id });
    }
    if ((!meaningful(q.answerHtml) || !answerBody(q.answerHtml)) && !htmlImage(q.answerHtml)) add('answers', 'answer-empty', 'Reference answer has no independent body', ref);
    if (/(?:正文待补|答案暂缺|此处(?:填写|展开)|\bTODO\b|\bPLACEHOLDER\b)/iu.test(answerBody(q.answerHtml))) add('answers', 'answer-placeholder', 'Reference answer contains an explicit drafting placeholder', ref);
    if ((!meaningful(q.explanationHtml) || !answerBody(q.explanationHtml)) && !htmlImage(q.explanationHtml)) add('explanations', 'explanation-empty', 'Explanation has no substantive body', ref);
    // A gate notice is text, so the non-empty checks above accept it. Name it explicitly.
    if (!htmlImage(q.answerHtml) && accessGate(visible(q.answerHtml))) add('answers', 'answer-access-gate', 'Answer slot shows an access or entitlement notice instead of an observed answer', ref);
    if (!htmlImage(q.explanationHtml) && accessGate(visible(q.explanationHtml))) add('explanations', 'explanation-access-gate', 'Explanation slot shows an access or entitlement notice instead of an observed explanation', ref);
    if (identity.subject === 'xingce') {
      const opts = Array.isArray(q.options) ? q.options : [];
      if (opts.length < 2) add('questions', 'options-missing', 'Choice question has fewer than two options', ref);
      const labels = opts.map((o) => String(o.label ?? '').trim());
      if (labels.some((label) => !/^[A-Z]$/u.test(label)) || new Set(labels).size !== labels.length) add('questions', 'option-label-invalid', 'Option labels are missing, duplicated, or unsupported', ref);
      for (const option of opts) if (!content(option.contentHtml)) add('questions', 'option-body-empty', 'Option has no source content', { ...ref, option: option.label });
      const answer = htmlText(q.answerHtml).replace(/\s+/gu, '').toUpperCase();
      const selected = /^[A-Z](?:[,、;]?[A-Z])*$/u.test(answer) ? answer.replace(/[,、;]/gu, '').split('') : [];
      if (!selected.length || new Set(selected).size !== selected.length || selected.some((label) => !labels.includes(label))) add('answers', 'answer-option-mismatch', 'Answer must explicitly match existing option labels; numeric encodings are not guessed', ref);
    } else if (identity.subject === 'shenlun') {
      if (!meaningful(q.requirementsHtml)) add('questions', 'requirements-empty', 'Shenlun requirements and word limits need source verification', ref);
      if (meaningful(q.answerHtml) && (answerBody(q.answerHtml).length < 30 || /^(?:写作提纲|答题思路|参考答案|参考范文)\s*[:：]?\s*$/u.test(answerBody(q.answerHtml)))) add('answers', 'answer-body-unverified', 'A heading, short note, or outline is not a verified full reference answer', ref);
      const rules = wordRules(q.requirementsHtml), length = answerBody(q.answerHtml).length;
      if (rules.manual || rules.unknown) add('questions', rules.manual ? 'word-limits-manual-review' : 'word-limits-unknown', 'Source word limits could not be fully verified by the supported rules', ref);
      if (Number.isFinite(rules.minimum) && length < rules.minimum) add('answers', 'answer-below-word-minimum', 'Reference body is shorter than the source requirement', { ...ref, characters: length, minimum: rules.minimum });
      if (Number.isFinite(rules.maximum) && length > rules.maximum) add('answers', 'answer-above-word-maximum', 'Reference body exceeds the source requirement', { ...ref, characters: length, maximum: rules.maximum });
    }
  }
  if (Number.isInteger(expected.questions) && expected.questions > 10000) add('questions', 'question-count-unreasonable', 'Declared count exceeds the supported per-paper bound');
  const declaredNumbers = Array.isArray(expected.questionNumbers) ? expected.questionNumbers : Number.isInteger(expected.questions) && expected.questions > 0 && expected.questions <= 10000 ? Array.from({ length: expected.questions }, (_, i) => i + 1) : null;
  if (declaredNumbers && (declaredNumbers.length !== new Set(declaredNumbers).size || declaredNumbers.some((n) => !Number.isInteger(n) || n < 1) || declaredNumbers.length !== numbers.size || declaredNumbers.some((n) => !numbers.has(n)))) add('questions', 'question-number-set-mismatch', 'Original question numbers do not match expected positions');
  if (Array.isArray(expected.materialIds) && (expected.materialIds.length !== new Set(expected.materialIds).size || expected.materialIds.length !== materials.size || expected.materialIds.some((id) => !materials.has(id)))) add('materials', 'material-id-set-mismatch', 'Captured materials do not match declared IDs');
  let matchingSourceIdSet = false;
  for (const evidence of doc.evidence ?? []) if (evidence.type === 'source-question-id-order') {
    const declared = evidence.questionIds;
    if (!Array.isArray(declared) || declared.some((id) => id == null || String(id) === '')
      || new Set(declared.map(String)).size !== declared.length || declared.length !== ids.size
      || declared.some((id) => !ids.has(String(id)))) {
      add('questions', 'source-question-id-set-mismatch', 'Captured source IDs do not match the paper-declared ID set; this does not verify original numbering');
    } else if (declared.length > 0) matchingSourceIdSet = true;
  }
  const matchingPaper = (doc.evidence ?? []).some((item) => item.type === 'source-paper-identity' && String(item.paperId) === String(identity.id));
  const operatorVerified = (doc.evidence ?? []).some((item) => item.type === 'operator-verified-source'
    && String(item.paperId) === String(identity.id) && item.url === doc.source?.url && item.verified === true);
  if (!matchingPaper && !matchingSourceIdSet && !operatorVerified) add('identity', 'paper-binding-unverified', 'No matching source paper ID, paper-declared question ID set, or explicit verified source mapping binds these questions to this paper');
  const urls = collectAssetUrls(doc);
  const htmlFields = [...doc.materials.map((m) => m.contentHtml), ...(Array.isArray(doc.chapters) ? doc.chapters.map(chapter => chapter.instructionsHtml) : []), ...doc.questions.flatMap((q) => [q.contentHtml, q.answerHtml, q.explanationHtml, q.requirementsHtml, ...(Array.isArray(q.options) ? q.options.map((o) => o.contentHtml) : [])])];
  for (const html of htmlFields) {
    const $ = load(String(html ?? ''), null, false);
    if ($('[data-capture-rejected-reference]').length) add('images', 'reference-removed-for-privacy', 'A sensitive or unsupported source reference was removed; content needs review');
    $('img, image').each((_, element) => {
      const src = $(element).attr('src') || $(element).attr('data-src') || $(element).attr('href') || $(element).attr('xlink:href');
      try { if (!src || !['http:', 'https:'].includes(new URL(src, doc.source.url).protocol)) throw new Error(); }
      catch { add('images', 'image-reference-invalid', 'Image uses a missing or unsupported source; inline data also needs explicit validation'); }
    });
  }
  const assetUrls = new Set();
  let verifiedImages = 0;
  let canonicalRoot = null;
  if (assetRoot) try { canonicalRoot = await realpath(assetRoot); } catch { add('images', 'asset-root-invalid', 'Asset root does not exist', {}, true); }
  for (const asset of doc.assets) {
    if (assetUrls.has(asset.url)) add('images', 'asset-duplicate', 'Duplicate asset manifest entry', { url: asset.url });
    assetUrls.add(asset.url);
    if (asset.status !== 'downloaded' || !asset.localPath || !asset.sha256 || !Number.isInteger(asset.bytes) || asset.bytes < 1 || !(asset.width > 0 && asset.height > 0)) {
      add('images', 'asset-incomplete', 'Asset lacks successful download metadata', { url: asset.url }); continue;
    }
    if (!canonicalRoot) { add('images', 'asset-unverified', 'Asset bytes cannot be verified without an asset root', { url: asset.url }); continue; }
    const candidate = path.resolve(canonicalRoot, asset.localPath);
    if (!within(canonicalRoot, candidate)) { add('images', 'asset-path-outside-root', 'Asset path escapes the allowed root', { url: asset.url }, true); continue; }
    try {
      const actualPath = await realpath(candidate);
      if (!within(canonicalRoot, actualPath)) { add('images', 'asset-path-outside-root', 'Asset symlink escapes the allowed root', { url: asset.url }, true); continue; }
      const bytes = await readFile(actualPath);
      const digest = createHash('sha256').update(bytes).digest('hex');
      const size = imageSize(bytes);
      const decodeBound = asset.decoded === true && asset.decode?.method === 'browser-image-decode'
        && asset.decode.sha256 === digest && asset.decode.width === asset.width && asset.decode.height === asset.height;
      if (bytes.length !== asset.bytes || digest !== asset.sha256 || (size && (size[0] !== asset.width || size[1] !== asset.height)) || (!size && !decodeBound)) add('images', 'asset-integrity-failed', 'Asset bytes, hash, format, or dimensions do not match', { url: asset.url });
      else {
        verifiedImages++;
        if (!decodeBound) add('images', 'asset-decode-unverified', 'Header integrity passed; a complete decode bound to these exact bytes is still required', { url: asset.url });
      }
    } catch { add('images', 'asset-read-failed', 'Asset file is missing or unreadable', { url: asset.url }); }
  }
  for (const url of urls) if (!assetUrls.has(url)) add('images', 'asset-reference-missing', 'Referenced image has no local manifest entry', { url });
  const status = Object.values(dimensions).some((d) => d.status === 'blocked') ? 'blocked' : Object.values(dimensions).some((d) => d.status !== 'complete') ? 'partial' : 'complete';
  return { status, dimensions, issues, observed: { questions: doc.questions.length, materials: doc.materials.length, answers: doc.questions.filter((q) => meaningful(q.answerHtml)).length,
    explanations: doc.questions.filter((q) => meaningful(q.explanationHtml)).length, imageReferences: urls.length, assets: doc.assets.length, verifiedImageHeaders: verifiedImages } };
}
