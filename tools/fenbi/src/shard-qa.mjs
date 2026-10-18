#!/usr/bin/env node
/**
 * shard-qa.mjs — bounded, metadata-only QA for one assigned paper group.
 *
 * Inputs are JSON only:
 *   --spec    shard spec: paper identity + PR #72 aggregate counts + optional
 *             per-question alignment file.
 *   --inbox   a fenbi-browser-owner observation handoff (no credentials).
 *   --out     machine-readable result JSON.
 *   --md      human-readable report (numbers only; no stems/options/URLs/images).
 *
 * Exit codes:
 *   0  every paper verified and no open review item
 *   2  partial: at least one paper is blocked or needs review
 *   1  invalid input or a hard identity/count/SHA mismatch
 *
 * The checker never fetches anything, never reads browser state, and never
 * emits question text, options, image bytes, cookies, tokens, or practice URLs.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

export const EXIT = Object.freeze({ OK: 0, INVALID: 1, PARTIAL: 2 });
export const BLOCKED_TOKEN = 'BLOCKED_HOFF_OWNERS';
const SHA256_RE = /^[0-9a-f]{64}$/;

function readJson(file) {
  const text = fs.readFileSync(file, 'utf8');
  return { value: JSON.parse(text), sha256: sha256(text) };
}

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

function asString(value) {
  return value === null || value === undefined ? '' : String(value);
}

function sameIdentity(obs, spec) {
  return asString(obs.paperSourceId) === asString(spec.sourceId)
    && asString(obs.area) === asString(spec.area)
    && Number(obs.year) === Number(spec.year)
    && asString(obs.variant) === asString(spec.variant)
    && asString(obs.subject) === asString(spec.subject);
}

function imageChecks(images) {
  const errors = [];
  if (!Array.isArray(images)) return { errors: ['images-not-array'], count: 0, unique: 0 };
  const seen = new Set();
  for (const [i, img] of images.entries()) {
    const ref = asString(img?.ref) || `#${i}`;
    const sha = asString(img?.sha256);
    if (!SHA256_RE.test(sha)) errors.push(`bad-image-sha:${ref}`);
    if (seen.has(sha)) errors.push(`duplicate-image-sha:${ref}`);
    seen.add(sha);
  }
  return { errors, count: images.length, unique: seen.size };
}

function countChecks(spec) {
  const errors = [];
  const textUsable = Number(spec.textUsable);
  const imagePositions = Number(spec.imagePositions);
  const placeholders = Number(spec.placeholders);
  const verified = Number(spec.verified);
  const remaining = Number(spec.remaining);
  const weak = Number(spec.weak);
  const positions = Number(spec.positions);
  if (textUsable + imagePositions + placeholders !== positions) {
    errors.push('closure:positions');
  }
  if (verified + remaining + weak !== textUsable) {
    errors.push('closure:textUsable');
  }
  return { errors, values: { positions, textUsable, imagePositions, placeholders, verified, remaining, weak } };
}

function perQuestionChecks(rows, spec, perQuestion) {
  const errors = [];
  const warnings = [];
  if (!Array.isArray(rows)) return { errors: ['per-question-not-array'], stats: null };

  const positions = Number(spec.positions);
  if (rows.length !== positions) errors.push('per-question:row-count');

  const numbers = rows.map((r) => Number(r.sourceNumber)).sort((a, b) => a - b);
  const expectedNumbers = Array.from({ length: positions }, (_, i) => i + 1);
  if (numbers.length !== expectedNumbers.length || numbers.some((n, i) => n !== expectedNumbers[i])) {
    errors.push('per-question:number-set');
  }

  let matched = 0;
  let unmatched = 0;
  const unmatchedNumbers = [];
  const repoNumbers = new Set();
  const imageStats = { same: 0, different: 0, not_compared: 0, other: 0 };

  for (const row of rows) {
    if (row.status === 'matched') {
      matched += 1;
      const d = row.dimensions || {};
      for (const dim of ['number', 'stem', 'options', 'materials']) {
        if (d[dim]?.status !== 'same') errors.push(`per-question:${dim}:${row.sourceNumber}`);
      }
      if (d.qid?.status !== 'not_compared') errors.push(`per-question:qid:${row.sourceNumber}`);
      for (const dim of ['answer', 'explanation']) {
        if (d[dim]?.status !== 'unknown') errors.push(`per-question:${dim}:${row.sourceNumber}`);
      }
      if (row.repositoryNumber !== null && row.repositoryNumber !== undefined) {
        if (repoNumbers.has(row.repositoryNumber)) errors.push(`per-question:duplicate-repo-number:${row.repositoryNumber}`);
        repoNumbers.add(row.repositoryNumber);
      } else {
        errors.push(`per-question:missing-repo-number:${row.sourceNumber}`);
      }
      const imgStatus = d.images?.status;
      if (imgStatus in imageStats) imageStats[imgStatus] += 1;
      else imageStats.other += 1;
    } else if (row.status === 'unmatched') {
      unmatched += 1;
      unmatchedNumbers.push(Number(row.sourceNumber));
      if (!asString(row.reason)) errors.push(`per-question:unmatched-reason:${row.sourceNumber}`);
    } else {
      errors.push(`per-question:unknown-status:${row.sourceNumber}`);
    }
  }

  if (matched + unmatched !== rows.length) errors.push('per-question:status-closure');
  if (repoNumbers.size !== matched) errors.push('per-question:repo-number-count');

  if (perQuestion.expectedMatched !== undefined && matched !== Number(perQuestion.expectedMatched)) {
    errors.push(`per-question:expected-matched:${matched}`);
  }
  if (Array.isArray(perQuestion.expectedUnmatchedSourceNumbers)) {
    const want = perQuestion.expectedUnmatchedSourceNumbers.slice().sort((a, b) => a - b);
    const got = unmatchedNumbers.slice().sort((a, b) => a - b);
    if (JSON.stringify(want) !== JSON.stringify(got)) errors.push('per-question:expected-unmatched');
  }

  // PR #72 uses a content-only caliber; the explicit-number trial may report a
  // different verified count. Never reconcile them silently.
  if (matched !== Number(spec.verified)) {
    warnings.push(`caliber_conflict:per_question_matched=${matched}:pr72_verified=${spec.verified}`);
  }
  if (unmatched > 0) warnings.push(`unmatched_source_numbers=${unmatchedNumbers.join(',')}`);
  if (imageStats.different > 0) warnings.push(`image_dimension_different=${imageStats.different}`);

  return {
    errors,
    warnings,
    stats: {
      rows: rows.length,
      matched,
      unmatched,
      unmatchedSourceNumbers: unmatchedNumbers,
      repositoryNumbers: repoNumbers.size,
      images: imageStats,
    },
  };
}

function validatePaper(spec, observations, globalPermissions = {}) {
  const reasons = [];
  const warnings = [];
  const obs = observations.filter((o) => asString(o.paperSourceId) === asString(spec.sourceId));

  if (obs.length !== 1) {
    return {
      sourceId: asString(spec.sourceId),
      identity: 'invalid',
      status: 'invalid',
      reasons: [`observation-count:${obs.length}`],
      warnings,
      counts: null,
      perQuestion: null,
      images: null,
    };
  }

  const observation = obs[0];
  if (!sameIdentity(observation, spec)) reasons.push('identity-mismatch');
  if (Number(observation.questionCount) !== Number(spec.positions)) reasons.push('question-count-mismatch');
  if (observation.contentStatus !== 'observed') reasons.push('content-status');
  if (observation.route?.kind !== 'existing_practice') reasons.push('route-kind');
  if (observation.route?.urlObserved !== true) reasons.push('route-url-observed');
  if (observation.route?.contentStatus !== 'observed') reasons.push('route-content-status');
  if (observation.route?.imageContentOnly !== false) reasons.push('image-content-only');
  if (observation.rights?.redistribution !== 'local_only') reasons.push('rights-redistribution');
  const permissions = observation.permissions || globalPermissions;
  for (const key of ['browserProfile', 'cookies', 'tokens']) {
    if (permissions?.[key] !== false) reasons.push(`permission:${key}`);
  }

  const images = imageChecks(observation.images);
  reasons.push(...images.errors);
  const counts = countChecks(spec);
  reasons.push(...counts.errors);

  let perQuestion = null;
  if (spec.perQuestion) {
    // The input is resolved by the caller and injected as `spec.perQuestionRows`.
    if (spec.perQuestionReadError) {
      reasons.push(`per-question-read-error:${spec.perQuestionReadError}`);
    } else {
      const result = perQuestionChecks(spec.perQuestionRows, spec, spec.perQuestion);
      reasons.push(...result.errors);
      warnings.push(...result.warnings);
      perQuestion = result.stats;
    }
  }

  if (reasons.length > 0) {
    return {
      sourceId: asString(spec.sourceId),
      identity: reasons.includes('identity-mismatch') ? 'mismatch' : 'ok',
      status: 'invalid',
      reasons,
      warnings,
      counts: counts.values,
      perQuestion,
      images: { files: images.count, uniqueSha256: images.unique },
    };
  }

  if (!spec.perQuestion) {
    return {
      sourceId: asString(spec.sourceId),
      identity: 'ok',
      status: 'blocked',
      reasons: [`${BLOCKED_TOKEN}:per-question-shard-absent`],
      warnings,
      counts: counts.values,
      perQuestion: null,
      images: { files: images.count, uniqueSha256: images.unique },
    };
  }

  const status = warnings.length > 0 ? 'needs_review' : 'verified';
  return {
    sourceId: asString(spec.sourceId),
    identity: 'ok',
    status,
    reasons: [],
    warnings,
    counts: counts.values,
    perQuestion,
    images: { files: images.count, uniqueSha256: images.unique },
  };
}

export function runShardQA({ spec, inbox, cwd = process.cwd(), inputs = {} }) {
  if (spec?.kind !== 'gwy-zhenti-shard-spec' || !Array.isArray(spec.papers)) {
    return { exitCode: EXIT.INVALID, report: { error: 'invalid-spec' }, inputs };
  }
  if (!Array.isArray(inbox?.observations)) {
    return { exitCode: EXIT.INVALID, report: { error: 'invalid-inbox' }, inputs };
  }

  const papers = spec.papers.map((paper) => {
    const enriched = { ...paper };
    if (paper.perQuestion?.file) {
      const file = path.resolve(cwd, paper.perQuestion.file);
      try {
        const loaded = readJson(file);
        const rows = loaded.value?.[paper.perQuestion.key];
        enriched.perQuestionRows = rows;
        inputs.perQuestionFiles ??= {};
        inputs.perQuestionFiles[paper.sourceId] = {
          path: paper.perQuestion.file,
          sha256: loaded.sha256,
          key: paper.perQuestion.key,
        };
      } catch (error) {
        enriched.perQuestionRows = null;
        enriched.perQuestionReadError = error?.message || String(error);
      }
    }
    return validatePaper(enriched, inbox.observations, inbox.permissions || {});
  });

  const invalid = papers.filter((p) => p.status === 'invalid').length;
  const blocked = papers.filter((p) => p.status === 'blocked').length;
  const needsReview = papers.filter((p) => p.status === 'needs_review').length;
  const verified = papers.filter((p) => p.status === 'verified').length;
  const exitCode = invalid > 0 ? EXIT.INVALID : (blocked > 0 || needsReview > 0 ? EXIT.PARTIAL : EXIT.OK);

  const positions = papers.reduce((n, p) => n + (p.counts?.positions || 0), 0);
  const perQuestionRows = papers.reduce((n, p) => n + (p.perQuestion?.rows || 0), 0);
  const blockedPositions = papers
    .filter((p) => p.status === 'blocked')
    .reduce((n, p) => n + (p.counts?.positions || 0), 0);

  return {
    exitCode,
    report: {
      schemaVersion: 1,
      kind: 'gwy-zhenti-shard-qa-result',
      generatedAt: new Date().toISOString(),
      exitCode,
      summary: {
        papers: papers.length,
        verified,
        needsReview,
        blocked,
        invalid,
        positions,
        perQuestionRows,
        blockedPositions,
        officialVerification: false,
        note: 'normalized_equal/near is not official verification; image paths and ⟦IMAGE⟧ markers are not image evidence.',
      },
      papers,
    },
    inputs,
  };
}

export function renderMarkdown(result, inputs = {}, spec = {}) {
  const r = result.report;
  const lines = [];
  lines.push('# Shard QA — JS2025C / JS2024A / ZJ2026C（2026-10-18）');
  lines.push('');
  lines.push('**metadata-only**：不含题干、选项、答案正文、图片字节、Cookie、账号或练习 URL。');
  lines.push('本报告是分片 QA，不是官方原卷验真；`normalized_equal`/`near` 都不等于独立验真。');
  lines.push('');
  lines.push(`- exit: **${r.exitCode}**（0=全绿，2=partial/blocked，1=输入无效）`);
  lines.push(`- papers: ${r.summary.papers}；verified ${r.summary.verified}；needs_review ${r.summary.needsReview}；blocked ${r.summary.blocked}；invalid ${r.summary.invalid}`);
  lines.push(`- question positions: ${r.summary.positions}；per-question rows: ${r.summary.perQuestionRows}；blocked positions: ${r.summary.blockedPositions}`);
  lines.push(`- officialVerification: **false**`);
  lines.push('');
  lines.push('## 0. 结论');
  lines.push('');
  lines.push(`- 本批次仅对 **${r.summary.perQuestionRows} / ${r.summary.positions}** 个题位做了逐题核对；其余 **${r.summary.blockedPositions}** 个题位因缺合法逐题 shard 而 \`BLOCKED_HOFF_OWNERS\`。`);
  const zj = r.papers.find((p) => p.sourceId === '8399763' && p.perQuestion);
  if (zj) {
    lines.push(`- 浙江 8399763：${zj.perQuestion.matched} matched、${zj.perQuestion.unmatched} unmatched（${zj.perQuestion.unmatchedSourceNumbers.join(', ')}）；图片 same/different/not_compared = ${zj.perQuestion.images.same}/${zj.perQuestion.images.different}/${zj.perQuestion.images.not_compared}；answer/explanation 全部 unknown。`);
    lines.push('- 浙江的 109 matched 与 PR#72 的 102 verified 是**两套口径**，差 7 不合并；Q54 的严格自动结论是 unmatched，是否人工等价需 Owner 复核。');
  }
  lines.push('- PR#72 的 322 verified（106+114+102）、26 remaining、7 weak 仅为**聚合引用**，不是本次逐题复核结论。');
  lines.push(`- 真实 exit = **${r.exitCode}**（partial），不是全绿。`);
  lines.push('');
  lines.push('## 1. 分片结果');
  lines.push('');
  lines.push('| sourceId | 身份 | 状态 | 题位 | 逐题行 | matched | unmatched | 图片文件 | 原因/警告 |');
  lines.push('|---|---|---|---:|---:|---:|---:|---:|---|');
  for (const p of r.papers) {
    const reasons = [...p.reasons, ...p.warnings].join('; ') || '—';
    lines.push(`| ${p.sourceId} | ${p.identity} | ${p.status} | ${p.counts?.positions ?? '—'} | ${p.perQuestion?.rows ?? 0} | ${p.perQuestion?.matched ?? '—'} | ${p.perQuestion?.unmatched ?? '—'} | ${p.images?.files ?? '—'} | ${reasons} |`);
  }
  lines.push('');
  lines.push('## 2. PR #72 聚合口径（仅数字，未逐题复核）');
  lines.push('');
  lines.push('| sourceId | 题位 | 题干可用 | 含图题位 | 来源占位 | verified | remaining | weak |');
  lines.push('|---|---:|---:|---:|---:|---:|---:|---:|');
  for (const p of r.papers) {
    const c = p.counts || {};
    lines.push(`| ${p.sourceId} | ${c.positions ?? '—'} | ${c.textUsable ?? '—'} | ${c.imagePositions ?? '—'} | ${c.placeholders ?? '—'} | ${c.verified ?? '—'} | ${c.remaining ?? '—'} | ${c.weak ?? '—'} |`);
  }
  lines.push('');
  const withPerQ = r.papers.filter((p) => p.perQuestion);
  if (withPerQ.length > 0) {
    lines.push('## 3. 逐题证据（仅列出有 shard 的卷）');
    lines.push('');
    for (const p of withPerQ) {
      const q = p.perQuestion;
      lines.push(`### ${p.sourceId}`);
      lines.push('');
      lines.push(`- rows: **${q.rows}**；matched: **${q.matched}**；unmatched: **${q.unmatched}**（${q.unmatchedSourceNumbers.join(', ') || '—'}）`);
      lines.push(`- repository numbers unique: **${q.repositoryNumbers}**`);
      lines.push(`- images: same **${q.images.same}** / different **${q.images.different}** / not_compared **${q.images.not_compared}** / other **${q.images.other}**`);
      lines.push('- answer/explanation dimensions: **unknown**（源内容未观察）；qid: **not_compared**（命名空间不同）');
      if (q.matched !== (p.counts?.verified ?? q.matched)) {
        lines.push(`- **caliber conflict**: per-question matched ${q.matched} vs PR#72 verified ${p.counts?.verified}；两套口径不合并、不取平均。`);
      }
      if (q.unmatched > 0) {
        lines.push(`- **unmatched ${q.unmatchedSourceNumbers.join(', ')}**：保留为 needs_review，未推测内容。`);
      }
      if (q.images.different > 0) {
        lines.push(`- **image_dimension_different=${q.images.different}**：只表示字节/切分不同，不等于内容不同；未独立验真。`);
      }
      lines.push('');
    }
  }
  const blocked = r.papers.filter((p) => p.status === 'blocked');
  if (blocked.length > 0) {
    lines.push('## 4. 阻断（无合法逐题 shard）');
    lines.push('');
    lines.push(`以下卷**没有** Owner 落地且合法授权的逐题 fingerprint shard；` +
      `本次只核了卷级身份、题量、图片 SHA 格式与计数闭合，**没有**逐题 matched/weak 结论。`);
    lines.push('');
    for (const p of blocked) {
      lines.push(`- **${p.sourceId}**：${p.reasons.join('; ')}；题位 ${p.counts?.positions ?? '—'}，` +
        `PR#72 aggregate verified ${p.counts?.verified ?? '—'} / remaining ${p.counts?.remaining ?? '—'} / weak ${p.counts?.weak ?? '—'}（仅引用，未独立复核）。`);
    }
    lines.push('');
  }
  lines.push('## 5. 口径与边界');
  lines.push('');
  lines.push('- `matched` = 显式原号 + 内容对齐（live trial 口径）；`PR#72 verified` = 内容匹配口径。两套口径不可混用，差异保留为 `caliber_conflict`。');
  lines.push('- `image_dimension_different` 只表示图片字节/切分不同，不等于内容不同；未做独立原图验真。');
  lines.push('- 缺逐题 shard 的卷输出 `BLOCKED_HOFF_OWNERS`，不推测缺失题号、不把 sourceId 当抓取许可。');
  lines.push('- 本轮未访问粉笔、未开浏览器、未创建第 6 份练习、未答题/交卷/购买。');
  lines.push('');
  lines.push('## 6. 输入');
  lines.push('');
  if (spec.source) {
    lines.push(`- PR#72 head: \`${spec.source.pr72 || '—'}\``);
    lines.push(`- PR#75 head: \`${spec.source.pr75 || '—'}\``);
    lines.push(`- base (PR#20 head): \`${spec.source.base || '—'}\``);
    lines.push(`- inbox: \`${spec.source.inbox || '—'}\``);
  }
  if (inputs.inboxSha256) lines.push(`- inbox sha256: \`${inputs.inboxSha256}\``);
  if (inputs.specSha256) lines.push(`- spec sha256: \`${inputs.specSha256}\``);
  for (const [id, v] of Object.entries(inputs.perQuestionFiles || {})) {
    lines.push(`- per-question ${id}: \`${v.path}\` sha256 \`${v.sha256}\``);
  }
  if (spec.environment) {
    const e = spec.environment;
    lines.push(`- host: \`${e.host || '—'}\`；load: \`${e.load || '—'}\`；MemAvailable: \`${e.memAvailable || '—'}\`；swap used: \`${e.swapUsed || '—'}\`；PSI cpu/mem/io: \`${e.psi || '—'}\``);
  }
  lines.push('');
  lines.push('## 7. 复跑');
  lines.push('');
  lines.push('```bash');
  lines.push('cd tools/fenbi && node --test test/shard-qa.test.mjs');
  lines.push('cd ../.. && node tools/fenbi/src/shard-qa.mjs \\');
  lines.push('  --spec reports/shard-qa-20261018/spec.json \\');
  lines.push('  --inbox <safe-observations>/inbox/observations-batch-20261018-1437a2b44ed1.json \\');
  lines.push('  --out reports/shard-qa-20261018/result.json \\');
  lines.push('  --md reports/SHARD-QA-JS2025C-JS2024A-ZJ2026C-20261018.md');
  lines.push('```');
  return `${lines.join('\n')}\n`;
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith('--')) continue;
    args[key.slice(2)] = argv[i + 1];
    i += 1;
  }
  return args;
}

function main(argv) {
  const args = parseArgs(argv);
  if (!args.spec || !args.inbox) {
    console.error('usage: node src/shard-qa.mjs --spec <spec.json> --inbox <observations.json> [--out result.json] [--md report.md]');
    return EXIT.INVALID;
  }
  const spec = readJson(path.resolve(args.spec));
  const inbox = readJson(path.resolve(args.inbox));
  const inputs = { specSha256: spec.sha256, inboxSha256: inbox.sha256 };
  const { exitCode, report } = runShardQA({ spec: spec.value, inbox: inbox.value, inputs });
  const json = `${JSON.stringify(report, null, 2)}\n`;
  if (args.out) {
    fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
    fs.writeFileSync(path.resolve(args.out), json);
  } else {
    process.stdout.write(json);
  }
  if (args.md) {
    fs.mkdirSync(path.dirname(path.resolve(args.md)), { recursive: true });
    fs.writeFileSync(path.resolve(args.md), renderMarkdown({ report }, inputs, spec.value));
  }
  return exitCode;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = main(process.argv.slice(2));
}
