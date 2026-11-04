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
         '- **局部缺口**：已收录试卷内的缺失，按题计。行测分三级——缺题干、缺选项、缺答案，每题只计最严重的一级；申论分缺题目、缺材料、缺答案。',
         '- **来源**：以粉笔为主，华图与网络检索补充。每份试卷在文件头 `来源` 与 `来源清单` 中记录实际采用的全部来源；缺卷指上述来源均未取得的应有试卷。', '',
         '## 总览', '']
    s_new, s_old = summary(rows, xingce, shenlun, papers, 2016, 2026), summary(rows, xingce, shenlun, papers, 0, 2015)
    L += overview(s_new, s_old)
    L += ['', f'已收录试卷 {files:,} 份（2016–2026 年 {len(recent):,} 份）。'
          f"另有 {s['unverified']} 题参考答案已收录、但与题目的对应关系待核，见 [#157]({ISSUES}157)。", '']
    grade = grades(rows, xingce, shenlun)
    L += ['## 试卷健康度', '',
          '每份试卷按最严重的缺口定级：**完整** → **答案待补**（缺参考答案或答案对应待核）→ **缺选项或材料** → **缺题干或题目**。', '',
          ]
    L += slots_md(rows, grade, papers, '###') + ['### 按地区汇总', '']
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


# 试卷健康等级：每份试卷按最严重的缺口定级，0 完整、1 答案待补、2 缺选项或材料、3 缺题干或题目。


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


SUBJECTS = ('行测', '申论')
FOCUS = ['国考', '浙江', '江苏', '上海', '北京', '天津', '广东', '广州', '深圳', '福建']
SPECIAL = ['新疆兵团', '公安招警和公检法']


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


# 槽位表：地区 × 年份的 Markdown 表格，每格两个符号依次为行测、申论。
# 表格在 GitHub 上过宽时可横向滑动，文字不随页面缩小。
MARKS = [('🟩', '完整'), ('🟨', '答案待补'), ('🟧', '缺选项或材料'), ('🟥', '缺题干或题目'),
         ('🟫', '已收录部分卷型，另有卷型缺卷'), ('⬛', '缺卷'), ('🟪', '待核'), ('➖', '无独立考试'),
         ('⬜', '未收录（2015 年及以前不判定缺卷）')]
MARK = dict((v, k) for k, v in MARKS)


def slot_mark(state, g, led):
    if state == '收录':
        return MARK['已收录部分卷型，另有卷型缺卷'] if '缺卷' in led else MARKS[g][0]
    return {'缺卷': '⬛', '待核': '🟪', '无独立考试': '➖', '不统计': '⬜'}.get(state, '❔')


def slot_legend():
    return ['图例：' + ' · '.join(f'{m} {t}' for m, t in MARKS), '']


def slot_table(rows, grade, papers, lo, hi, prefix=''):
    """地区 × 年份槽位表。2016 年起每行末尾为 完整/应有（应有 = 已收录 + 缺卷）；2015 年及以前为 完整/已收录。"""
    recent = lo >= 2016
    slots = slot_status(rows, grade, papers)
    period = [r for r in rows if lo <= int(r['year']) <= hi]
    names = {k[0] for k in slots} if recent else {series(r) for r in period}
    order = ([n for n in FOCUS if n in names] + sorted(n for n in names if n not in FOCUS and n not in SPECIAL)
             + [n for n in SPECIAL if n in names])
    done, have = Counter(), Counter()
    for r in period:
        have[series(r)] += 1
        done[series(r)] += grade[r['path']] == 0
    missing = Counter(p['area'] for p in papers if p['status'] == '缺卷' and lo <= p['year'] <= hi)
    years = list(range(lo, hi + 1))
    tail = ['完整\u2060/\u2060应有', '缺卷'] if recent else ['完整\u2060/\u2060已收录']
    L = ['| 地区 | ' + ' | '.join(str(y) for y in years) + ' | ' + ' | '.join(tail) + ' |',
         '| --- | ' + ' | '.join(':---:' for _ in years) + ' | ' + ' | '.join('---:' for _ in tail) + ' |']
    nb = '\u2060'.join  # 字间插入不可断字符，表格变窄时整格不折行，改为横向滑动
    for n in order:
        cells = [nb(slot_mark(*slots[(n, y, s)]) for s in SUBJECTS) for y in years]
        if recent:
            end = [f'{done[n]}/{have[n] + missing[n]}', str(missing[n]) if missing[n] else '0']
        else:
            end = [f'{done[n]}/{have[n]}']
        L.append(f'| {nb(n)} | ' + ' | '.join(cells) + ' | ' + ' | '.join(end) + ' |')
    return L


def slots_md(rows, grade, papers, h):
    """两段槽位表：2016–2026 按台账，2008–2015 只看已收录试卷。"""
    return (slot_legend()
            + ['每格两个符号依次为**行测、申论**；同一科目有多个卷型时取最差的一份。表格较宽时可左右滑动。', '',
               f'{h} 2016–2026 年', '']
            + slot_table(rows, grade, papers, 2016, 2026)
            + ['', '行末「完整/应有」中，应有 = 已收录 + 缺卷；广州 2019 年起并入广东省考，无独立考试。', '',
               f'{h} 2008–2015 年', '']
            + slot_table(rows, grade, papers, 2008, 2015)
            + ['', '2015 年及以前只统计已收录试卷的局部缺口，不判定缺卷。', ''])


def slots_block(rows, grade, papers):
    return '\n'.join(['<!-- gwy:slots:start -->'] + slots_md(rows, grade, papers, '####') + ['<!-- gwy:slots:end -->'])


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
    grade = grades(data[0], data[1], data[2])
    for name, block in (('gaps', readme_block(s_new, s_old)), ('coverage', coverage_block(cov)),
                        ('slots', slots_block(data[0], grade, data[3]))):
        readme = re.sub(rf'<!-- gwy:{name}:start -->.*?<!-- gwy:{name}:end -->', lambda _: block, readme, flags=re.S)
    outputs = {ROOT / 'docs/GAP-STATUS.md': status + '\n', readme_path: readme,
               ROOT / 'docs/assets/dashboard.svg': dashboard_svg(data[0], s, cov),
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
