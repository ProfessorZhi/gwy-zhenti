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
import html
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


# 专项收录：非国考、省考的招录考试（公安院校联考、政法干警等）。试卷照常收录与浏览，
# 但不进入槽位台账，不计入应有试卷、收录率与缺口统计。
SPECIAL_COLLECTIONS = ('公安招警和公检法',)


def special_rows():
    rows = [json.loads(l) for l in (ROOT / 'catalog/manifest.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    return [r for r in rows if r['area'] in SPECIAL_COLLECTIONS]


def collect():
    rows = [json.loads(l) for l in (ROOT / 'catalog/manifest.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if r['area'] not in SPECIAL_COLLECTIONS]
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
    papers = [p for p in papers if p['area'] not in SPECIAL_COLLECTIONS]
    return rows, xingce, shenlun, papers


def summary(rows, xingce, shenlun, papers, lo=0, hi=9999):
    s = Counter()
    year = {r['path']: int(r['year']) for r in rows}
    for path, v in xingce.items():
        if lo <= year[path] <= hi:
            for k in ('stem', 'option', 'answer'):
                s['x_' + k] += len(v[k]); s['xp_' + k] += bool(v[k])
    for path, v in shenlun.items():
        if lo <= year[path] <= hi:
            for k in ('question', 'material', 'answer'):
                s['s_' + k] += len(v[k]); s['sp_' + k] += bool(v[k])
    s['missing'] = sum(p['status'] == '缺卷' for p in papers if lo <= p['year'] <= hi)
    s['pending'] = sum(p['status'] == '待核' for p in papers if lo <= p['year'] <= hi)
    s['unverified'] = sum(len(v) for v in ANSWER_UNVERIFIED.values())
    s['questions'] = sum(int(r.get('declared_questions') or 0) for r in rows)
    return s


def num(n, unit):
    return f'{n} {unit}' if n else '—'


def overview(new, old):
    """缺口总表：2016–2026 与 2008–2015 分列；2015 年及以前不判定缺卷。"""
    def pq(n, p, unit='题'):
        return f'{n} {unit} · {p} 卷' if n else '—'
    rows = [('**缺卷**', '已确认缺卷', num(new['missing'], '卷'), '不判定', f'[#160]({ISSUES}160)'),
            ('', '考试身份待核', num(new['pending'], '卷'), '不判定', f'[#161]({ISSUES}161)')]
    for label, key, unit, issue in (('**行测**|缺题干', 'stem', '题', f'[#155]({ISSUES}155) [#156]({ISSUES}156)'),
                                    ('|缺选项', 'option', '题', f'[#157]({ISSUES}157)'), ('|缺答案', 'answer', '题', '')):
        a, b_ = label.split('|')
        rows.append((a, b_, pq(new['x_' + key], new['xp_' + key], unit), pq(old['x_' + key], old['xp_' + key], unit), issue))
    for label, key, unit, issue in (('**申论**|缺题目', 'question', '题', ''), ('|缺材料', 'material', '份材料', f'[#159]({ISSUES}159)'),
                                    ('|缺答案', 'answer', '题', f'[#158]({ISSUES}158)')):
        a, b_ = label.split('|')
        rows.append((a, b_, pq(new['s_' + key], new['sp_' + key], unit), pq(old['s_' + key], old['sp_' + key], unit), issue))
    return ['| 层级 | 类别 | 2016–2026 | 2008–2015 | 跟踪 |', '| --- | --- | ---: | ---: | :---: |'] + \
           [f'| {a} | {b_} | {c} | {d} | {e} |' for a, b_, c, d, e in rows]


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
         f'- **专项收录**：公安招警和公检法（公安院校联考、政法干警等）不属于国考、省考，{len(special_rows())} 份试卷照常收录、可在目录中浏览，但不进入槽位台账，不计入应有试卷、收录率与缺口统计。',
         '- **局部缺口**：已收录试卷内的缺失，按题计。行测分三级——缺题干、缺选项、缺答案，每题只计最严重的一级；申论分缺题目、缺材料、缺答案。',
         '- **来源**：以粉笔为主，华图与网络检索补充。每份试卷在文件头 `来源` 与 `来源清单` 中记录实际采用的全部来源；缺卷指上述来源均未取得的应有试卷。', '',
         '## 总览', '']
    s_new, s_old = summary(rows, xingce, shenlun, papers, 2016, 2026), summary(rows, xingce, shenlun, papers, 0, 2015)
    L += overview(s_new, s_old)
    L += ['', f'已收录试卷 {files:,} 份（2016–2026 年 {len(recent):,} 份）。'
          f"另有 {s['unverified']} 题参考答案已收录、但与题目的对应关系待核，见 [#157]({ISSUES}157)。", '']
    grade = grades(rows, xingce, shenlun)
    L += ['## 逐卷分布与健康度', '',
          '每份试卷按最严重的缺口定级：**完整** → **答案待补**（缺参考答案或答案对应待核）→ **缺选项或材料** → **缺题干或题目**。', '',
          scroll_img('assets/health.svg', '逐卷分布与健康度：2008–2026 年各地区各年份的每份试卷及其状态', health_svg(rows, grade, papers)), '']
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
        '应有试卷 = 已收录 + 缺卷，收录率 = 已收录 ÷ 应有试卷；待核卷次确认开考后计入，当年无独立试卷的科目不计入。2015 年及以前只统计已收录试卷。'
        f'公安招警和公检法（公安院校联考、政法干警等）{len(special_rows())} 份为专项收录，可在目录中浏览，不计入台账与缺口统计。',
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
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{rad}" fill="none" stroke="url(#ring)" stroke-width="14" stroke-linecap="butt" '
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
GRADES = [('完整', '#34d399'), ('答案待补', '#fcd34d'), ('缺选项或材料', '#fb923c'), ('缺题干或题目', '#f43f5e')]
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


PENDING_COLOR = '#c4b5fd'
NO_EXAM_COLOR = '#f1f5f9'
UNCOUNTED_COLOR = '#f8fafc'
UNREGISTERED_COLOR = '#fecdd3'
SUBJECTS = ('行测', '申论')
FOCUS = ['国考', '浙江', '江苏', '上海', '北京', '天津', '广东', '广州', '深圳', '福建']
SPECIAL = ['新疆兵团']


def series(r):
    """试卷所属的地图行，即地区。"""
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


SCROLL_HINT = '← 左右滑动查看全部年份 · 点击图片查看原图 →'


def scroll_img(src, alt, svg):
    """按原始尺寸嵌入宽图。GitHub 把表格设为可横向滚动，但图片默认按格宽缩小；
    图上的提示行用不断行字符补足到图宽，撑开单元格，过宽时整张图左右滑动而不被压缩。"""
    w = int(re.search(r'width="(\d+)"', svg).group(1))
    hint = '\u2060'.join(SCROLL_HINT).replace(' ', '&nbsp;')
    used = sum(12 if ord(c) > 255 else 6.5 for c in SCROLL_HINT)      # <sub> 字号约 12px
    pad = '&nbsp;' * max(0, round((w - used) / 3.3))                  # 不断行空格约 3.1–3.4px，因字体而异
    return (f'<table><tr><td><sub>{hint}{pad}</sub><br>'
            f'<a href="{src}"><img src="{src}" alt="{alt}" width="{w}"></a></td></tr></table>')


def paper_marks(rows, grade, papers):
    """{(地区, 年份, 科目): [(状态, 等级, 提示)]}，一份试卷一个标记。
    状态：收录、缺卷、待核；无试卷的槽位给一个 无独立考试 或 未收录 标记，保证每格都有图例状态。"""
    marks = defaultdict(list)
    for r in sorted(rows, key=lambda r: (norm_pt(r.get('paper_type')) or '', r['path'])):
        g = grade[r['path']]
        tip = f"{r['path'][:-3]} · {GRADES[g][0]}"
        marks[(series(r), int(r['year']), r['subject'])].append(('收录', g, tip))
    for p in sorted(papers, key=lambda p: (p['status'], p['variant'] or '')):
        if p['status'] in ('缺卷', '待核'):
            tip = f"{p['area']} {p['year']} {p['subject']}-{p['variant'] or '卷型待定'} · {p['status']}"
            marks[(p['area'], p['year'], p['subject'])].append((p['status'], None, tip))
    for (name, y, subj), (state, _, _) in slot_status(rows, grade, papers).items():
        if not marks.get((name, y, subj)):
            label = {'无独立考试': '无独立考试', '不统计': '未收录'}.get(state, state)
            marks[(name, y, subj)].append((label, None, f'{name} {y} {subj} · {label}'))
    return marks


MARK_COLORS = {'缺卷': MISSING_COLOR, '待核': PENDING_COLOR}


def health_svg(rows, grade, papers):
    """逐卷分布与健康度（2008–2026）：每个地区分行测、申论两行，每格内一份试卷一个方块，
    方块数即该年该科目的试卷数，颜色为试卷健康等级或台账状态；无试卷的格子标为无独立考试或未收录。
    2016 年起按槽位台账统计缺卷，2015 年及以前只统计已收录试卷。"""
    marks = paper_marks(rows, grade, papers)
    names = {k[0] for k in marks}
    groups = [('国考与重点地区', [n for n in FOCUS if n in names]),
              ('其他省份', sorted(n for n in names if n not in FOCUS and n not in SPECIAL)),
              ('新疆兵团', [n for n in SPECIAL if n in names])]
    old, new = list(range(2008, 2016)), list(range(2016, 2027))
    sq, gap, pad = 10, 2, 5                                  # 方块边长、间距、格内边距
    per = max(len(v) for v in marks.values())
    cw = per * (sq + gap) - gap + pad * 2 + 4
    sub, pair = 15, 38                                       # 科目行高、地区行高
    lw, split = 172, 22
    sw_new, sw_old = 150, 70                                 # 两段的行尾汇总列宽
    xcol = {y: lw + i * cw for i, y in enumerate(new)}       # 先 2016–2026，再 2008–2015
    rx0 = xcol[2026] + cw + 12                               # 2016–2026 汇总列
    xcol.update({y: rx0 + sw_new + split + i * cw for i, y in enumerate(old)})
    ox0 = xcol[2015] + cw + 12                               # 2008–2015 汇总列
    W = ox0 + sw_old + 20
    top = 296
    H = top + sum(len(m) for _, m in groups) * pair + len(groups) * 36 + 60
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">',
           '<defs><pattern id="none" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="4" stroke="#94a3b8" stroke-width="1.2"/></pattern></defs>',
           f'<rect width="{W}" height="{H}" rx="18" fill="#ffffff" stroke="#e2e8f0"/>',
           '<text x="28" y="44" font-size="24" font-weight="800" fill="#0f172a">逐卷分布与健康度 · 2008–2026</text>',
           '<text x="28" y="70" font-size="13" fill="#64748b">每个方块是一份试卷：方块数为该地区当年该科目的试卷数，颜色为健康等级或台账状态；'
           '左侧 2016–2026 按槽位台账统计缺卷，右侧 2008–2015 只统计已收录试卷</text>']

    def card(x, w, title, sub_, segs, total):
        out.append(f'<rect x="{x}" y="90" width="{w}" height="86" rx="14" fill="#f8fafc" stroke="#e2e8f0"/>')
        out.append(f'<text x="{x + 18}" y="116" font-size="15" font-weight="800" fill="#0f172a">{title}</text>')
        out.append(f'<text x="{x + w - 18}" y="116" font-size="12" fill="#475569" text-anchor="end">{sub_}</text>')
        out.append(f'<clipPath id="c{x}"><rect x="{x + 18}" y="130" width="{w - 36}" height="14" rx="7"/></clipPath>')
        out.append(f'<g clip-path="url(#c{x})"><rect x="{x + 18}" y="130" width="{w - 36}" height="14" fill="#e2e8f0"/>')
        xx = x + 18
        for v, c, _ in segs:
            ww = (w - 36) * v / total if total else 0
            if v:
                out.append(f'<rect x="{xx:.1f}" y="130" width="{max(ww, 3):.1f}" height="14" fill="{c}"/>')
            xx += ww
        out.append('</g>')
        lx = x + 18
        for v, c, label in segs:
            if v:
                out.append(f'<rect x="{lx}" y="155" width="10" height="10" rx="2" fill="{c}"/>')
                out.append(f'<text x="{lx + 15}" y="164" font-size="11.5" fill="#475569">{label} '
                           f'<tspan font-weight="700" fill="#0f172a">{v:,}</tspan></text>')
                lx += 34 + len(label) * 11.5 + len(f'{v:,}') * 7

    for lo, hi, x0, x1 in ((2016, 2026, 28, rx0 + sw_new), (2008, 2015, xcol[2008], W - 28)):
        period = [r for r in rows if lo <= int(r['year']) <= hi]
        cnt = Counter(grade[r['path']] for r in period); n = len(period)
        segs = [(cnt[g], c, label) for g, (label, c) in enumerate(GRADES)]
        if lo >= 2016:
            cov = coverage(rows, papers)['2016–2026']
            segs.append((cov['missing'], MISSING_COLOR, '缺卷'))
            card(x0, x1 - x0, f'{lo} – {hi} · 按槽位台账',
                 f"应有 {cov['expected']:,} 卷 · 收录率 {cov['rate']:.1%} · 已收录试卷 {n:,} 份，完整率 {cnt[0] / n:.1%}",
                 segs, n + cov['missing'])
        else:
            card(x0, x1 - x0, f'{lo} – {hi} · 只计已收录', f'已收录试卷 {n:,} 份，完整率 {cnt[0] / n:.1%}', segs, n)

    def square(x, y, state, g, tip):
        t = f'<title>{html.escape(tip)}</title>'
        if state == '收录':
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{sq}" height="{sq}" rx="2" fill="{GRADES[g][1]}">{t}</rect>')
        elif state in MARK_COLORS:
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{sq}" height="{sq}" rx="2" fill="{MARK_COLORS[state]}">{t}</rect>')
        elif state == '无独立考试':
            out.append(f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{sq - 1}" height="{sq - 1}" rx="2" fill="url(#none)" stroke="#94a3b8" stroke-width="0.8">{t}</rect>')
        else:                                                # 未收录（2015 年及以前不判定缺卷）
            out.append(f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{sq - 1}" height="{sq - 1}" rx="2" fill="#ffffff" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="2 1.5">{t}</rect>')

    # 图例
    legend = [(label, '收录', g) for g, (label, _) in enumerate(GRADES)] + [
        ('缺卷', '缺卷', None), ('待核', '待核', None), ('无独立考试', '无独立考试', None), ('未收录（2015 年及以前不判定缺卷）', '未收录', None)]
    px, py = 28, 192
    for txt, state, g in legend:
        w = 36 + sum(12.5 if ord(c) > 255 else 7 for c in txt)
        out.append(f'<rect x="{px:.1f}" y="{py}" width="{w:.1f}" height="26" rx="13" fill="#ffffff" stroke="#e2e8f0"/>')
        square(px + 11, py + 8.5, state, g, txt)
        out.append(f'<text x="{px + 27:.1f}" y="{py + 17.5}" font-size="12" fill="#334155">{txt}</text>')
        px += w + 8
    out.append(f'<text x="28" y="{py + 48}" font-size="11.5" fill="#64748b">每个地区上行为行测、下行为申论；同格内方块按卷型排列。点击图片打开原图后，鼠标悬停方块可查看对应试卷。</text>')
    # 年份表头
    for y, x in xcol.items():
        out.append(f'<text x="{x + cw / 2}" y="{top - 10}" font-size="12.5" font-weight="700" fill="#334155" text-anchor="middle">{y}</text>')
    out.append(f'<text x="{rx0 + 8}" y="{top - 10}" font-size="11" font-weight="700" fill="#334155">完整 / 应有</text>')
    out.append(f'<text x="{ox0 + 4}" y="{top - 10}" font-size="11" font-weight="700" fill="#334155">完整 / 已收录</text>')
    dx = xcol[2008] - split / 2
    out.append(f'<line x1="{dx}" y1="{top - 26}" x2="{dx}" y2="{H - 44}" stroke="#cbd5e1" stroke-dasharray="4 3"/>')
    done = defaultdict(Counter); need = defaultdict(Counter)
    for r in rows:
        k = 'new' if int(r['year']) >= 2016 else 'old'
        need[series(r)][k] += 1
        done[series(r)][k] += grade[r['path']] == 0
    for p in papers:
        if p['status'] == '缺卷':
            need[p['area']]['new'] += 1
    y0 = top
    stripe = 0
    for title, members in groups:
        if not members:
            continue
        y0 += 8
        out.append(f'<text x="28" y="{y0 + 13}" font-size="12" font-weight="800" fill="#475569">{title}</text>')
        out.append(f'<line x1="{28 + len(title) * 13 + 10}" y1="{y0 + 9}" x2="{W - 28}" y2="{y0 + 9}" stroke="#e2e8f0"/>')
        y0 += 28
        for name in members:
            if stripe % 2:
                out.append(f'<rect x="20" y="{y0 - 2}" width="{W - 40}" height="{pair - 2}" rx="8" fill="#f8fafc"/>')
            stripe += 1
            out.append(f'<text x="{lw - 40}" y="{y0 + pair / 2 + 3}" font-size="13" font-weight="600" fill="#1e293b" text-anchor="end">{name}</text>')
            for y, x in xcol.items():
                out.append(f'<rect x="{x + 2}" y="{y0 + 1}" width="{cw - 4}" height="{pair - 6}" rx="6" fill="#f1f5f9"/>')
            for j, subj in enumerate(SUBJECTS):
                yy = y0 + 4 + j * sub
                out.append(f'<text x="{lw - 10}" y="{yy + 9}" font-size="9.5" fill="#94a3b8" text-anchor="end">{subj}</text>')
                for y, x in xcol.items():
                    ms = marks[(name, y, subj)]
                    x0 = x + (cw - (len(ms) * (sq + gap) - gap)) / 2
                    for k, (state, g, tip) in enumerate(ms):
                        square(x0 + k * (sq + gap), yy, state, g, tip)
            d, n = done[name]['new'], need[name]['new']
            out.append(f'<rect x="{rx0 + 8}" y="{y0 + 11}" width="76" height="8" rx="4" fill="#e2e8f0"/>')
            if n:
                out.append(f'<rect x="{rx0 + 8}" y="{y0 + 11}" width="{76 * d / n:.1f}" height="8" rx="4" fill="#34d399"/>')
            out.append(f'<text x="{rx0 + 92}" y="{y0 + 19}" font-size="11.5" fill="#334155">{d}/{n}</text>')
            do, no = done[name]['old'], need[name]['old']
            out.append(f'<text x="{ox0 + 4}" y="{y0 + 19}" font-size="11.5" fill="#64748b">{f"{do}/{no}" if no else "—"}</text>')
            y0 += pair
    out.append(f'<text x="28" y="{H - 20}" font-size="11.5" fill="#94a3b8">2016–2026 汇总为 完整/应有（应有 = 已收录 + 缺卷），2008–2015 汇总为 完整/已收录 · '
               '广州 2019 年起并入广东省考 · 公安招警和公检法为专项收录，不在本图 · 状态来自槽位台账 catalog/exam-slots.jsonl</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def readme_block(new, old):
    lines = ['<!-- gwy:gaps:start -->'] + overview(new, old) + [
        '', '行测每题只计最严重的一级。缺卷以实际举行的考试为准，仅统计 2016–2026 年；2015 年及以前只统计已收录试卷的局部缺口。'
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
    s_new = summary(data[0], data[1], data[2], data[3], 2016, 2026)
    s_old = summary(data[0], data[1], data[2], data[3], 0, 2015)
    health = health_svg(data[0], grades(data[0], data[1], data[2]), data[3])
    health_block = '<!-- gwy:health:start -->\n' + scroll_img('docs/assets/health.svg', '逐卷分布与健康度：2008–2026 年各地区各年份的每份试卷及其状态', health) + '\n<!-- gwy:health:end -->'
    for name, block in (('gaps', readme_block(s_new, s_old)), ('coverage', coverage_block(cov)), ('health', health_block)):
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
