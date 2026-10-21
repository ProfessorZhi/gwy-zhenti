import fs from 'node:fs/promises';
import path from 'node:path';
import { load } from 'cheerio';
import TurndownService from 'turndown';
import gfmPlugin from 'turndown-plugin-gfm';
import { publicUrl, safeChild } from './config.mjs';
import { digest, writeJson } from './store.mjs';

const quote = value => JSON.stringify(value ?? '待核实');

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
  return service.turndown($.html()).trim();
}

export function renderCandidate(document, verdict, { imagePrefix = 'assets' } = {}) {
  if (verdict.status !== 'complete') throw new Error('Only an independently validated complete capture can be rendered');
  const { identity: id, source } = document;
  const convert = html => markdown(html, document.assets, imagePrefix, source.url);
  const questions = [...document.questions].sort((a, b) => a.number - b.number);
  const subject = id.subject === 'xingce' ? '行测' : '申论';
  const lines = ['---', `考试: ${quote(id.area === '国考' ? '国考' : '省考')}`, `地区: ${quote(id.area)}`,
    `年份: ${quote(id.year)}`, `科目: ${quote(subject)}`, `卷型: ${quote(id.variant)}`,
    '真题性质: "粉笔题库整理版本，未认证为官方原卷"', `来源: ${quote(publicUrl(source.url))}`,
    `源试卷ID: ${quote(id.id)}`, `采集时间: ${quote(source.capturedAt)}`,
    '题号口径: "采集到的来源题号，待人工与原卷核对"',
    '校验状态: "候选；机器结构验收通过，尚未人工核验或正式入库"', '---', '', `# ${id.title}`, '',
    '> 候选采集稿。参考答案及解析来自粉笔页面，不代表官方答案或真实高分答卷；来源使用许可与原卷对应关系仍需人工核实。', ''];
  if (document.chapters?.length) {
    lines.push('## 题型与作答说明', '');
    for (const chapter of document.chapters) lines.push(convert(chapter.instructionsHtml), '');
  }
  if (document.materials.length) lines.push('## 给定材料', '');
  // 申论材料按源页签编号（材料1…材料N）；行测沿用内容哈希 ID，行为不变。
  for (const material of document.materials) lines.push(`### 材料 ${material.number ?? material.id}`, '', convert(material.contentHtml), '');
  lines.push('## 题目', '');
  for (const q of questions) {
    lines.push(`### 第 ${q.number} 题`, '', convert(q.contentHtml), '');
    if (q.materialIds.length) lines.push(`关联材料：${q.materialIds.join('、')}`, '');
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
    lines.push(`<details><summary>第 ${q.number} 题</summary>`, '',
      q.answerHtml?.trim() ? answerLabel : '**答案状态：unknown（来源未提供）**', '',
      q.answerHtml?.trim() ? convert(q.answerHtml) : '', '',
      q.explanationHtml?.trim() ? explanationLabel : '**解析状态：unknown（来源未提供）**', '',
      q.explanationHtml?.trim() ? convert(q.explanationHtml) : '', '', '</details>', '');
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
