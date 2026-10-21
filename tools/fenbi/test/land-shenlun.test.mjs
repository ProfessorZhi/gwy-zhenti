import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { landShenlun, shenlunBlockers } from '../worker/land-shenlun.mjs';
import { parseShenlunCapture } from '../src/shenlun.mjs';

// 全部是合成文本和合成图片，不含任何真实粉笔内容。
process.env.GIT_CONFIG_GLOBAL = '/dev/null';
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const git = (cwd, ...a) => execFileSync('git', ['-C', cwd, ...a], { encoding: 'utf8' }).trim();
const IMG_URL = 'https://fb.fenbike.cn/api/tarzan/images/synthetic.png';
const MATERIAL = `<div><p>合成材料一：完全虚构的材料正文。</p><img src="${IMG_URL}"></div>`;
const TITLE = '2025年浙江省公务员录用考试《申论》题（A类）（网友回忆版）';
const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex');

const section = (title, body) => `<section class="result-common-section"><app-solution-title><div class="solution-title-container">`
  + `<div class="solution-title">${title}</div></div></app-solution-title><div class="content"><app-format-html>${body}</app-format-html></div></section>`;
const question = (index, total, analysis) => ({
  index, questionKey: 'k' + index, anchorsVisible: Array.from({ length: total }, (_, i) => `${i + 1}题`),
  prompt: { html: `<app-solution-smart><div class="stem-area"><p>合成题干${index}：归纳要点。</p><p>要求：不超过300字。</p></div>`
    + `<app-result-common><div class="result-common-container">${analysis ? section('解析', '<p>合成文字解析。</p>') : section('解析视频', '<p>视频</p>')}</div></app-result-common></app-solution-smart>` },
  materialsThisQuestion: [{ textLen: 20, htmlSha: sha(MATERIAL) }],
  referenceAnswer: [{ title: '参考答案', html: section('参考答案', `<p>合成参考答案${index}，仅供离线测试。</p>`) }],
});
const capture = ({ total = 2, captured = total } = {}) => ({
  schemaVersion: 2, subject: 'shenlun', cloudStorageBlocked: true,
  identity: { sourceId: '1001', paperId: '1001', area: '浙江', year: 2025, variant: 'a' },
  source: { detailPath: '/ti/view/paper/synthetic' }, capturedAt: '2026-10-20T00:00:00.000Z',
  materials: [{ index: 0, textLen: 20, htmlSha: sha(MATERIAL), html: MATERIAL }],
  questions: Array.from({ length: captured }, (_, i) => question(i + 1, total, i === 0)),
});
const dom = `<!doctype html><html><head><title>${TITLE}</title></head><body><div class="choose-tab">材料1</div></body></html>`;

async function world(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'land-shenlun-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const origin = path.join(root, 'origin.git'), seed = path.join(root, 'seed'), integ = path.join(root, 'integ');
  execFileSync('git', ['init', '-q', '--bare', '-b', 'main', origin]);
  execFileSync('git', ['init', '-q', '-b', 'main', seed]);
  git(seed, 'config', 'user.name', 'F'); git(seed, 'config', 'user.email', 'f@example.invalid');
  const old = '# 旧申论\n\n### 第 1 题\n\n旧题\n\n### 第 2 题\n\n旧题\n';
  await fs.mkdir(path.join(seed, '省考/浙江/2025'), { recursive: true });
  await fs.writeFile(path.join(seed, '省考/浙江/2025/申论-A类.md'), old);
  await fs.mkdir(path.join(seed, 'catalog'));
  await fs.writeFile(path.join(seed, 'catalog/manifest.jsonl'), JSON.stringify({ path: '省考/浙江/2025/申论-A类.md', sha256: sha(old), subject: '申论' }) + '\n');
  git(seed, 'add', '.'); git(seed, 'commit', '-qm', 'base'); git(seed, 'remote', 'add', 'origin', origin); git(seed, 'push', '-q', 'origin', 'main');
  execFileSync('git', ['clone', '-q', origin, integ]);
  git(integ, 'switch', '-qc', 'fenbi-integ');
  git(integ, 'config', 'user.name', 'F'); git(integ, 'config', 'user.email', 'f@example.invalid');
  const rightsFile = path.join(root, 'rights.json');
  await fs.writeFile(rightsFile, JSON.stringify({ schemaVersion: 1, allowGitHubStorage: true, evidence: 'synthetic fixture', sourceIds: [], coverAllCapturedSources: true }));
  const captures = path.join(root, 'captures');
  return { root, origin, integ, rightsFile, captures };
}
async function addCapture(w, name, doc) {
  const dir = path.join(w.captures, name);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(path.join(dir, 'document.json'), JSON.stringify(doc));
  await fs.writeFile(path.join(dir, 'meta.json'), JSON.stringify({ sourceId: '1001', paperId: '1001', cloudStorageBlocked: true, rightsStatus: 'unverified' }));
  await fs.writeFile(path.join(dir, 'dom.html'), dom);
}
const fakeFetch = async () => new Response(PNG, { status: 200, headers: { 'content-type': 'image/png' } });

test('申论采集卷覆盖本库同一卷并推进 main：图片落地、缺解析的题照常发布', async t => {
  const w = await world(t);
  await addCapture(w, 'zj-2025-a', capture());
  const r = await landShenlun({ captures: w.captures, repo: w.integ, rightsFile: w.rightsFile, push: true, autoMerge: true, fetchImpl: fakeFetch });
  assert.equal(r.A, 1, JSON.stringify(r));
  assert.equal(r.gate.ok, true, JSON.stringify(r.gate.reasons));
  assert.equal(r.pushedMain, true);
  const md = execFileSync('git', ['--git-dir', w.origin, 'show', 'main:省考/浙江/2025/申论-A类.md'], { encoding: 'utf8' });
  assert.match(md, /合成参考答案1/u);
  assert.match(md, /解析状态：unknown（来源未提供）/u, 'second question has no textual analysis and is marked');
  assert.match(md, new RegExp(`assets-fenbi-1001/${sha(PNG)}\\.png`, 'u'));
  const files = execFileSync('git', ['-c', 'core.quotePath=false', '--git-dir', w.origin, 'ls-tree', '-r', '--name-only', 'main'], { encoding: 'utf8' });
  assert.match(files, new RegExp(`省考/浙江/2025/assets-fenbi-1001/${sha(PNG)}\\.png`, 'u'));
  const manifest = execFileSync('git', ['--git-dir', w.origin, 'show', 'main:catalog/manifest.jsonl'], { encoding: 'utf8' }).trim().split('\n');
  assert.equal(manifest.length, 1, 'the old row is replaced, not duplicated');
});

test('缺题的申论卷判 C，不落地', async t => {
  const w = await world(t);
  await addCapture(w, 'zj-2025-a', capture({ total: 3, captured: 2 }));
  const r = await landShenlun({ captures: w.captures, repo: w.integ, rightsFile: w.rightsFile, push: false, fetchImpl: fakeFetch });
  assert.deepEqual([r.A, r.C], [0, 1]);
  assert.equal(r.cReasons['question-missing'], 1);
});

test('采集时写死的 cloudStorageBlocked 不再拦落盘；授权只看 RIGHTS_FILE', () => {
  const { doc } = parseShenlunCapture({ capture: capture(), meta: { cloudStorageBlocked: true }, domHtml: dom });
  assert.deepEqual(shenlunBlockers(doc), []);
});
