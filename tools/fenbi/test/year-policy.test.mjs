import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { createDocument } from '../src/model.mjs';
import { validateDocument } from '../src/validate.mjs';
import { promoteAll } from '../src/promote-all.mjs';
import {
  MIN_MODERN_YEAR, DEFAULT_FLOOR, yearFloor, yearCeiling, yearAllowed, targetPathAllowed,
} from '../src/year-policy.mjs';

/**
 * Year admission: Zhejiang's genuinely captured historical papers (2008–2015) must not be
 * graded C merely for predating 2016, while every other area keeps the original 2016 floor.
 * All fixtures are synthetic; no captured content or source metadata is embedded here.
 */

const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const NOW = new Date('2026-10-20T00:00:00Z');

// ── policy unit tests ───────────────────────────────────────────────────────

test('Zhejiang admits historical years, every other area keeps the 2016 floor', () => {
  assert.equal(yearFloor({ area: '浙江' }), MIN_MODERN_YEAR);
  assert.equal(yearFloor({ area: '江苏' }), DEFAULT_FLOOR);
  assert.equal(yearFloor({}), DEFAULT_FLOOR);
  assert.equal(yearCeiling(NOW), 2026);
});

test('Zhejiang 2008 and 2015 are admitted for both subjects', () => {
  for (const year of [2008, 2015]) {
    for (const subject of ['xingce', 'shenlun']) {
      assert.equal(yearAllowed({ area: '浙江', year, subject }, NOW), true, `${year}/${subject}`);
    }
  }
});

test('other areas still reject 2015 and admit 2016', () => {
  assert.equal(yearAllowed({ area: '江苏', year: 2015 }, NOW), false);
  assert.equal(yearAllowed({ area: '江苏', year: 2016 }, NOW), true);
  assert.equal(yearAllowed({ area: '国考', year: 2008 }, NOW), false);
});

test('future and pre-modern years are rejected everywhere', () => {
  assert.equal(yearAllowed({ area: '浙江', year: 2027 }, NOW), false);
  assert.equal(yearAllowed({ area: '江苏', year: 2027 }, NOW), false);
  assert.equal(yearAllowed({ area: '浙江', year: 1899 }, NOW), false);
});

test('an unknown or malformed year is rejected', () => {
  for (const year of [undefined, null, '', '  ', '2008年', 2008.5, NaN]) {
    assert.equal(yearAllowed({ area: '浙江', year }, NOW), false, String(year));
  }
});

test('target paths: Zhejiang may use 19xx, others stay 20xx', () => {
  assert.equal(targetPathAllowed('省考/浙江/2008/行测-统考.md', '浙江', NOW), true);
  assert.equal(targetPathAllowed('省考/浙江/2015/申论-A类.md', '浙江', NOW), true);
  assert.equal(targetPathAllowed('省考/江苏/2015/行测-统考.md', '江苏', NOW), false);
  assert.equal(targetPathAllowed('省考/江苏/2016/行测-统考.md', '江苏', NOW), true);
  assert.equal(targetPathAllowed('省考/浙江/2027/行测-A类.md', '浙江', NOW), false);
  assert.equal(targetPathAllowed('省考/浙江/2008/行测-统考.txt', '浙江', NOW), false);
  assert.equal(targetPathAllowed('../../../etc/passwd', '浙江', NOW), false);
});

// ── validateDocument integration ────────────────────────────────────────────

function doc({ area = '浙江', year = 2008, subject = 'xingce' } = {}) {
  const d = createDocument({ id: `synthetic-${year}`, title: '合成卷', subject, year, area, variant: '统考' },
    { url: 'https://www.fenbi.com/spa/tiku/synthetic', capturedAt: new Date().toISOString() });
  d.expected.questions = 1;
  d.evidence.push({ type: 'source-paper-identity', paperId: `synthetic-${year}`, url: d.source.url });
  d.questions = [{ id: 'q1', number: 1, contentHtml: '<p>合成题干。</p>',
    options: [{ label: 'A', contentHtml: '甲' }, { label: 'B', contentHtml: '乙' }],
    materialIds: [], answerHtml: 'B', explanationHtml: '合成解析。', requirementsHtml: '' }];
  return d;
}

const identityIssueCodes = verdict => verdict.issues.filter(i => i.dimension === 'identity').map(i => i.code);

test('validateDocument does not flag Zhejiang 2008 as year-invalid', async () => {
  const v = await validateDocument(doc({ area: '浙江', year: 2008 }));
  assert.ok(!identityIssueCodes(v).includes('year-invalid'), identityIssueCodes(v).join(','));
});

test('validateDocument does not flag Zhejiang 2015 shenlun as year-invalid', async () => {
  const d = doc({ area: '浙江', year: 2015, subject: 'shenlun' });
  d.questions[0].options = [];
  d.questions[0].requirementsHtml = '<p>作答要求。</p>';
  const v = await validateDocument(d);
  assert.ok(!identityIssueCodes(v).includes('year-invalid'), identityIssueCodes(v).join(','));
});

test('Zhejiang 2015 shenlun passes the year gate but still needs its own source evidence', async () => {
  // A historical year is not a free pass: shenlun still has to carry materials, task
  // requirements and a real answer body, exactly as any other year would.
  const d = doc({ area: '浙江', year: 2015, subject: 'shenlun' });
  d.questions[0].options = [];
  d.questions[0].materialIds = [];        // no material bound
  d.questions[0].requirementsHtml = '';   // no task requirements
  d.questions[0].contentHtml = '';        // no stem
  const v = await validateDocument(d);
  const codes = identityIssueCodes(v);
  assert.ok(!codes.includes('year-invalid'), 'the year itself must be admitted: ' + codes.join(','));
  assert.notEqual(v.dimensions.materials.status, 'complete', 'materials must still be gated');
  const nonIdentity = v.issues.filter(i => i.dimension !== 'identity').map(i => i.code);
  assert.ok(nonIdentity.length > 0, 'structural gaps must still be reported, not waived by the year fix');
});

test('validateDocument still flags Jiangsu 2015 as year-invalid', async () => {
  const v = await validateDocument(doc({ area: '江苏', year: 2015 }));
  assert.ok(identityIssueCodes(v).includes('year-invalid'), identityIssueCodes(v).join(','));
});

test('validateDocument still flags a Zhejiang future year as year-invalid', async () => {
  const v = await validateDocument(doc({ area: '浙江', year: 2099 }));
  assert.ok(identityIssueCodes(v).includes('year-invalid'), identityIssueCodes(v).join(','));
});

// ── promote end-to-end ──────────────────────────────────────────────────────

async function repoFixture(t, { rel, area, year, old = null }) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'year-policy-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const repo = path.join(root, 'repo'), work = path.join(root, 'work'), candRoot = path.join(work, 'batch-ingest');
  const cand = path.join(candRoot, 'p1');
  await fs.mkdir(path.join(repo, 'catalog'), { recursive: true });
  await fs.mkdir(path.join(cand, 'assets-fenbi-85'), { recursive: true });
  execFileSync('git', ['init', '-q', '-b', 'integ', repo]);
  await fs.writeFile(path.join(repo, 'catalog/manifest.jsonl'), '');
  if (old !== null) {
    await fs.mkdir(path.dirname(path.join(repo, rel)), { recursive: true });
    await fs.writeFile(path.join(repo, rel), old);
  }
  const md = '# 合成卷\n\n## 题目\n\n### 第 1 题\n\n题干。\n';
  await fs.writeFile(path.join(cand, 'assets-fenbi-85', 'q.png'), 'img');
  await fs.writeFile(path.join(cand, 'paper.md'), md);
  await fs.writeFile(path.join(cand, 'receipt.json'), JSON.stringify({
    sourceId: '85', area, year, subject: 'xingce', variant: '统考', grade: 'A',
    path: rel, counts: { sourceQuestions: 1 }, answerNumbers: [1],
    markdownSha256: sha(md), oldSha256: old === null ? null : sha(old) }));
  const rights = path.join(root, 'rights.json');
  await fs.writeFile(rights, JSON.stringify({ schemaVersion: 1, allowGitHubStorage: true,
    evidence: 'synthetic year-policy fixture', sourceIds: ['85'] }));
  execFileSync('git', ['-C', repo, 'add', '.']);
  execFileSync('git', ['-C', repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'base']);
  return { repoRoot: repo, candidateRoot: candRoot, rightsFile: rights, rel, repo };
}

test('a Zhejiang 2008 paper promotes', async t => {
  const f = await repoFixture(t, { rel: '省考/浙江/2008/行测-统考.md', area: '浙江', year: 2008 });
  const s = await promoteAll({ ...f, apply: true });
  assert.equal(s.promoted, 1);
  assert.equal(await fs.readFile(path.join(f.repo, f.rel), 'utf8'), '# 合成卷\n\n## 题目\n\n### 第 1 题\n\n题干。\n');
});

test('a Jiangsu 2015 paper is refused at the target-path gate', async t => {
  const f = await repoFixture(t, { rel: '省考/江苏/2015/行测-统考.md', area: '江苏', year: 2015 });
  const s = await promoteAll({ ...f, apply: true });
  assert.equal(s.promoted, 0);
  assert.ok((s.blocked['invalid-target-path'] || []).length, JSON.stringify(s.blocked));
});

test('a Zhejiang 2008 replacement with a stale old hash is refused', async t => {
  const old = '# 旧合成卷\n';
  const f = await repoFixture(t, { rel: '省考/浙江/2008/行测-统考.md', area: '浙江', year: 2008, old });
  const rp = path.join(f.candidateRoot, 'p1', 'receipt.json');
  const rc = JSON.parse(await fs.readFile(rp, 'utf8'));
  rc.oldSha256 = 'deadbeef'.repeat(8);
  await fs.writeFile(rp, JSON.stringify(rc));
  const s = await promoteAll({ ...f, apply: true, allowReplace: true });
  assert.equal(s.promoted, 0);
  assert.ok(s.blocked['repository-paper-changed-since-candidate'], JSON.stringify(s.blocked));
  assert.equal(await fs.readFile(path.join(f.repo, f.rel), 'utf8'), old);
});

test('re-running a Zhejiang 2008 promotion makes no further commit', async t => {
  const f = await repoFixture(t, { rel: '省考/浙江/2008/行测-统考.md', area: '浙江', year: 2008 });
  assert.equal((await promoteAll({ ...f, apply: true })).promoted, 1);
  execFileSync('git', ['-C', f.repo, 'add', '.']);
  execFileSync('git', ['-C', f.repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'promoted']);
  const before = execFileSync('git', ['-C', f.repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const second = await promoteAll({ ...f, apply: true });
  assert.equal(second.promoted, 0);
  assert.equal(second.alreadyPromoted, 1);
  assert.equal(execFileSync('git', ['-C', f.repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), before);
  assert.equal(execFileSync('git', ['-C', f.repo, 'status', '--porcelain'], { encoding: 'utf8' }).trim(), '');
});
