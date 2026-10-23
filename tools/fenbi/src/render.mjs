import fs from 'node:fs/promises';
import path from 'node:path';
import { load } from 'cheerio';
import TurndownService from 'turndown';
import gfmPlugin from 'turndown-plugin-gfm';
import { publicUrl, safeChild } from './config.mjs';
import { digest, writeJson } from './store.mjs';

const quote = value => JSON.stringify(value ?? '待核实');

// HTML 正文里的 `<`（如「<72%」「《<大圣归来>》」）经 Turndown 会原样落进 Markdown。
// 下游解析器按标签切分时，一个裸 `<` 会一路吃到后面某个 `>`，把中间正文整段删掉。
// 这里只保留真正的标签：已知空元素、闭合标签、以及本片段内存在配对闭合的开标签；
// 其余一律转成 `&lt;`（渲染出来仍是 `<`，但不会再被当成标签起点）。
const VOID_TAGS = new Set(['img', 'br', 'hr', 'source', 'input', 'meta', 'link', 'wbr', 'col', 'area', 'base', 'embed', 'param', 'track']);
const TAG_AT = /^<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:[^<>"']|"[^"]*"|'[^']*')*)>/u;

export function escapeStrayLt(text) {
  const src = String(text ?? '');
  const closers = new Set();
  for (const m of src.matchAll(/<\/([a-zA-Z][a-zA-Z0-9-]*)\s*>/gu)) closers.add(m[1].toLowerCase());
  let out = '';
  let i = 0;
  while (i < src.length) {
    if (src[i] !== '<') { out += src[i]; i += 1; continue; }
    const match = src.slice(i).match(TAG_AT);
    if (!match) { out += '&lt;'; i += 1; continue; }
    const name = match[2].toLowerCase();
    const keep = match[1] === '/' || VOID_TAGS.has(name) || match[3].trimEnd().endsWith('/') || closers.has(name);
    out += keep ? match[0] : '&lt;';
    i += keep ? match[0].length : 1;
  }
  return out;
}

export function markdown(html, assets = [], imagePrefix = 'assets', baseUrl = 'https://www.fenbi.com/') {
  const $ = load(String(html || ''), null, false);
  $('script,style,iframe,object,embed,form,input,button,textarea,select').remove();
  $('*').each((_, el) => {
    for (const key of Object.keys(el.attribs || {})) if (/^on/i.test(key) || ['srcdoc', 'style'].includes(key)) $(el).removeAttr(key);
  });
  $('a').each((_, el) => {
    const a = $(el), href = a.attr('href') || '';
    try { a.attr('href', publicUrl(href)); } catch { a.replaceWith(a.contents()); }
  });
  $('img, source, image').each((_, el) => {
    const image = $(el);
    const src = image.attr('src') || image.attr('data-src') || image.attr('href') || image.attr('xlink:href');
    const sources = [...new Set([src, ...(image.attr('srcset') || '').split(',').map(x => x.trim().split(/\s+/)[0])].filter(Boolean))];
    const local = value => {
      const absolute = new URL(value, baseUrl).toString();
      const asset = assets.find(x => x.url === absolute);
      if (!asset || asset.status !== 'downloaded' || !asset.localPath) throw new Error('Unresolved image prevents Markdown export');
      return `${imagePrefix}/${asset.localPath.replaceAll('\\', '/')}`;
    };
    if (!sources.length) throw new Error('Image has no source');
    if (el.tagName === 'image') {
      image.attr('href', local(sources[0])); image.removeAttr('xlink:href');
    } else {
      const replacements = sources.map(value => $('<img>').attr('src', local(value)).attr('alt', image.attr('alt') || '')).map(x => $.html(x)).join('');
      image.replaceWith(replacements);
    }
    image.removeAttr('srcset'); image.removeAttr('data-src');
  });
  const service = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced', bulletListMarker: '-',
    blankReplacement: (_content, node) => node.nodeName.toLowerCase() === 'svg' ? `\n\n${node.outerHTML}\n\n` : node.isBlock ? '\n\n' : '',
  });
  service.use(gfmPlugin.gfm);
  service.keep(['svg']);
  service.addRule('math', {
    filter: ['math'], replacement: (_content, node) => node.outerHTML,
  });
  service.addRule('latex', {
    filter: node => node.getAttribute?.('data-latex') !== null,
    replacement: (_content, node) => `$${node.getAttribute('data-latex')}$`,
  });
  return escapeStrayLt(service.turndown($.html()).trim());
}

// 申论的 explanationHtml 常把「参考答案说明」和「考点 / 来源 / 视频入口说明」放在一起，
// 前者已经随参考答案渲染在答案区，整段照搬会重复。这里只保留从「考点」开始的部分。
const KAODIAN_START = /<p[^>]*>\s*<strong>\s*考点\s*<\/strong>/iu;
export function explanationFragment(html) {
  const source = String(html ?? '');
  const at = source.search(KAODIAN_START);
  const fragment = at >= 0 ? source.slice(at) : source;
  // 题库 DOM 把标签文字也并进了值里：「考点提出对策类」「来源2016年…」
  return fragment
    .replace(/<strong>\s*考点\s*<\/strong>\s*[：:]\s*考点/gu, '<strong>考点</strong>：')
    .replace(/<strong>\s*来源\s*<\/strong>\s*[：:]\s*来源/gu, '<strong>来源</strong>：');
}

export function renderCandidate(document, verdict, { imagePrefix = 'assets' } = {}) {
  if (verdict.status !== 'complete') throw new Error('Only an independently validated complete capture can be rendered');
  const { identity: id, source } = document;
  const convert = html => markdown(html, document.assets, imagePrefix, source.url);
  const questions = [...document.questions].sort((a, b) => a.number - b.number);
  const subject = id.subject === 'xingce' ? '行测' : '申论';
  const lines = ['---', `考试: ${quote(id.area === '国考' ? '国考' : '省考')}`, `地区: ${quote(id.area)}`,
    `年份: ${quote(id.year)}`, `科目: ${quote(subject)}`, `卷型: ${quote(id.paperLabel ?? id.variant)}`,
    '真题性质: "粉笔题库整理版本，未认证为官方原卷"', `来源: ${quote(publicUrl(source.url))}`,
    `源试卷ID: ${quote(id.id)}`, `采集时间: ${quote(source.capturedAt)}`,
    '题号口径: "采集到的来源题号，待人工与原卷核对"',
    '校验状态: "候选；机器结构验收通过，尚未人工核验或正式入库"', '---', '', `# ${id.title}`, '',
    '> 候选采集稿。参考答案及解析来自粉笔页面，不代表官方答案或真实高分答卷；来源使用许可与原卷对应关系仍需人工核实。', ''];
  if (document.chapters?.length) {
    lines.push('## 题型与作答说明', '');
    for (const chapter of document.chapters) lines.push(convert(chapter.instructionsHtml), '');
  }
  // 材料编号：按首个引用它的题排序，未被引用的排在最后；编号 1…N 稳定可读，取代内容哈希。
  const firstUse = new Map();
  questions.forEach((q, index) => { for (const mid of q.materialIds) if (!firstUse.has(mid)) firstUse.set(mid, index); });
  const materialOrder = [...document.materials].sort((a, b) =>
    (firstUse.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (firstUse.get(b.id) ?? Number.MAX_SAFE_INTEGER));
  const materialNumber = new Map(materialOrder.map((material, index) => [material.id, index + 1]));
  const materialOf = new Map(document.materials.map(material => [material.id, material]));
  const label = id_ => `材料 ${materialNumber.get(id_) ?? id_}`;
  if (subject === '申论') {
    // 申论：给定资料是全文共用，保持前置；题干的「关联材料」指向 材料 N。
    if (document.materials.length) lines.push('## 给定材料', '');
    for (const material of materialOrder) lines.push(`### ${label(material.id)}`, '', convert(material.contentHtml), '');
  }
  lines.push('## 题目', '');
  let current = null;
  for (const q of questions) {
    const refs = q.materialIds.filter(mid => materialOf.has(mid));
    // 行测：资料分析/篇章阅读的材料紧跟其首题，图文交叉不割裂。
    if (subject !== '申论' && refs.length && refs[0] !== current) {
      current = refs[0];
      lines.push(`## ${label(current)}`, '', convert(materialOf.get(current).contentHtml), '');
    }
    lines.push(`### 第 ${q.number} 题`, '', convert(q.contentHtml), '');
    // 材料就在上方时省略引用行，避免每道题重复；跨组或多材料引用保留。
    const extra = refs.filter(mid => subject === '申论' || mid !== current);
    if (extra.length && (subject === '申论' || extra.length !== refs.length || refs.length > 1)) {
      lines.push(`关联材料：${extra.map(label).join('、')}`, '');
    }
    for (const option of q.options) lines.push(`${option.label}. ${convert(option.contentHtml)}`, '');
    if (q.requirementsHtml) lines.push('作答要求：', '', convert(q.requirementsHtml), '');
  }
  lines.push('## 答案与解析', '');
  for (const q of questions) {
    const answerLabel = q.answerOrigin === 'original-repository'
      ? '**参考答案（原库来源，按题目内容唯一映射保留）**'
      : '**参考答案（粉笔题库参考内容）**';
    const explanationLabel = q.explanationOrigin === 'original-repository'
      ? '**解析（原库来源，按题目内容唯一映射保留）**' : '**解析**';
    const explanation = explanationFragment(q.explanationHtml);
    lines.push(`<details><summary>第 ${q.number} 题</summary>`, '',
      q.answerHtml?.trim() ? answerLabel : '**答案状态：unknown（来源未提供）**', '',
      q.answerHtml?.trim() ? convert(q.answerHtml) : '', '',
      explanation.trim() ? explanationLabel : '**解析状态：unknown（来源未提供）**', '',
      explanation.trim() ? convert(explanation) : '', '', '</details>', '');
  }
  return lines.join('\n');
}

export async function exportCandidate(document, verdict, bundleDir, destination) {
  // Fresh, immutable directories make an export reviewable and prevent accidental replacement.
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.mkdir(destination);
  try {
    const md = renderCandidate(document, verdict);
    await fs.writeFile(path.join(destination, 'paper.md'), md + '\n', { flag: 'wx' });
    await fs.mkdir(path.join(destination, 'assets'));
    for (const asset of document.assets) {
      const source = safeChild(path.join(bundleDir, 'assets'), asset.localPath);
      const bytes = await fs.readFile(source);
      if (digest(bytes) !== asset.sha256) throw new Error('Image changed after validation');
      await fs.writeFile(safeChild(path.join(destination, 'assets'), asset.localPath), bytes, { flag: 'wx' });
    }
    await writeJson(path.join(destination, 'validation.json'), verdict);
    return destination;
  } catch (error) {
    await writeJson(path.join(destination, 'EXPORT-INCOMPLETE.json'), { status: 'failed', reason: error.message });
    throw error;
  }
}
