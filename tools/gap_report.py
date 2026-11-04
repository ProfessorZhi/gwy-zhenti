#!/usr/bin/env python3
"""生成缺口总账 docs/GAP-STATUS.md 与 README 的缺口区块。

缺口分两层：
    缺卷      真实开考、本库未收录的卷次，来自 catalog/missing-papers.jsonl（缺卷 / 待核）。
    局部缺口  已收录试卷内的缺失，逐题从试卷正文识别：
              行测  缺题干 > 缺选项 > 缺答案，每题只计最严重的一级；
              申论  缺题目、缺材料、缺答案。

用法：
    python3 -I tools/gap_report.py            # 写 docs/GAP-STATUS.md 与 README 区块
    python3 -I tools/gap_report.py --check    # 只检查是否最新
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from gap_content_audit import scan  # noqa: E402

ISSUES = 'https://github.com/ProfessorZhi/gwy-zhenti/issues/'
STUB = '粉笔暂未收录本题'
NO_ANSWER = '答案状态：unknown'
# 题干中的材料引用：「给定资料 3」「材料2-4」「资料 2\-4」「材料2至4」等。
MATERIAL_REF = re.compile(r'(?:资料|材料)\s*(\d{1,2})(?!\d)(?:\s*(?:\\?[-—–~～]|至|到)\s*(\d{1,2})(?!\d))?')
# 答案已收录、但与题目的对应关系尚未核实的题（无法从正文机读，在此登记）。
ANSWER_UNVERIFIED = {'省考/北京/2025/行测-统考.md': [1, 6, 7, 8, 9, 15, 23, 25, 26, 27, 28, 31, 67, 68, 69, 70, 71, 78]}


def blocks(text):
    parts = re.split(r'^#{2,3} 第 ?(\d+) ?题', text, flags=re.M)
    return [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts), 2)]


def ranges(nums):
    nums = sorted(nums)
    out, start = [], None
    for i, n in enumerate(nums):
        if start is None:
            start = n
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f'{start}–{n}')
            start = None
    return '、'.join(out)


def name(path):
    parts = path[:-3].split('/')
    area = '国考' if parts[0] == '国考' else parts[1]
    subject, _, label = parts[-1].partition('-')
    return f'{area} {parts[-2]} {subject} {label}'


def collect():
    rows = [json.loads(l) for l in (ROOT / 'catalog/manifest.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    findings, _ = scan(ROOT)
    no_option = defaultdict(list)
    no_answer_confirmed = defaultdict(list)
    for f in findings:
        if f['type'].startswith('a2_confirmed'):
            no_option[f['path']].append(f['question'])
        elif f['type'] == 'b2_confirmed_explicit_no_answer':
            no_answer_confirmed[f['path']].append(f['question'])
    xingce, shenlun = {}, {}
    for r in rows:
        path = r['path']
        text = (ROOT / path).read_text(encoding='utf-8')
        qs = blocks(text)
        if r['subject'] == '行测':
            stem = [q for q, b in qs if STUB in b]
            option = [q for q in no_option.get(path, []) if q not in stem]
            answer = [q for q, b in qs if NO_ANSWER in b and q not in stem and q not in option]
            if stem or option or answer:
                xingce[path] = {'stem': stem, 'option': option, 'answer': answer}
        else:
            have = {int(x) for x in re.findall(r'^#{2,4} 材料 ?(\d+)', text, re.M)}
            missing = set()
            for _, b in qs:
                body = re.sub(r'^关联材料：.*$', '', b.split('<details')[0], flags=re.M)
                for a, z in MATERIAL_REF.findall(body):
                    a, z = int(a), int(z or a)
                    missing.update(n for n in range(a, z + 1) if z >= a and n not in have)
            question = [q for q, b in qs if STUB in b]
            answer = sorted(set(no_answer_confirmed.get(path, [])) | {q for q, b in qs if NO_ANSWER in b and q not in question})
            if question or missing or answer:
                shenlun[path] = {'question': question, 'material': sorted(missing), 'answer': answer}
    papers = [json.loads(l) for l in (ROOT / 'catalog/missing-papers.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    return rows, xingce, shenlun, papers


def summary(rows, xingce, shenlun, papers):
    s = Counter()
    for v in xingce.values():
        for k in ('stem', 'option', 'answer'):
            s['x_' + k] += len(v[k]); s['xp_' + k] += bool(v[k])
    for v in shenlun.values():
        for k in ('question', 'material', 'answer'):
            s['s_' + k] += len(v[k]); s['sp_' + k] += bool(v[k])
    s['missing'] = sum(p['status'] == '缺卷' for p in papers)
    s['pending'] = sum(p['status'] == '待核' for p in papers)
    s['unverified'] = sum(len(v) for v in ANSWER_UNVERIFIED.values())
    return s


def num(n, unit):
    return f'{n} {unit}' if n else '—'


def overview(s, link_prefix=''):
    def pq(n, p, unit='题'):
        return f'{n} {unit} · {p} 卷' if n else '—'
    return [
        '| 层级 | 类别 | 数量 | 跟踪 |',
        '| --- | --- | ---: | :---: |',
        f"| **缺卷** | 已确认缺卷 | {num(s['missing'], '卷')} | [#160]({ISSUES}160) |",
        f"| | 考试身份待核 | {num(s['pending'], '卷')} | [#161]({ISSUES}161) |",
        f"| **行测** | 缺题干 | {pq(s['x_stem'], s['xp_stem'])} | [#155]({ISSUES}155) [#156]({ISSUES}156) |",
        f"| | 缺选项 | {pq(s['x_option'], s['xp_option'])} | [#157]({ISSUES}157) |",
        f"| | 缺答案 | {pq(s['x_answer'], s['xp_answer'])} | |",
        f"| **申论** | 缺题目 | {pq(s['s_question'], s['sp_question'])} | |",
        f"| | 缺材料 | {pq(s['s_material'], s['sp_material'], '份材料')} | [#159]({ISSUES}159) |",
        f"| | 缺答案 | {pq(s['s_answer'], s['sp_answer'])} | [#158]({ISSUES}158) |",
    ]


def status_md(rows, xingce, shenlun, papers):
    s = summary(rows, xingce, shenlun, papers)
    files = len(rows)
    recent = [r for r in rows if int(r['year']) >= 2016]
    L = ['# 缺口总账', '',
         '[← 返回首页](../README.md) · [文档](README.md)', '',
         '<!-- 由 tools/gap_report.py 生成，勿手改 -->', '',
         '## 统计口径', '',
         '- **缺卷**：以实际举行的考试为准，按「地区 × 年份 × 科目 × 卷型」计。范围为 2016–2026 年；2015 年及以前只统计已收录试卷，不计缺卷。'
         '考试身份或卷型尚未确认的，列为「待核」，不计入缺卷。',
         '- **局部缺口**：已收录试卷内的缺失，按题计。行测分三级——缺题干、缺选项、缺答案，每题只计最严重的一级；申论分缺题目、缺材料、缺答案。',
         '- **来源**：以粉笔为主、华图补充。每份试卷在文件头 `来源` 与 `来源清单` 中记录实际采用的全部来源；缺卷指上述来源均未收录的卷次。', '',
         '## 总览', '']
    L += overview(s)
    L += ['', f'已收录试卷 {files:,} 份（2016–2026 年 {len(recent):,} 份）。'
          f"另有 {s['unverified']} 题参考答案已收录、但与题目的对应关系待核，见 [#157]({ISSUES}157)。", '']
    # 缺卷
    L += ['## 一、缺卷', '', '| 年份 | 地区 | 科目 | 卷型 | 状态 | 依据 |', '| :---: | --- | --- | --- | --- | --- |']
    for p in sorted(papers, key=lambda p: (p['status'] != '缺卷', -p['year'], p['area'], p['subject'], p['variant'] or '')):
        basis = p['basis']
        basis = f'[招录公告]({basis})' if basis.startswith('http') else basis
        L.append(f"| {p['year']} | {p['area']} | {p['subject']} | {p['variant'] or '待定'} | {p['status']} | {basis} |")
    L += ['', '缺卷台账：[`catalog/missing-papers.jsonl`](../catalog/missing-papers.jsonl)。', '']
    # 行测
    L += ['## 二、行测局部缺口', '', '| 试卷 | 缺题干 | 缺选项 | 缺答案 |', '| --- | --- | --- | --- |']
    for path, v in sorted(xingce.items(), key=lambda x: (-sum(map(len, x[1].values())), x[0])):
        cell = lambda q: f'{len(q)} 题：{ranges(q)}' if q else '—'
        L.append(f"| [{name(path)}](../{path}) | {cell(v['stem'])} | {cell(v['option'])} | {cell(v['answer'])} |")
    L += ['']
    # 申论
    L += ['## 三、申论局部缺口', '', '| 试卷 | 缺题目 | 缺材料 | 缺答案 |', '| --- | --- | --- | --- |']
    for path, v in sorted(shenlun.items()):
        cell = lambda q, u='题': f'第 {ranges(q)} {u}' if q else '—'
        mat = f"材料 {ranges(v['material'])}" if v['material'] else '—'
        L.append(f"| [{name(path)}](../{path}) | {cell(v['question'])} | {mat} | {cell(v['answer'])} |")
    L += ['', '## 补录原则', '',
          '- 只采用同年、同地区、同科目、同卷型且题序一致的来源；补录后在文件头 `来源清单` 中登记来源与所补题号。',
          '- 缺失内容不以其他卷型、默认答案或生成内容替代。',
          f'- 汇总跟踪见 [#148]({ISSUES}148)；读者勘误请使用 [勘误模板]({ISSUES}new?template=erratum.yml)。', '']
    return '\n'.join(L), s


def readme_block(s):
    lines = ['<!-- gwy:gaps:start -->'] + overview(s) + [
        '', '行测每题只计最严重的一级。缺卷以实际举行的考试为准（2016–2026 年）。'
        f'逐卷明细见 [缺口总账](docs/GAP-STATUS.md)，汇总跟踪见 [#148]({ISSUES}148)。', '<!-- gwy:gaps:end -->']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    status, s = status_md(*collect())
    readme_path = ROOT / 'README.md'
    readme = readme_path.read_text(encoding='utf-8')
    readme = re.sub(r'<!-- gwy:gaps:start -->.*?<!-- gwy:gaps:end -->', lambda _: readme_block(s), readme, flags=re.S)
    outputs = {ROOT / 'docs/GAP-STATUS.md': status + '\n', readme_path: readme}
    stale = [p for p, c in outputs.items() if not p.exists() or p.read_text(encoding='utf-8') != c]
    if args.check:
        print('最新' if not stale else '需要重新生成：' + '、'.join(p.relative_to(ROOT).as_posix() for p in stale))
        return 1 if stale else 0
    for p in stale:
        p.write_text(outputs[p], encoding='utf-8')
    print(f'写入 {len(stale)} 个文件；缺卷 {s["missing"]}、待核 {s["pending"]}；'
          f'行测 缺题干 {s["x_stem"]} 缺选项 {s["x_option"]} 缺答案 {s["x_answer"]}；'
          f'申论 缺题目 {s["s_question"]} 缺材料 {s["s_material"]} 缺答案 {s["s_answer"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
