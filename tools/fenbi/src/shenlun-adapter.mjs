// Shenlun (essay) adapter — normalised schema, deterministic parser/renderer/validator.
//
// Design constraints (deliberate):
//   * shenlun has NO A-D options; the xingce option/label gates must never apply.
//   * absence is a first-class value: every node carries state
//       'observed' | 'absent' (source explicitly has none) | 'unknown' (not shown)
//     A missing explanation is normal, not a failure. Nothing here ever generates
//     answer or explanation text.
//   * an empty material/question body is only legal when the source declares it
//     empty; otherwise it is a defect.
//   * publishing is blocked by default: rightsStatus defaults to 'unverified' and
//     cloudStorageBlocked to true. assertCloudPublishable() throws for any real
//     shenlun paper without a cleared rights record.
//
// Offline only. Nothing here reads a browser, a network, a profile or a cache.

import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';

export const SHENLUN_SCHEMA_VERSION = 1;
export const SHENLUN_SUBJECT = 'shenlun';
export const STATES = Object.freeze(['observed', 'absent', 'unknown']);
export const OBSERVED = 'observed';
export const ABSENT = 'absent';
export const UNKNOWN = 'unknown';

const TAG = /<[^>]+>/gu;
const IMG = /<img\b[^>]*?\bsrc\s*=\s*"([^"]+)"/giu;
const SHA256 = /^[0-9a-f]{64}$/u;

export class ShenlunError extends Error {
  constructor(code, detail = '') {
    super(detail ? `${code}: ${detail}` : code);
    this.code = code;
    this.detail = detail;
  }
}

const fail = (code, detail) => { throw new ShenlunError(code, detail); };
const str = (v) => (v == null ? '' : String(v));
export const visible = (html) => str(html).replace(TAG, ' ').replace(/\s+/gu, ' ').trim();
export const images = (html) => [...str(html).matchAll(IMG)].map((m) => m[1]);
export const sha256Text = (s) => createHash('sha256').update(str(s), 'utf8').digest('hex');
export const sha256Document = (doc) => sha256Text(JSON.stringify(doc, sortKeys));

function sortKeys(_k, v) {
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    return Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]]));
  }
  return v;
}

const stateOf = (node, fallback) => (STATES.includes(node?.state) ? node.state : fallback);

/** Normalise S1's structural metadata into the shenlun document schema. */
export function parseShenlun(source = {}, { expected = {} } = {}) {
  const ident = source.identity ?? {};
  if (ident.subject !== SHENLUN_SUBJECT) fail('not-shenlun', str(ident.subject));
  for (const key of ['area', 'year', 'variant', 'sourceId']) {
    if (ident[key] == null || str(ident[key]).trim() === '') fail('identity-incomplete', key);
  }

  const paperId = source.paperId ?? null;
  if (paperId != null && str(paperId) !== str(ident.sourceId)) fail('paper-id-mismatch', `${paperId} != ${ident.sourceId}`);
  if (expected.sourceId != null && str(expected.sourceId) !== str(ident.sourceId)) fail('expected-source-id-mismatch');

  const sourceSha = source.sourceSha ?? null;
  if (sourceSha != null && !SHA256.test(str(sourceSha))) fail('source-sha-malformed');
  if (expected.sourceSha != null && str(expected.sourceSha) !== str(sourceSha)) fail('source-sha-mismatch');
  if (expected.documentSha != null && expected.documentSha !== sha256Document(source)) fail('document-sha-mismatch');

  // ---- materials: 0..n, order preserved
  const materials = [];
  const matIds = new Set();
  (source.materials ?? []).forEach((m, i) => {
    const mid = str(m?.materialId);
    if (!mid) fail('material-id-missing', `index ${i}`);
    if (matIds.has(mid)) fail('duplicate-material-id', mid);
    matIds.add(mid);
    const body = str(m.contentHtml);
    let state = stateOf(m, UNKNOWN);
    if (!visible(body)) {
      if (state !== ABSENT) fail('material-body-missing', mid);   // empty only if declared empty
      state = ABSENT;
    } else {
      state = OBSERVED;
    }
    materials.push({
      order: i, materialId: mid, contentHtml: body, text: visible(body), state,
      assets: images(body).map((src) => ({ src })),
      provenance: m.provenance ?? { source: 'fenbi', kind: 'observed_ui' },
    });
  });

  // ---- questions: 1..n (never assume a fixed count); no options field
  const questions = [];
  const qids = new Set();
  const orders = new Set();
  (source.questions ?? []).forEach((q, i) => {
    const qid = str(q?.questionId);
    if (!qid) fail('question-id-missing', `index ${i}`);
    if (qids.has(qid)) fail('duplicate-question-key', qid);
    qids.add(qid);
    const order = Number.isInteger(q.order) ? q.order : i;
    if (orders.has(order)) fail('duplicate-question-order', String(order));
    orders.add(order);
    const prompt = str(q.promptHtml);
    let state = stateOf(q, UNKNOWN);
    if (!visible(prompt)) {
      if (state !== ABSENT) fail('question-prompt-missing', qid);
    } else {
      state = OBSERVED;
    }
    questions.push({
      order, questionId: qid, sourceId: str(ident.sourceId),
      promptHtml: prompt, promptText: visible(prompt),
      requirementsHtml: str(q.requirementsHtml),
      wordLimit: q.wordLimit ?? null, marks: q.marks ?? null,
      tasks: [...(q.tasks ?? [])], materialIds: [...(q.materialIds ?? [])], state,
    });
  });
  questions.sort((a, b) => a.order - b.order);

  // ---- reference answers: per question, may be absent/unknown
  const answers = new Map();
  for (const a of source.referenceAnswers ?? []) {
    const qid = str(a?.questionId);
    if (!qids.has(qid)) fail('answer-for-unknown-question', qid);
    if (answers.has(qid)) fail('duplicate-answer-key', qid);
    const body = str(a.answerHtml);
    const imgs = [...(a.answerImages ?? [])];
    // explicit state wins; otherwise presence means observed, absence means unknown
    const state = STATES.includes(a.state) ? a.state : (visible(body) || imgs.length ? OBSERVED : UNKNOWN);
    if (state === OBSERVED && !(visible(body) || imgs.length)) fail('answer-observed-but-empty', qid);
    answers.set(qid, {
      questionId: qid,
      answerHtml: state === OBSERVED ? body : '',
      answerImages: state === OBSERVED ? imgs : [],
      state,
      sha256: state === OBSERVED && body ? sha256Text(body) : null,
      provenance: a.provenance ?? { source: 'fenbi', kind: 'observed_ui' },
    });
  }
  const referenceAnswers = questions.filter((q) => answers.has(q.questionId))
    .map((q) => answers.get(q.questionId));

  // ---- explanations: absent is normal, never a failure
  const explanations = [];
  for (const e of source.explanations ?? []) {
    const qid = str(e?.questionId);
    if (!qids.has(qid)) fail('explanation-for-unknown-question', qid);
    explanations.push({
      questionId: qid, sourceText: str(e.sourceText), video: Boolean(e.video),
      topic: e.topic ?? null, state: stateOf(e, UNKNOWN),
    });
  }

  const identity = {
    area: ident.area,
    year: Number.isInteger(ident.year) ? ident.year : (str(ident.year).match(/^\d+$/u) ? Number(ident.year) : ident.year),
    subject: SHENLUN_SUBJECT,
    variant: ident.variant,
    sourceId: str(ident.sourceId),
    paperId: paperId == null ? null : str(paperId),
    sourceSha,
    observedAt: source.observedAt ?? null,
    // publishing is blocked unless the caller supplies a cleared record
    rightsStatus: source.rightsStatus ?? 'unverified',
    cloudStorageBlocked: source.cloudStorageBlocked ?? true,
  };

  const doc = {
    schemaVersion: SHENLUN_SCHEMA_VERSION,
    identity, materials, questions, referenceAnswers, explanations,
  };
  doc.coverage = coverage(doc);
  return doc;
}

/** Per-field completeness. `absent` is known; `unknown` is not. */
export function coverage(doc) {
  const mats = doc.materials ?? [];
  const qs = doc.questions ?? [];
  const ans = new Map((doc.referenceAnswers ?? []).map((a) => [a.questionId, a]));
  const exp = new Map((doc.explanations ?? []).map((e) => [e.questionId, e]));
  const tally = (values) => {
    const out = { observed: 0, absent: 0, unknown: 0 };
    for (const v of values) out[STATES.includes(v) ? v : UNKNOWN] += 1;
    return out;
  };
  const matStates = tally(mats.map((m) => m.state));
  const promptStates = tally(qs.map((q) => q.state));
  const ansStates = tally(qs.map((q) => (ans.get(q.questionId)?.state ?? UNKNOWN)));
  const expStates = tally(qs.map((q) => (exp.get(q.questionId)?.state ?? UNKNOWN)));
  const complete = qs.length > 0 && promptStates.unknown === 0 && matStates.unknown === 0
    && ansStates.unknown === 0 && expStates.unknown === 0;
  return {
    materials: matStates, prompts: promptStates,
    referenceAnswers: ansStates, explanations: expStates,
    complete, explanationsRequired: false,
  };
}

/** Deterministic Markdown; preserves order, paragraph boundaries and images. */
export function renderShenlunMarkdown(doc) {
  const id = doc.identity;
  const out = [`# ${id.area} ${id.year} ${id.subject} ${id.variant}`, '',
    `> sourceId ${id.sourceId} · rightsStatus ${id.rightsStatus}`, ''];
  for (const m of doc.materials) {
    out.push(`## 材料 ${m.materialId}`, '');
    out.push(m.state === ABSENT ? '<!-- source-empty: material body not provided by source -->' : m.contentHtml, '');
  }
  for (const q of doc.questions) {
    out.push(`## 第 ${q.order + 1} 题`, '', q.promptHtml, '');
    if (q.requirementsHtml) out.push(q.requirementsHtml, '');
    if (q.wordLimit != null) out.push(`<!-- wordLimit ${q.wordLimit} -->`);
    if (q.marks != null) out.push(`<!-- marks ${q.marks} -->`);
    for (const t of q.tasks) out.push(`<!-- task ${t} -->`);
    out.push('');
  }
  for (const a of doc.referenceAnswers) {
    out.push(`### 参考作答 ${a.questionId}`, '');
    if (a.state === OBSERVED) {
      if (a.answerHtml) out.push(a.answerHtml, '');
      for (const src of a.answerImages) out.push(`<img src="${src}" />`, '');
    } else {
      out.push(`<!-- source-${a.state}: no reference answer observed -->`, '');
    }
  }
  for (const e of doc.explanations) {
    if (e.state === ABSENT) out.push(`<!-- explanation-absent: ${e.questionId} -->`);
    else if (e.video) out.push(`<!-- explanation-video: ${e.questionId} -->`);
    else if (e.state === OBSERVED) out.push(e.sourceText);
  }
  return `${out.join('\n').replace(/\n+$/u, '')}\n`;
}

/** Verify declared image assets against files under `root`. Never repairs. */
export function assessAssets(assets = [], root) {
  const problems = [];
  let verified = 0;
  for (const a of assets) {
    const ref = str(a?.ref);
    const want = str(a?.sha256);
    if (!SHA256.test(want)) { problems.push({ code: 'asset-sha-malformed', ref }); continue; }
    if (!ref || ref.split('/').includes('..') || path.isAbsolute(ref)) {
      problems.push({ code: 'asset-ref-invalid', ref }); continue;
    }
    const file = path.resolve(root, ref);
    if (!file.startsWith(path.resolve(root) + path.sep)) { problems.push({ code: 'asset-ref-invalid', ref }); continue; }
    let st;
    try { st = statSync(file); } catch { problems.push({ code: 'asset-missing', ref }); continue; }
    if (!st.isFile()) { problems.push({ code: 'asset-missing', ref }); continue; }
    const got = createHash('sha256').update(readFileSync(file)).digest('hex');
    if (got !== want) { problems.push({ code: 'asset-sha-mismatch', ref }); continue; }
    verified += 1;
  }
  return { ok: problems.length === 0, verified, problems };
}

/** Structural validation. Deliberately does not require options or explanations. */
export function validateShenlun(doc = {}) {
  const problems = [];
  const bad = (code, ev = {}) => problems.push({ code, ...ev });
  if (doc.identity?.subject !== SHENLUN_SUBJECT) bad('subject-not-shenlun');
  if (!(doc.questions ?? []).length) bad('no-questions');
  if (!(doc.materials ?? []).length) bad('no-materials');

  const qids = (doc.questions ?? []).map((q) => q.questionId);
  if (new Set(qids).size !== qids.length) bad('duplicate-question-key');
  const orders = (doc.questions ?? []).map((q) => q.order);
  if (JSON.stringify(orders) !== JSON.stringify([...orders].sort((a, b) => a - b))) bad('order-not-preserved');
  if (new Set(orders).size !== orders.length) bad('duplicate-question-order');

  const matIds = new Set((doc.materials ?? []).map((m) => m.materialId));
  for (const q of doc.questions ?? []) {
    for (const mid of q.materialIds ?? []) {
      if (!matIds.has(mid)) bad('material-link-broken', { questionId: q.questionId, materialId: mid });
    }
    if (q.options) bad('options-present-in-shenlun', { questionId: q.questionId });
  }
  for (const a of doc.referenceAnswers ?? []) {
    if (!qids.includes(a.questionId)) bad('answer-for-unknown-question', { questionId: a.questionId });
    if (a.state === OBSERVED && !(visible(a.answerHtml) || (a.answerImages ?? []).length)) {
      bad('answer-observed-but-empty', { questionId: a.questionId });
    }
    for (const src of a.answerImages ?? []) if (!src) bad('answer-image-without-ref', { questionId: a.questionId });
  }
  const cov = coverage(doc);
  if (!cov.complete) bad('coverage-incomplete', { coverage: cov });
  return { ok: problems.length === 0, problems, coverage: cov };
}

/**
 * Publishing gate. Real shenlun content may only leave Dell when the rights record
 * has been explicitly cleared AND cloud storage is explicitly unblocked.
 */
export function assertCloudPublishable(doc = {}) {
  const id = doc.identity ?? {};
  if (id.subject !== SHENLUN_SUBJECT) fail('not-shenlun');
  if (id.rightsStatus === 'cleared' && id.cloudStorageBlocked === false) return true;
  fail('shenlun-cloud-blocked',
    id.rightsStatus === 'cleared' ? 'cloudStorageBlocked-not-lifted' : 'rightsStatus-unverified');
}

/** Guard so the xingce path can never be handed a shenlun document. */
export function assertXingceDocument(doc = {}) {
  if (doc.identity?.subject === SHENLUN_SUBJECT) fail('shenlun-in-xingce-path');
  return true;
}
