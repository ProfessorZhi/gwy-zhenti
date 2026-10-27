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
    # 先解实体再去标签，标签只认「<字母 … >」且中间不含另一个 <。
    # 否则「290<M<300」这种题干里的比较号会被当成标签，连同后文一起吃掉
    # （重庆 2024 行测-选调生第 54 题、山东 2022 行测第 21 题的「《…建议》」都是这么丢的）。
    text = html.unescape(text)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    text = re.sub(r'</?[a-zA-Z][^<>]*>', ' ', text)
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
    """答案区：每个 `<details><summary>第 N 题 · 答案与解析</summary>` 的内容。

    答案块现行写法是「题下内联折叠」，全库 90,845 个块统一为
    `<summary>第 N 题 · 答案与解析</summary>`，没有独立的「## 答案与解析」章节；
    只有佐证版卷才带该章节标题（且章节内无答案）。所以没有标题时要在全文里找，
    有标题时从标题之后找，summary 的「题」后面允许有后缀文字。
    """
    cut = re.search(r'\n##\s*答案与解析', body)
    seg = body[cut.end():] if cut else body
    parts = re.split(r'<details><summary>\s*第\s*(\d+)\s*题[^<]*</summary>', seg)
    out = {}
    for i in range(1, len(parts), 2):
        block = parts[i + 1]
        end = block.find('</details>')
        out[int(parts[i])] = block[:end] if end > 0 else block
    return out


def split_explanation(block):
    # 行测解析区的标签有两种：「**解析**」与「**官方解析**」（须先用圆括号的可选前缀，
    # 否则 `\*\*解析\*\*` 匹配不到 `**官方解析**`，整卷解析会被判成缺失）。
    match = re.search(r'\*\*(?:官方)?解析\*\*', block)
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


SUBJECT_OF = {'xingce': '行测', 'shenlun': '申论'}
# 粉笔的分类里「选调生」「公安招警和公检法」是 area 桶，仓库按省份记 area、
# 把这两类记在卷型里，只是命名不同，不比 area。
# 其余 area（含深圳、广州、新疆兵团、国考）两边同名，照比。
AREA_BUCKETS = {'选调生', '公安招警和公检法'}


def identity_of(document):
    """采集文档自称的「地区／年份／科目」，用于比对前先确认是不是同一份卷。

    不先验身份就比正文，会把「同一 sid 被两卷引用」的错配当成内容失真：
    国考 2009 行测（140 题）对上一份 4 题申论文档时，会报 136 处缺题。
    """
    ident = document.get('identity') or {}
    subject = ident.get('subject') or document.get('subject')
    return {'area': ident.get('area'), 'year': ident.get('year'),
            'subject': SUBJECT_OF.get(subject, subject),
            'title': ident.get('title') or ''}


def is_joint_exam(*titles):
    """联考共用一套题，粉笔按其中一个省归档，仓库按拆分后的省份记 area。
    西藏 2016 就是这么来的：仓库标西藏，缓存标广西，标题同为「2016年423联考」。
    """
    return any('联考' in (t or '') for t in titles)


def paper_title(text):
    match = re.search(r'^#\s+(.+)$', text, re.M)
    return match.group(1).strip() if match else ''


def identity_conflict(record, ident, title_text=''):
    if (ident['area'] and ident['area'] not in AREA_BUCKETS
            and record.get('area') and ident['area'] != record['area']
            and not is_joint_exam(title_text, ident.get('title'))):
        return f"地区 {record['area']} ≠ 缓存 {ident['area']}"
    if ident['year'] and record.get('year') and str(ident['year']) != str(record['year']):
        return f"年份 {record.get('year')} ≠ 缓存 {ident['year']}"
    if ident['subject'] and record.get('subject') and ident['subject'] != record['subject']:
        return f"科目 {record['subject']} ≠ 缓存 {ident['subject']}"
    return None


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
    # 材料正文的键名是 `html`（不是题目的 `contentHtml`），两种都试。
    state['img_src'] += sum(len(images_in_html(m.get('contentHtml') or m.get('html') or ''))
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
                # 申论参考答案里的「参考答案说明」常被渲染到解析区，是有意的版式切分，
                # 不是丢内容：按「答案区 + 解析区」合并再判一次，仍不足才记低覆盖。
                if cover(source_answer, source_explanation + nz(md_explanation)) < 0.9:
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
    parser.add_argument('--ignore-identity', action='store_true',
                        help='不校验缓存文档的地区/年份/科目（默认校验，不符的卷单列）')
    args = parser.parse_args()

    rows, nocache, conflicts = [], [], []
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
            ident = identity_of(document)
            conflict = identity_conflict(record, ident, paper_title(text))
            if conflict and not args.ignore_identity:
                conflicts.append({'path': record['path'], 'sid': match.group(1),
                                  'where': where, 'conflict': conflict, 'cached': ident})
                continue
            state = audit_paper(record, document, where)
            if state:
                state['sid'] = match.group(1)
                rows.append(state)

    totals = collections.Counter()
    for row in rows:
        for key in COUNTERS:
            totals[key] += row[key + '_n']
    print(f'核卷 {len(rows)} · 无缓存 {len(nocache)} · 身份不符 {len(conflicts)}')
    print(dict(totals))
    print('图片 源', sum(r['img_src'] for r in rows), 'md', sum(r['img_md'] for r in rows))
    print('HTML残留卷', sum(1 for r in rows if r['html_residue']))
    print('材料数不符卷', sum(1 for r in rows if r['mat_src'] and r['mat_src'] != r['mat_md']))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump({'rows': rows, 'nocache': nocache, 'identity_conflicts': conflicts},
                      handle, ensure_ascii=False)
        print('已写入', args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
