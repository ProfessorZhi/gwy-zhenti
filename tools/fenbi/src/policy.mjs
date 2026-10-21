#!/usr/bin/env node
/**
 * Fixed policy loader and behaviour helpers. policy.json is authoritative: callers read
 * enums from here instead of ad-hoc env strings. Unknown enums fail closed.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_POLICY_PATH = path.resolve(HERE, '../policy.json');

const ENUMS = {
  source_priority: ['fenbi'],
  replace: ['if_question_count_not_less', 'never'],
  stub: ['mark_missing_and_publish', 'block'],
  answer_conflict: ['use_fenbi_note_other', 'block'],
  storage: ['private_repo_approved'],
  refreshStubs: ['monthly', 'manual'],
  'reporting.cadence': ['daily'],
  'reporting.singleKpi': ['main_fenbi_verified_papers/catalog_unique_papers'],
  'publishing.cadence': ['daily'],
  'publishing.mode': ['pure_content_only'],
  'publishing.mergeWhenAllowed': ['auto_a', 'manual']
};
const EXCEPTION_ENUMS = {
  auth_failure: ['stop_notify'],
  captcha: ['stop_notify'],
  grade_c: ['repair_once_by_category', 'block'],
  fenbi_fewer: ['keep_existing_queue'],
  member_only: ['queue_user_decision'],
  unknown: ['ask_user_no_new_tool']
};

const TOP_KEYS = ['schemaVersion', 'source_priority', 'replace', 'stub', 'answer_conflict', 'storage', 'years', 'exceptionHandling', 'refreshStubs', 'reporting', 'engineering', 'publishing', 'legalRights'];
const LEGAL_KEYS = ['privateStorageUserConsentRecorded', 'publicRedistributionRequiresRightsHolderInstrument', 'note'];

export function validatePolicy (policy) {
  const errors = [];
  if (!policy || typeof policy !== 'object') return {ok: false, errors: ['policy-not-object']};
  if (policy.schemaVersion !== 1) errors.push('schema-version');
  for (const key of Object.keys(policy)) if (!TOP_KEYS.includes(key)) errors.push('unknown-key:' + key);
  for (const key of Object.keys(policy.legalRights ?? {})) if (!LEGAL_KEYS.includes(key)) errors.push('unknown-legalRights-key:' + key);
  for (const key of Object.keys(policy.exceptionHandling ?? {})) if (!(key in EXCEPTION_ENUMS)) errors.push('unknown-exceptionHandling-key:' + key);
  for (const [key, allowed] of Object.entries(ENUMS)) {
    const value = key.split('.').reduce((acc, part) => acc?.[part], policy);
    if (!allowed.includes(value)) errors.push(`enum:${key}`);
  }
  for (const [key, allowed] of Object.entries(EXCEPTION_ENUMS)) {
    if (!allowed.includes(policy.exceptionHandling?.[key])) errors.push(`enum:exceptionHandling.${key}`);
  }
  const years = policy.years ?? {};
  for (const scope of ['default', 'zhejiang']) {
    const range = years[scope];
    if (!Array.isArray(range) || range.length !== 2 || !range.every(Number.isInteger) || range[0] > range[1]) errors.push(`years:${scope}`);
  }
  const legal = policy.legalRights ?? {};
  if (legal.privateStorageUserConsentRecorded !== true) errors.push('legalRights:privateStorageUserConsentRecorded');
  if (legal.publicRedistributionRequiresRightsHolderInstrument !== true) errors.push('legalRights:publicRedistributionRequiresRightsHolderInstrument');
  for (const key of ['maxOpenCodePR', 'triggerNoGrowthHours', 'ttlHours']) {
    if (!Number.isInteger(policy.engineering?.[key]) || policy.engineering[key] < 0) errors.push(`engineering:${key}`);
  }
  return {ok: errors.length === 0, errors};
}

export async function loadPolicy (file = DEFAULT_POLICY_PATH) {
  let policy;
  try { policy = JSON.parse(await fs.readFile(file, 'utf8')); } catch (e) {
    throw Object.assign(new Error('policy-unreadable:' + (e.code || e.message)), {code: 'policy-unreadable'});
  }
  const verdict = validatePolicy(policy);
  if (!verdict.ok) throw Object.assign(new Error('policy-invalid:' + verdict.errors.join(',')), {code: 'policy-invalid', errors: verdict.errors});
  return Object.freeze(policy);
}

/** Strict env switch: only the string "1" enables replacement. */
export function isReplaceEnabled (value) {
  return value === '1';
}

const STUB = /题目正在全力以赴征集|网友未回忆起|题目缺失/u;
const QUESTION_HEAD = /^#{2,3}\s*第\s*(\d+)\s*题/gmu;

/** Count question positions and effective (non-stub) questions. */
export function countQuestions (markdown) {
  const md = String(markdown ?? '');
  const heads = [...md.matchAll(QUESTION_HEAD)];
  let effective = 0;
  for (let i = 0; i < heads.length; i++) {
    const start = heads[i].index + heads[i][0].length;
    const body = md.slice(start, heads[i + 1]?.index ?? md.length);
    if (!STUB.test(body)) effective++;
  }
  return {slots: heads.length, effective};
}

/**
 * Replacement guard: the new paper may not reduce effective question count, may not
 * reduce total slots, and identity/old-sha checks are the caller's responsibility.
 */
export function assertReplacementAllowed (policy, {priorMarkdown, newMarkdown}) {
  const rule = policy?.replace;
  if (rule === 'never') return {allowed: false, reasons: ['replace-disabled-by-policy']};
  if (rule !== 'if_question_count_not_less') return {allowed: false, reasons: ['policy-invalid:replace']};
  const prior = countQuestions(priorMarkdown);
  const next = countQuestions(newMarkdown);
  const reasons = [];
  if (next.effective < prior.effective) reasons.push('effective-question-count-decreased');
  if (next.slots < prior.slots) reasons.push('question-slot-count-decreased');
  return {allowed: reasons.length === 0, reasons, prior, next};
}

/**
 * Partial-source status for stubs. This is NOT grade A and never publishable as complete.
 */
export function classifyPartialSource (policy, {stubNumbers = [], optionsMissing = [], multiPart = [], totalSlots}) {
  if (policy?.stub !== 'mark_missing_and_publish') return {status: 'BLOCKED', publishable: false, reasons: ['stub-policy-block']};
  if (optionsMissing.length || multiPart.length) {
    return {status: 'BLOCKED', publishable: false, reasons: ['not-a-collection-stub']};
  }
  if (!stubNumbers.length) return {status: 'COMPLETE', publishable: false, reasons: ['no-stub']};
  return {
    status: 'PARTIAL_SOURCE_MISSING',
    slots: totalSlots,
    missingNumbers: [...new Set(stubNumbers)].sort((a, b) => a - b),
    publishable: false,
    completeness: 'partial',
    note: '原题缺失（粉笔与本库均无）；保留题位，不判定为完整 A'
  };
}

/**
 * Single KPI: verified source-backed papers on main / unique in-scope catalog papers.
 * Numerator requires mainSha + sourceId + subject + an independent QA/provenance binding.
 */
export function computeKpi ({mainSha, papers = [], catalog = null, policy, mainFileSha256ByPath = null, verifyQaAttestation = null}) {
  if (!mainSha || !/^[0-9a-f]{40}$/u.test(mainSha)) return {value: null, status: 'UNKNOWN', reason: 'main-sha-missing'};
  if (!Array.isArray(catalog)) return {value: null, status: 'UNKNOWN', reason: 'catalog-missing'};
  const years = policy?.years ?? {};
  const inScope = catalog.filter(row => {
    if (!row?.sourceId || !row?.subject) return false;
    const range = years[row.area === '浙江' || row.region === '浙江' ? 'zhejiang' : 'default'] ?? years.default;
    return !range || (Number.isInteger(row.year) && row.year >= range[0] && row.year <= range[1]);
  });
  const denominator = new Set(inScope.map(row => `${row.subject}:${row.sourceId}`)).size;
  if (denominator === 0) return {value: null, status: 'UNKNOWN', reason: 'catalog-empty'};
  // A caller-supplied array may claim anything. The numerator needs the real main blob
  // sha per paper plus a verifier for the independent QA attestation; otherwise UNKNOWN.
  const plausible = papers.filter(p => p?.mainSha === mainSha && p?.sourceId && p?.subject &&
    /^[0-9a-f]{64}$/u.test(p?.mainBlobSha256 ?? '') && p?.qa?.verdict === 'pass');
  if (!mainFileSha256ByPath || typeof verifyQaAttestation !== 'function') {
    return {
      value: null, status: 'UNKNOWN', reason: 'numerator-unverifiable',
      unverifiedNumerator: new Set(plausible.map(p => `${p.subject}:${p.sourceId}`)).size,
      denominator, mainSha
    };
  }
  const verified = plausible.filter(p => {
    const actual = mainFileSha256ByPath[p.path];
    if (!actual || actual !== p.mainBlobSha256) return false;
    try { return verifyQaAttestation(p) === true; } catch { return false; }
  });
  const numerator = new Set(verified.map(p => `${p.subject}:${p.sourceId}`)).size;
  return {value: numerator / denominator, numerator, denominator, status: 'OK', mainSha};
}

/** Same area/year/subject/variant with different sourceIds is an identity conflict. */
export function findIdentityConflicts (entries = []) {
  const byIdentity = new Map();
  for (const entry of entries) {
    if (!entry?.area || !Number.isInteger(entry.year) || !entry.subject || !entry.variant) continue;
    const key = [entry.area, entry.year, entry.subject, entry.variant].join('|');
    if (!byIdentity.has(key)) byIdentity.set(key, []);
    byIdentity.get(key).push(entry.sourceId ?? entry.path ?? null);
  }
  return [...byIdentity.entries()]
    .filter(([, ids]) => new Set(ids).size > 1)
    .map(([identity, ids]) => ({identity, sourceIds: [...new Set(ids)]}));
}
