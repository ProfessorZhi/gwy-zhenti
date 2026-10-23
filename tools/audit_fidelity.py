#!/usr/bin/env python3
"""逐题比对仓库 Markdown 与本地采集到的 document.json。

只读本地文件，不访问网络。用来回答一个问题：MD 里的题干、选项、答案、解析、图片，
和当初从题库采集下来的原始文档是否一致。

用法：
    python3 tools/audit_fidelity.py --work <采集工作区, 含 papers/ 与 shenlun-capture/>
    python3 tools/audit_fidelity.py --work <...> --out rows.json     # 落盘逐卷明细

口径：
    * nz() 做归一化（去 Markdown 转义、图片/链接、HTML 标签，NFKC，只留汉字与字母数字）；
    * cover() 用 4-gram 覆盖率衡量「源文本有多少落在 MD 里」，短串改判包含；
    * 覆盖率 < 0.9 记为待查——它只是线索，需要结合源长度归因，不等于内容缺失。
"""

import argparse
import collections
import html
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB = re.compile(r'全力以赴征集|正在搜集中|本题暂无收集到|暂无收集到|网友未回忆起|题目缺失')
COUNTERS = ['miss_block', 'stem_low', 'stem_short', 'opt', 'ans_low', 'ans_miss',
            'expl_low', 'expl_miss', 'img_broken']


def nz(text):
    text = text or ''
    text = re.sub(r'\\([\\`*_{}\[\]()#+\-.!>|~])', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[^0-9A-Za-z一-鿿]', '', text)
    # 选项字母在两侧的位置不同，先把孤立的 A-H 去掉再比。
    return re.sub(r'(?<![A-Za-z])[A-H](?![A-Za-z])', '', text)


def cover(source, target):
    if not source:
        return 1.0
    if len(source) < 4:
        return 1.0 if source in target else 0.0
    grams = {source[i:i + 4] for i in range(len(source) - 3)}
    return len(grams & {target[i:i + 4] for i in range(len(target) - 3)}) / len(grams)


def md_questions(body):
    """题面区：`### 第 N 题` 到 `## 答案与解析` 之间。"""
    cut = re.search(r'\n##\s*答案与解析', body)
    seg = body[:cut.start()] if cut else body
    parts = re.split(r'\n#{2,4}\s*第\s*(\d+)\s*题[^\n]*\n', seg)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def md_answers(body):
    """答案区：每个 `<details><summary>第 N 题</summary>` 的内容。"""
    cut = re.search(r'\n##\s*答案与解析', body)
    seg = body[cut.end():] if cut else ''
    parts = re.split(r'<details><summary>\s*第\s*(\d+)\s*题\s*</summary>', seg)
    out = {}
    for i in range(1, len(parts), 2):
        block = parts[i + 1]
        end = block.find('</details>')
        out[int(parts[i])] = block[:end] if end > 0 else block
    return out


def split_explanation(block):
    match = re.search(r'\*\*解析\*\*', block)
    return (block[:match.start()], block[match.end():]) if match else (block, '')


# 申论的 explanationHtml 里，「参考答案说明」已经随参考答案渲染在答案区，
# 解析区只保留从「考点」开始的部分。比对源文本时要用同一条规则，否则会把
# 有意的拆分当成内容丢失。
KAODIAN = re.compile(r'<p[^>]*>\s*<strong>\s*考点\s*</strong>', re.I)


def explanation_tail(html_text):
    text = html_text or ''
    found = KAODIAN.search(text)
    if found:
        text = text[found.start():]
    text = re.sub(r'<strong>\s*考点\s*</strong>\s*[：:]\s*考点', '<strong>考点</strong>：', text)
    return re.sub(r'<strong>\s*来源\s*</strong>\s*[：:]\s*来源', '<strong>来源</strong>：', text)


def images_in_md(text):
    return re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text or '')


def images_in_html(text):
    return re.findall(r'<img[^>]+src=["\']([^"\']+)', text or '')


def find_document(work, sid):
    for base in (os.path.join(work, 'papers'), os.path.join(work, 'shenlun-capture')):
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            if name.endswith('-' + sid) or name == sid:
                path = os.path.join(base, name, 'document.json')
                if os.path.exists(path):
                    with open(path, encoding='utf-8') as handle:
                        return json.load(handle), path
    return None, None


def normalize_source_questions(document):
    """把两种 document schema 统一成 {number, contentHtml, options, answerHtml, explanationHtml}。"""
    questions = []
    for question in document.get('questions') or []:
        if 'number' in question:
            questions.append(question)
            continue
        # 旧申论 schema：index / prompt / referenceAnswer / otherSections
        answers = ' '.join(x.get('html') or '' for x in question.get('referenceAnswer') or [] if isinstance(x, dict))
        explanations = ' '.join(
            x.get('html') or '' for x in question.get('otherSections') or []
            if isinstance(x, dict) and re.search(r'解析|说明', x.get('title') or ''))
        questions.append({
            'number': question.get('index'),
            'contentHtml': (question.get('prompt') or {}).get('html') or '',
            'options': [],
            'answerHtml': answers,
            'explanationHtml': explanations,
        })
    return [q for q in questions if q.get('number')]


def audit_paper(manifest_row, document, where):
    path = manifest_row['path']
    full = os.path.join(ROOT, path)
    with open(full, encoding='utf-8') as handle:
        text = handle.read()
    end = text.find('\n---', 3)
    if end < 0:
        return None
    body = text[end + 4:]
    questions = normalize_source_questions(document)
    stems, answers = md_questions(body), md_answers(body)
    state = dict(path=path, sid=None, where=where, src_q=len(questions), md_q=len(stems), md_a=len(answers),
                 img_src=0, img_md=0, mat_src=0, mat_md=0, html_residue=0)
    for key in COUNTERS:
        state[key] = []
    state['html_residue'] = len(re.findall(r'</?(?:p|div|span|b|strong|img|br|table|td)\b', body))
    state['mat_md'] = len(re.findall(r'\n#{2,4}\s*材料\s*\d*', body))
    state['mat_src'] = len(document.get('materials') or [])
    # 题面区的图片数（答案区单独计）
    split = body.find('## 答案与解析')
    state['img_md'] += len(re.findall(r'!\[[^\]]*\]\(([^)]+)\)', body[:split] if split > 0 else body))
    state['img_src'] += sum(len(images_in_html(m.get('contentHtml') or ''))
                            for m in document.get('materials') or [])
    for question in questions:
        number = question['number']
        stem_html = question.get('contentHtml') or ''
        options = question.get('options') or []
        if STUB.search(re.sub(r'<[^>]+>', '', stem_html)):
            continue  # 源页面自带的「题目缺失」占位，不按缺失处理
        option_text = ''.join(
            nz(o.get('contentHtml') or o.get('text') or '') if isinstance(o, dict) else nz(str(o))
            for o in options)
        source_text = nz(stem_html) + option_text
        block = stems.get(number)
        if block is None:
            state['miss_block'].append(number)
            continue
        md_text = nz(block)
        score = cover(source_text, md_text)
        if score < 0.9:
            state['stem_low'].append((number, round(score, 3)))
        if len(md_text) < 0.6 * len(source_text) and len(source_text) > 40:
            state['stem_short'].append((number, len(source_text), len(md_text)))
        if options:
            found = len(re.findall(r'(?m)^\s*[A-H][\.．、]', block))
            if found < len(options):
                state['opt'].append((number, len(options), found))
        state['img_src'] += len(images_in_html(stem_html)) + sum(
            len(images_in_html(o.get('contentHtml') or '')) for o in options if isinstance(o, dict))
        for url in images_in_md(block):
            if url.startswith('http'):
                continue
            if not os.path.exists(os.path.join(os.path.dirname(full), url)):
                state['img_broken'].append((number, url))
        answer_html = question.get('answerHtml') or ''
        explanation_html = question.get('explanationHtml') or ''
        md_answer, md_explanation = split_explanation(answers.get(number, ''))
        source_answer, source_explanation = nz(answer_html), nz(md_answer)
        if source_answer:
            if not source_explanation:
                state['ans_miss'].append(number)
            elif cover(source_answer, source_explanation) < 0.9:
                state['ans_low'].append((number, round(cover(source_answer, source_explanation), 3)))
        source_expl, md_expl = nz(explanation_tail(explanation_html)), nz(md_explanation)
        if source_expl:
            if not md_expl:
                state['expl_miss'].append(number)
            elif cover(source_expl, md_expl) < 0.9:
                state['expl_low'].append((number, round(cover(source_expl, md_expl), 3)))
        state['img_src'] += len(images_in_html(answer_html)) + len(images_in_html(explanation_html))
        state['img_md'] += len(images_in_md(md_answer)) + len(images_in_md(md_explanation))
    for key in COUNTERS:
        state[key + '_n'] = len(state[key])
        state[key] = state[key][:40]
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', default=os.path.join(ROOT, 'catalog/manifest.jsonl'))
    parser.add_argument('--work', required=True, help='采集工作区（含 papers/ 与 shenlun-capture/）')
    parser.add_argument('--out', help='逐卷明细写到该路径')
    args = parser.parse_args()

    rows, nocache = [], []
    with open(args.manifest, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            full = os.path.join(ROOT, record['path'])
            with open(full, encoding='utf-8') as paper:
                text = paper.read()
            match = re.search(r'^源试卷ID:\s*"(\d+)"', text[:text.find('\n---', 3)], re.M)
            if not match:
                continue  # 非粉笔来源，没有可比的采集文档
            document, where = find_document(args.work, match.group(1))
            if not document:
                nocache.append((record['path'], match.group(1)))
                continue
            state = audit_paper(record, document, where)
            if state:
                state['sid'] = match.group(1)
                rows.append(state)

    totals = collections.Counter()
    for row in rows:
        for key in COUNTERS:
            totals[key] += row[key + '_n']
    print(f'核卷 {len(rows)} · 无缓存 {len(nocache)}')
    print(dict(totals))
    print('图片 源', sum(r['img_src'] for r in rows), 'md', sum(r['img_md'] for r in rows))
    print('HTML残留卷', sum(1 for r in rows if r['html_residue']))
    print('材料数不符卷', sum(1 for r in rows if r['mat_src'] and r['mat_src'] != r['mat_md']))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump({'rows': rows, 'nocache': nocache}, handle, ensure_ascii=False)
        print('已写入', args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
