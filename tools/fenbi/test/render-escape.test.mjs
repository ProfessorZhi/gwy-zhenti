import test from 'node:test';
import assert from 'node:assert/strict';
import { escapeStrayLt, explanationFragment, markdown } from '../src/render.mjs';

test('prose "<" is escaped so downstream tag splitting cannot swallow the body', () => {
  assert.equal(escapeStrayLt('占比<72%'), '占比&lt;72%');
  assert.equal(escapeStrayLt('19.93<11.12×2，错误。'), '19.93&lt;11.12×2，错误。');
  assert.equal(escapeStrayLt('【文段出处】《<大圣归来>说启迪》'), '【文段出处】《&lt;大圣归来>说启迪》');
  assert.equal(escapeStrayLt('A. <45%'), 'A. &lt;45%');
});

test('real markup produced by the renderer survives untouched', () => {
  const md = '<details><summary>第 1 题</summary>\n\n![](assets/a.png)\n\n</details>';
  assert.equal(escapeStrayLt(md), md);
  assert.equal(escapeStrayLt('<svg><path d="M0 0"/></svg>'), '<svg><path d="M0 0"/></svg>');
  assert.equal(escapeStrayLt('<math><mi>x</mi></math>'), '<math><mi>x</mi></math>');
  assert.equal(escapeStrayLt('a<br>b'), 'a<br>b');
});

test('an unpaired "<b>" in prose is text, not an emphasis tag', () => {
  assert.equal(escapeStrayLt('把<b>当成正文'), '把&lt;b>当成正文');
  // 同一片段里真有闭合标签时才算标签
  assert.equal(escapeStrayLt('<b>粗</b>'), '<b>粗</b>');
});

test('escaping is idempotent and never double-encodes an entity', () => {
  const once = escapeStrayLt('增速<72%，另见 &lt;10%');
  assert.equal(once, '增速&lt;72%，另见 &lt;10%');
  assert.equal(escapeStrayLt(once), once);
});

test('markdown() escapes a bare "<" that came from HTML text content', () => {
  const out = markdown('<p>铁路货物周转量占总体比重<10%，且19.93<11.12×2。</p>');
  assert.ok(out.includes('&lt;10%'), out);
  assert.ok(out.includes('&lt;11.12'), out);
  assert.ok(!/<10%/u.test(out), out);
  // 以后面的 `>` 切标签也不会再吃掉正文
  assert.ok(!/<[^>]*>/u.test(out), out);
});

test('markdown() keeps genuine images while escaping the prose around them', () => {
  const assets = [{ url: 'https://fb.fbstatic.cn/a.png', status: 'downloaded', localPath: 'a.png', sha256: 'x' }];
  const out = markdown('<p>占比<10%</p><p><img src="https://fb.fbstatic.cn/a.png"></p>', assets, 'assets', 'https://spa.fenbi.com/');
  assert.ok(out.includes('&lt;10%'), out);
  assert.ok(/!\[\]\(assets\/a\.png\)/u.test(out), out);
});

test('申论文章分析类解析整段保留，不被「考点」切法清空', () => {
  const html = '<p><b>文章分析</b></p><p>范文正文</p><p>【标题的优点：紧扣主题】</p>'
    + '<p><strong>考点</strong>：考点文章写作题</p><p><strong>来源</strong>：来源2026年国考</p>';
  const out = explanationFragment(html);
  assert.match(out, /文章分析/);
  assert.match(out, /范文正文/);
  assert.match(out, /考点<\/strong>：文章写作题/);
  assert.match(out, /来源<\/strong>：2026年国考/);
});

test('只有参考答案说明与考点的解析仍从考点起切', () => {
  const html = '<p>参考答案说明：分条撰写。</p><p><strong>考点</strong>：考点特点类</p>'
    + '<p><strong>来源</strong>：来源2016年联考</p>';
  const out = explanationFragment(html);
  assert.doesNotMatch(out, /参考答案说明/);
  assert.match(out, /考点<\/strong>：特点类/);
});

test('文章分析排在考点之后时仍保留考点与来源', () => {
  const html = '<p><strong>考点</strong>：考点概括</p><p><b>范文分析</b></p><p>正文</p>';
  const out = explanationFragment(html);
  assert.match(out, /考点/);
  assert.match(out, /范文分析/);
});
