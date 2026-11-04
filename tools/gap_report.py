#!/usr/bin/env python3
"""生成缺口总账 docs/GAP-STATUS.md 与 README 的缺口区块。

缺口分两层：
    槽位台账  2016–2026 年全部应有试卷，每卷一行：已收录、缺卷、待核或无独立考试。
              已收录部分来自 catalog/manifest.jsonl；未收录部分人工维护于 catalog/uncollected-slots.jsonl；
              合并后写出 catalog/exam-slots.jsonl。缺卷 = 台账中状态为「缺卷」的试卷。
同时写出 README 的收录区块与概览仪表盘 docs/assets/dashboard.svg。
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
from coverage_stats import FONT, norm_pt  # noqa: E402

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
    papers = [json.loads(l) for l in (ROOT / 'catalog/uncollected-slots.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
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
    s['questions'] = sum(int(r.get('declared_questions') or 0) for r in rows)
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
         '- **槽位台账**：以实际举行的考试为准，2016–2026 年每份应有试卷（地区 × 年份 × 科目 × 卷型）登记一行，状态为已收录、缺卷、待核或无独立考试。'
         '应有试卷 = 已收录 + 缺卷，缺卷即台账中尚未收录的应有试卷；考试身份或卷型未确认的列为待核，确认后计入。2015 年及以前只统计已收录试卷。',
         '- **局部缺口**：已收录试卷内的缺失，按题计。行测分三级——缺题干、缺选项、缺答案，每题只计最严重的一级；申论分缺题目、缺材料、缺答案。',
         '- **来源**：以粉笔为主，华图与网络检索补充。每份试卷在文件头 `来源` 与 `来源清单` 中记录实际采用的全部来源；缺卷指上述来源均未取得的应有试卷。', '',
         '## 总览', '']
    L += overview(s)
    L += ['', f'已收录试卷 {files:,} 份（2016–2026 年 {len(recent):,} 份）。'
          f"另有 {s['unverified']} 题参考答案已收录、但与题目的对应关系待核，见 [#157]({ISSUES}157)。", '']
    grade = grades(rows, xingce, shenlun)
    L += ['## 试卷健康度', '',
          '每份试卷按最严重的缺口定级：**完整** → **答案待补**（缺参考答案或答案对应待核）→ **缺选项或材料** → **缺题干或题目**。', '',
          '<p align="center"><img src="assets/health.svg" alt="试卷健康度：全库分级与地区年份分布" width="100%"></p>', '']
    L += health_table(rows, grade, papers) + ['']
    # 缺卷
    L += ['## 一、未收录卷次', '', '2016–2026 年每个「地区 × 年份 × 科目」槽位均须为已收录，或在台账中登记为缺卷、待核、无独立考试之一。', '',
          '| 年份 | 地区 | 科目 | 卷型 | 状态 | 依据 |', '| :---: | --- | --- | --- | --- | --- |']
    rank = {'缺卷': 0, '待核': 1, '无独立考试': 2}
    for p in sorted(papers, key=lambda p: (rank[p['status']], -p['year'], p['area'], p['subject'], p['variant'] or '')):
        basis = p['basis']
        basis = f'[招录公告]({basis})' if basis.startswith('http') else basis
        L.append(f"| {p['year']} | {p['area']} | {p['subject']} | {p['variant'] or '待定'} | {p['status']} | {basis} |")
    L += ['', '完整台账见 [`catalog/exam-slots.jsonl`](../catalog/exam-slots.jsonl)（含已收录卷次）；未收录部分维护于 [`catalog/uncollected-slots.jsonl`](../catalog/uncollected-slots.jsonl)。', '']
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


def source_kinds(text):
    """试卷的来源类别：粉笔、华图、网络检索（其余公开来源）。"""
    fm = re.match(r'^---\n(.*?)\n---\n', text, re.S).group(1)
    base = (re.search(r'^来源: (.*)$', fm, re.M) or [None, ''])[1]
    kinds = {'粉笔' if 'fenbi' in base else '网络检索'}
    for party in re.findall(r'^\s+- 来源方: "?([^"\n]+)"?', fm, re.M):
        kinds.add('粉笔' if '粉笔' in party else '华图' if '华图' in party else '网络检索')
    return [k for k in ('粉笔', '华图', '网络检索') if k in kinds]


def slot_ledger(rows, papers):
    """2016–2026 年槽位总台账：每份应有试卷（地区 × 年份 × 科目 × 卷型）一行。"""
    collected = defaultdict(list)
    for r in rows:
        if int(r['year']) >= 2016:
            collected[(series(r), int(r['year']), r['subject'], norm_pt(r.get('paper_type')))].append(r)
    out = []
    for (area, year, subject, _), rs in collected.items():
        kinds = set()
        for r in rs:
            kinds.update(source_kinds((ROOT / r['path']).read_text(encoding='utf-8')))
        out.append({'area': area, 'year': year, 'subject': subject,
                    'variant': Path(rs[0]['path']).stem.split('-', 1)[1], 'status': '已收录',
                    'papers': sorted(r['path'] for r in rs),
                    'sources': [k for k in ('粉笔', '华图', '网络检索') if k in kinds], 'basis': None})
    for p in papers:
        out.append({'area': p['area'], 'year': p['year'], 'subject': p['subject'], 'variant': p['variant'],
                    'status': p['status'], 'papers': [], 'sources': [], 'basis': p['basis']})
    out.sort(key=lambda r: (r['year'], r['area'], r['subject'], r['variant'] or ''))
    return out


def coverage(rows, papers):
    """台账口径：应有试卷 = 已收录 + 缺卷；待核卷次确认开考后计入。2015 年及以前只统计已收录试卷。"""
    ledger = slot_ledger(rows, papers)
    st = Counter(r['status'] for r in ledger)
    src = Counter(k for r in ledger for k in r['sources'])
    recent = {'files': sum(int(r['year']) >= 2016 for r in rows), 'collected': st['已收录'], 'missing': st['缺卷'],
              'pending': st['待核'], 'no_exam': st['无独立考试'], 'sources': src}
    recent['expected'] = recent['collected'] + recent['missing']
    recent['rate'] = recent['collected'] / recent['expected']
    old = [r for r in rows if int(r['year']) < 2016]
    history = {'files': len(old), 'collected': len({(series(r), r['year'], r['subject'], norm_pt(r.get('paper_type'))) for r in old})}
    return {'2016–2026': recent, '2008–2015': history, 'ledger': ledger}


def coverage_block(cov):
    r, h = cov['2016–2026'], cov['2008–2015']
    src = r['sources']
    return '\n'.join([
        '<!-- gwy:coverage:start -->',
        '| 年份 | 应有试卷 | 已收录 | 缺卷 | 待核 | 收录率 |',
        '| :---: | ---: | ---: | ---: | ---: | ---: |',
        f"| **2016–2026** | {r['expected']:,} | {r['collected']:,} | {r['missing']} | {r['pending']} | **{r['rate']:.1%}** |",
        f"| 2008–2015 | — | {h['collected']:,} | — | — | — |",
        '',
        '应有试卷以实际举行的考试为准，按「地区 × 年份 × 科目 × 卷型」逐卷登记于 [槽位台账](catalog/exam-slots.jsonl)，'
        '应有试卷 = 已收录 + 缺卷，收录率 = 已收录 ÷ 应有试卷；待核卷次确认开考后计入，当年无独立试卷的科目不计入。2015 年及以前只统计已收录试卷。',
        '',
        f"来源以粉笔为主，华图与网络检索补充：2016–2026 年已收录试卷中，含粉笔来源 {src['粉笔']:,} 卷、"
        f"华图补充 {src['华图']} 卷、网络检索来源 {src['网络检索']} 卷（一卷可有多个来源）。",
        '<!-- gwy:coverage:end -->'])


def dashboard_svg(rows, s, cov):
    r = cov['2016–2026']
    x = sum(row['subject'] == '行测' for row in rows); z = len(rows) - x
    W, H = 920, 260
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">',
           '<defs><linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2563eb"/><stop offset="1" stop-color="#7c3aed"/></linearGradient></defs>',
           f'<rect width="{W}" height="{H}" rx="16" fill="#ffffff"/>']
    def card(x0, w, title):
        out.append(f'<rect x="{x0}" y="16" width="{w}" height="{H - 32}" rx="14" fill="#f8fafc" stroke="#e2e8f0"/>')
        out.append(f'<text x="{x0 + 20}" y="48" font-size="15" font-weight="700" fill="#0f172a">{title}</text>')
    # 1. 收录率圆环
    card(16, 280, '2016–2026 收录率')
    cx, cy, rad = 96, 150, 54
    import math
    circ = 2 * math.pi * rad
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="none" stroke="#e2e8f0" stroke-width="14"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="none" stroke="url(#ring)" stroke-width="14" stroke-linecap="round" '
               f'stroke-dasharray="{circ * r["rate"]:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})"/>')
    out.append(f'<text x="{cx}" y="{cy + 7}" font-size="21" font-weight="800" fill="#0f172a" text-anchor="middle">{r["rate"]:.1%}</text>')
    for i, (k, v) in enumerate((('应有试卷', f"{r['expected']:,}"), ('已收录', f"{r['collected']:,}"), ('缺卷', r['missing']), ('待核', r['pending']))):
        out.append(f'<text x="172" y="{108 + i * 26}" font-size="12" fill="#64748b">{k}</text>')
        out.append(f'<text x="276" y="{108 + i * 26}" font-size="15" font-weight="700" fill="#0f172a" text-anchor="end">{v}</text>')
    # 2. 科目构成
    card(312, 280, '科目构成')
    total = x + z
    bw = 240
    xw = bw * x / total
    out.append(f'<text x="332" y="96" font-size="30" font-weight="800" fill="#0f172a">{total:,}</text>')
    out.append(f'<text x="332" y="118" font-size="12" fill="#64748b">份试卷 · {s["questions"]:,} 个题位</text>' if 'questions' in s else '')
    out.append(f'<rect x="332" y="140" width="{bw}" height="16" rx="8" fill="#f59e0b"/>')
    out.append(f'<rect x="332" y="140" width="{xw:.1f}" height="16" rx="8" fill="#3b82f6"/>')
    out.append(f'<rect x="{332 + xw - 8:.1f}" y="140" width="8" height="16" fill="#3b82f6"/>')
    for i, (k, v, c) in enumerate((('行测', x, '#3b82f6'), ('申论', z, '#f59e0b'))):
        yy = 186 + i * 28
        out.append(f'<rect x="332" y="{yy - 10}" width="12" height="12" rx="3" fill="{c}"/>')
        out.append(f'<text x="352" y="{yy}" font-size="13" fill="#334155">{k}</text>')
        out.append(f'<text x="572" y="{yy}" font-size="14" font-weight="700" fill="#0f172a" text-anchor="end">{v} 份 · {v / total:.0%}</text>')
    # 3. 局部缺口
    card(608, 296, '已收录试卷的局部缺口')
    items = [('行测 缺题干', s['x_stem'], '#ef4444'), ('行测 缺选项', s['x_option'], '#f97316'),
             ('申论 缺材料', s['s_material'], '#eab308'), ('申论 缺答案', s['s_answer'], '#a855f7')]
    peak = max([v for _, v, _ in items] + [1])
    for i, (k, v, c) in enumerate(items):
        yy = 84 + i * 38
        out.append(f'<text x="628" y="{yy + 4}" font-size="12" fill="#334155">{k}</text>')
        out.append(f'<rect x="712" y="{yy - 8}" width="140" height="14" rx="7" fill="#e2e8f0"/>')
        out.append(f'<rect x="712" y="{yy - 8}" width="{max(6, 140 * v / peak):.1f}" height="14" rx="7" fill="{c}"/>')
        out.append(f'<text x="884" y="{yy + 4}" font-size="13" font-weight="700" fill="#0f172a" text-anchor="end">{v}</text>')
    out.append(f'<text x="628" y="{H - 30}" font-size="11" fill="#94a3b8">单位：题（缺材料为份）· 行测每题只计最严重一级</text>')
    out.append('</svg>')
    return '\n'.join(o for o in out if o) + '\n'


# 试卷健康等级：每份试卷按最严重的缺口定级。
GRADES = [('完整', '#34d399'), ('答案待补', '#fde047'), ('缺选项或材料', '#fb923c'), ('缺题干或题目', '#ef4444')]
MISSING_COLOR = '#334155'


def grades(rows, xingce, shenlun):
    out = {}
    for r in rows:
        x, z = xingce.get(r['path'], {}), shenlun.get(r['path'], {})
        if x.get('stem') or z.get('question'):
            g = 3
        elif x.get('option') or z.get('material'):
            g = 2
        elif x.get('answer') or z.get('answer') or r['path'] in ANSWER_UNVERIFIED:
            g = 1
        else:
            g = 0
        out[r['path']] = g
    return out


def health_table(rows, grade, papers):
    by = defaultdict(lambda: Counter())
    for r in rows:
        by[series(r)][grade[r['path']]] += 1
    for p in papers:
        if p['status'] in ('缺卷', '待核'):
            by[p['area']]['missing' if p['status'] == '缺卷' else 'pending'] += 1
    order = sorted(by, key=lambda a: (a != '国考', -sum(by[a][g] for g in range(4)), a))
    L = ['| 地区 | 已收录 | 完整 | 答案待补 | 缺选项或材料 | 缺题干或题目 | 缺卷 | 待核 |',
         '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    tot = Counter()
    for a in order:
        c = by[a]; n = sum(c[g] for g in range(4))
        for k in list(range(4)) + ['missing', 'pending']:
            tot[k] += c[k]
        cell = lambda k: str(c[k]) if c[k] else '—'
        L.append(f"| {a} | {n} | {cell(0)} | {cell(1)} | {cell(2)} | {cell(3)} | {cell('missing')} | {cell('pending')} |")
    n = sum(tot[g] for g in range(4))
    L.append(f"| **合计** | **{n:,}** | **{tot[0]:,}** | **{tot[1]}** | **{tot[2]}** | **{tot[3]}** | **{tot['missing']}** | **{tot['pending']}** |")
    return L


PENDING_COLOR = '#a78bfa'
NO_EXAM_COLOR = '#ffffff'
UNCOUNTED_COLOR = '#f1f5f9'
UNREGISTERED_COLOR = '#fecdd3'
SUBJECTS = ('行测', '申论')


def series(r):
    """试卷所属的地图行：新疆目录下的兵团卷归入「新疆兵团」。"""
    if r['area'] == '新疆' and '兵团' in (r.get('paper_type') or ''):
        return '新疆兵团'
    return r['area']


def slot_status(rows, grade, papers):
    """{(行, 年份, 科目): (状态, 最差等级或 None, 台账状态集合)}；状态取 收录/缺卷/待核/无独立考试/不统计/未登记。"""
    have = defaultdict(list)
    for r in rows:
        have[(series(r), int(r['year']), r['subject'])].append(grade[r['path']])
    led = defaultdict(set)
    for p in papers:
        led[(p['area'], p['year'], p['subject'])].add(p['status'])
    names = {k[0] for k in have} | {k[0] for k in led}
    out = {}
    for name in names:
        for y in range(2008, 2027):
            for subj in SUBJECTS:
                k = (name, y, subj)
                g, l = have.get(k), led.get(k, set())
                if g:
                    out[k] = ('收录', max(g), l)
                elif '缺卷' in l:
                    out[k] = ('缺卷', None, l)
                elif '待核' in l:
                    out[k] = ('待核', None, l)
                elif '无独立考试' in l:
                    out[k] = ('无独立考试', None, l)
                else:
                    out[k] = ('不统计' if y < 2016 else '未登记', None, l)
    return out


def unregistered(rows, grade, papers):
    return sorted(k for k, v in slot_status(rows, grade, papers).items() if v[0] == '未登记')


def health_svg(rows, grade, papers):
    """上：全库试卷健康度条；下：地区 × 年份槽位图，每格左半为行测、右半为申论。"""
    slots = slot_status(rows, grade, papers)
    names = sorted({k[0] for k in slots}, key=lambda a: (a != '国考', a != '浙江', a in ('新疆兵团', '公安招警和公检法'), a))
    years = list(range(2008, 2027))
    count = Counter(grade.values()); total = sum(count.values())
    states = Counter(v[0] for v in slots.values())
    cw, ch, lw, top = 40, 24, 132, 230
    W = lw + len(years) * cw + 40
    H = top + len(names) * ch + 60
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">',
           '<defs><pattern id="none" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="6" stroke="#cbd5e1" stroke-width="1.5"/></pattern></defs>',
           f'<rect width="{W}" height="{H}" rx="14" fill="#ffffff"/>',
           '<text x="24" y="38" font-size="20" font-weight="700" fill="#0f172a">试卷健康度</text>',
           f'<text x="24" y="62" font-size="13" fill="#64748b">每份试卷按最严重的缺口定级 · 共 {total:,} 份</text>']
    bx, by_, bw = 24, 80, W - 48
    x = bx
    for g, (label, color) in enumerate(GRADES):
        w = bw * count[g] / total
        if w:
            out.append(f'<rect x="{x:.1f}" y="{by_}" width="{max(w, 3):.1f}" height="20" fill="{color}"/>')
        x += w
    out.append(f'<rect x="{bx}" y="{by_}" width="{bw}" height="20" rx="6" fill="none" stroke="#e2e8f0"/>')
    # 图例：两行，覆盖地图中出现的全部状态
    legend = [(f'{label} {count[g]:,} 份', color, None) for g, (label, color) in enumerate(GRADES)]
    status = Counter(p['status'] for p in papers)
    legend += [(f"缺卷 {status['缺卷']} 卷", MISSING_COLOR, None), (f"待核 {status['待核']} 卷", PENDING_COLOR, None),
               (f"无独立考试 {status['无独立考试']} 个科目年份", NO_EXAM_COLOR, 'url(#none)'), ('2015 年及以前未收录（不统计）', UNCOUNTED_COLOR, None)]
    if states['未登记']:
        legend.append((f"未登记 {states['未登记']}", UNREGISTERED_COLOR, None))
    per = 4
    for i, (txt, color, pattern) in enumerate(legend):
        lx = bx + (i % per) * (bw / per)
        ly = by_ + 36 + (i // per) * 24
        out.append(f'<rect x="{lx:.1f}" y="{ly}" width="14" height="14" rx="3" fill="{color}" stroke="#cbd5e1"/>')
        if pattern:
            out.append(f'<rect x="{lx:.1f}" y="{ly}" width="14" height="14" rx="3" fill="{pattern}"/>')
        out.append(f'<text x="{lx + 20:.1f}" y="{ly + 12}" font-size="12" fill="#334155">{txt}</text>')
    out.append(f'<text x="24" y="{top - 34}" font-size="15" font-weight="700" fill="#0f172a">地区 × 年份槽位</text>')
    out.append(f'<text x="{W - 24}" y="{top - 34}" font-size="12" fill="#64748b" text-anchor="end">每格左半为行测、右半为申论 · 角标表示同科目另有缺卷（深色）或待核（紫色）卷型</text>')
    for i, y in enumerate(years):
        out.append(f'<text x="{lw + i * cw + cw / 2}" y="{top - 8}" font-size="11" fill="#475569" text-anchor="middle">{y}</text>')
    half = (cw - 9) / 2
    for r, name in enumerate(names):
        yy = top + r * ch
        out.append(f'<text x="{lw - 12}" y="{yy + ch / 2 + 4}" font-size="12" fill="#334155" text-anchor="end">{name}</text>')
        for i, y in enumerate(years):
            for j, subj in enumerate(SUBJECTS):
                state, g, led = slots[(name, y, subj)]
                xx = lw + i * cw + 4 + j * (half + 1)
                fill = {'收录': GRADES[g][1] if g is not None else None, '缺卷': MISSING_COLOR, '待核': PENDING_COLOR,
                        '无独立考试': NO_EXAM_COLOR, '不统计': UNCOUNTED_COLOR, '未登记': UNREGISTERED_COLOR}[state]
                out.append(f'<rect x="{xx:.1f}" y="{yy + 2}" width="{half:.1f}" height="{ch - 4}" rx="3" fill="{fill}"/>')
                if state == '无独立考试':
                    out.append(f'<rect x="{xx:.1f}" y="{yy + 2}" width="{half:.1f}" height="{ch - 4}" rx="3" fill="url(#none)" stroke="#e2e8f0"/>')
                if state == '收录' and ('缺卷' in led or '待核' in led):
                    c = MISSING_COLOR if '缺卷' in led else PENDING_COLOR
                    out.append(f'<path d="M{xx + half - 8:.1f} {yy + 2} H{xx + half:.1f} V{yy + 10} Z" fill="{c}"/>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def readme_block(s):
    lines = ['<!-- gwy:gaps:start -->'] + overview(s) + [
        '', '行测每题只计最严重的一级。缺卷以实际举行的考试为准（2016–2026 年）。'
        f'逐卷明细见 [缺口总账](docs/GAP-STATUS.md)，汇总跟踪见 [#148]({ISSUES}148)。', '<!-- gwy:gaps:end -->']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = collect()
    status, s = status_md(*data)
    cov = coverage(data[0], data[3])
    readme_path = ROOT / 'README.md'
    readme = readme_path.read_text(encoding='utf-8')
    for name, block in (('gaps', readme_block(s)), ('coverage', coverage_block(cov))):
        readme = re.sub(rf'<!-- gwy:{name}:start -->.*?<!-- gwy:{name}:end -->', lambda _: block, readme, flags=re.S)
    outputs = {ROOT / 'docs/GAP-STATUS.md': status + '\n', readme_path: readme,
               ROOT / 'docs/assets/dashboard.svg': dashboard_svg(data[0], s, cov),
               ROOT / 'docs/assets/health.svg': health_svg(data[0], grades(data[0], data[1], data[2]), data[3]),
               ROOT / 'catalog/exam-slots.jsonl': ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in cov['ledger'])}
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
