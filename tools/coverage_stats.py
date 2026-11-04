#!/usr/bin/env python3
"""从 catalog/manifest.jsonl 统计覆盖情况，并可重新生成 docs 里的两张 SVG。

用法：
    python3 tools/coverage_stats.py                     # 终端摘要
    python3 tools/coverage_stats.py --json stats.json   # 额外输出逐卷数据
    python3 tools/coverage_stats.py --svg docs/assets   # 重写覆盖热力图与逐年柱状图
"""

import argparse
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L1 = {'浙江'}
L2 = {'国考', '江苏', '上海', '北京', '天津', '广东', '广州', '深圳', '福建'}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif"


def norm_pt(pt):
    """归一化卷型：去掉尾部试卷 ID、统一全/半角冒号与甲/乙、A/B/C 写法。"""
    x = re.sub(r'-\d{5,}$', '', pt or '')
    x = x.replace('：', '-').replace(':', '-')
    x = re.sub(r'^卷(甲|乙)级$', r'\1级', x)
    x = re.sub(r'^(甲|乙)卷$', r'\1级', x)
    x = re.sub(r'^(A|B|C)卷$', r'\1类', x)
    if x.endswith('卷') and len(x) > 2:
        x = x[:-1]
    return x


def tier(area):
    return 'L1' if area in L1 else ('L2' if area in L2 else 'L3')


def load_rows():
    rows = []
    path = os.path.join(ROOT, 'catalog/manifest.jsonl')
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            parts = rec['path'].split('/')
            area = '国考' if parts[0] == '国考' else parts[1]
            # 题目口径取卷面声明题数；29 份旧格式申论卷没有 `### 第 N 题` 锚点，
            # 只数锚点会漏掉 91 题（65,363 vs 65,454）。
            declared = rec.get('declared_questions')
            anchors = rec.get('question_anchors')
            rows.append({
                'area': area,
                'year': rec['year'],
                'subject': rec['subject'],
                'pt': rec.get('paper_type') or '',
                'pt2': norm_pt(rec.get('paper_type')),
                'path': rec['path'],
                'q': declared if isinstance(declared, int) else (anchors if isinstance(anchors, int) else len(anchors or [])),
                'img': rec.get('image_references') or 0,
            })
    return rows


def summarize(rows):
    slots = collections.defaultdict(list)
    for row in rows:
        slots[(row['area'], row['year'], row['subject'], row['pt2'])].append(row)
    years = sorted({int(r['year']) for r in rows})
    out = {
        'files': len(rows),
        'slots': len(slots),
        'areas': len({r['area'] for r in rows}),
        'years': years,
        'subject': dict(collections.Counter(r['subject'] for r in rows)),
        'questions': sum(r['q'] for r in rows),
        'images': sum(r['img'] for r in rows),
        'multi': sum(1 for v in slots.values() if len(v) > 1),
        'tiers': {},
        'by_area': {},
        'by_year': {},
    }
    for name in ('L1', 'L2', 'L3'):
        files = [r for r in rows if tier(r['area']) == name]
        out['tiers'][name] = {
            'slots': sum(1 for k in slots if tier(k[0]) == name),
            'files': len(files),
            'questions': sum(r['q'] for r in files),
        }
    for area in sorted({r['area'] for r in rows}):
        files = [r for r in rows if r['area'] == area]
        out['by_area'][area] = {
            'tier': tier(area),
            'files': len(files),
            'xingce': sum(1 for r in files if r['subject'] == '行测'),
            'shenlun': sum(1 for r in files if r['subject'] == '申论'),
            'questions': sum(r['q'] for r in files),
            'images': sum(r['img'] for r in files),
        }
    grid = collections.Counter((r['area'], r['year']) for r in rows)
    out['grid'] = {f'{a}|{y}': n for (a, y), n in grid.items()}
    for (year, subject), n in collections.Counter((r['year'], r['subject']) for r in rows).items():
        out['by_year'].setdefault(year, {'行测': 0, '申论': 0})[subject] = n
    return out


def heatmap_svg(stats):
    """地区 × 年份热力图：每格为该地区该年的试卷份数，右侧为地区合计，底部为年份合计。"""
    areas = sorted(stats['by_area'], key=lambda a: ({'L1': 0, 'L2': 1}.get(stats['by_area'][a]['tier'], 2), a))
    years = [str(y) for y in range(min(stats['years']), max(stats['years']) + 1)]
    cw, ch, lw, top = 40, 26, 132, 104
    gw = len(years) * cw
    width = lw + gw + 70
    height = top + len(areas) * ch + 110
    palette = ['#eff6ff', '#dbeafe', '#93c5fd', '#3b82f6', '#1d4ed8', '#1e3a8a']
    color = lambda n: palette[min(n, 5)] if n else '#f8fafc'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">',
           f'<rect width="{width}" height="{height}" rx="14" fill="#ffffff"/>',
           f'<text x="24" y="38" font-size="20" font-weight="700" fill="#0f172a">地区 × 年份收录分布</text>',
           f'<text x="24" y="62" font-size="13" fill="#64748b">单元格为该地区当年收录的试卷份数 · 共 {stats["files"]:,} 份 · '
           f'{stats["areas"]} 个地区 · {min(stats["years"])}–{max(stats["years"])}</text>']
    for i, year in enumerate(years):
        out.append(f'<text x="{lw + i * cw + cw / 2}" y="{top - 12}" font-size="11" fill="#475569" text-anchor="middle">{year}</text>')
    out.append(f'<text x="{lw + gw + 36}" y="{top - 12}" font-size="11" font-weight="700" fill="#475569" text-anchor="middle">合计</text>')
    col = collections.Counter()
    for r, area in enumerate(areas):
        y = top + r * ch
        if r and stats['by_area'][area]['tier'] != stats['by_area'][areas[r - 1]]['tier']:
            out.append(f'<line x1="24" y1="{y}" x2="{width - 24}" y2="{y}" stroke="#cbd5e1" stroke-dasharray="4 4"/>')
        out.append(f'<text x="{lw - 12}" y="{y + ch / 2 + 4}" font-size="12" fill="#334155" text-anchor="end">{area}</text>')
        total = 0
        for i, year in enumerate(years):
            n = stats['grid'].get(f'{area}|{year}', 0)
            total += n; col[year] += n
            x = lw + i * cw
            out.append(f'<rect x="{x + 2}" y="{y + 2}" width="{cw - 4}" height="{ch - 4}" rx="5" fill="{color(n)}"/>')
            if n:
                out.append(f'<text x="{x + cw / 2}" y="{y + ch / 2 + 4}" font-size="11" fill="{"#ffffff" if n >= 3 else "#1e3a8a"}" text-anchor="middle">{n}</text>')
        out.append(f'<text x="{lw + gw + 36}" y="{y + ch / 2 + 4}" font-size="12" font-weight="700" fill="#0f172a" text-anchor="middle">{total}</text>')
    yb = top + len(areas) * ch + 8
    out.append(f'<line x1="24" y1="{yb - 4}" x2="{width - 24}" y2="{yb - 4}" stroke="#e2e8f0"/>')
    out.append(f'<text x="{lw - 12}" y="{yb + 14}" font-size="12" font-weight="700" fill="#475569" text-anchor="end">合计</text>')
    for i, year in enumerate(years):
        out.append(f'<text x="{lw + i * cw + cw / 2}" y="{yb + 14}" font-size="11" font-weight="700" fill="#0f172a" text-anchor="middle">{col[year]}</text>')
    ly = yb + 52
    out.append(f'<text x="24" y="{ly}" font-size="12" fill="#475569">份数</text>')
    for i, (label, c) in enumerate([('0', '#f8fafc'), ('1', '#dbeafe'), ('2', '#93c5fd'), ('3', '#3b82f6'), ('4', '#1d4ed8'), ('5+', '#1e3a8a')]):
        x = 64 + i * 58
        out.append(f'<rect x="{x}" y="{ly - 12}" width="18" height="16" rx="4" fill="{c}" stroke="#e2e8f0"/>')
        out.append(f'<text x="{x + 24}" y="{ly + 1}" font-size="12" fill="#475569">{label}</text>')
    out.append(f'<text x="{width - 24}" y="{ly + 1}" font-size="12" fill="#94a3b8" text-anchor="end">虚线分隔：浙江 ｜ 国考与重点地区 ｜ 其余地区</text>')
    out.append('</svg>')
    return '\n'.join(out)


def year_svg(stats):
    """逐年柱状图：行测、申论并列，柱顶标数值。"""
    years = [str(y) for y in range(min(stats['years']), max(stats['years']) + 1)]
    x = [stats['by_year'].get(y, {}).get('行测', 0) for y in years]
    z = [stats['by_year'].get(y, {}).get('申论', 0) for y in years]
    peak = max(x + z + [1])
    step_v = 20 if peak <= 120 else 25
    ceil = -(-peak // step_v) * step_v
    width, height = 920, 400
    left, right, top, bottom = 56, 24, 88, 52
    plot_h = height - top - bottom
    step = (width - left - right) / len(years)
    bar = step / 2 - 4
    ypos = lambda v: top + plot_h * (1 - v / ceil)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">',
           f'<rect width="{width}" height="{height}" rx="14" fill="#ffffff"/>',
           '<text x="24" y="38" font-size="20" font-weight="700" fill="#0f172a">逐年收录试卷数</text>',
           f'<text x="24" y="62" font-size="13" fill="#64748b">按考试年份统计 · 行测 {sum(x)} 份 · 申论 {sum(z)} 份</text>',
           f'<rect x="{width - 196}" y="27" width="12" height="12" rx="3" fill="#3b82f6"/><text x="{width - 178}" y="38" font-size="13" fill="#334155">行测</text>',
           f'<rect x="{width - 118}" y="27" width="12" height="12" rx="3" fill="#f59e0b"/><text x="{width - 100}" y="38" font-size="13" fill="#334155">申论</text>']
    for v in range(0, ceil + 1, step_v):
        yy = ypos(v)
        out.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width - right}" y2="{yy:.1f}" stroke="{"#cbd5e1" if v == 0 else "#f1f5f9"}"/>')
        out.append(f'<text x="{left - 8}" y="{yy + 4:.1f}" font-size="11" fill="#94a3b8" text-anchor="end">{v}</text>')
    for i, year in enumerate(years):
        bx = left + i * step + 3
        for value, offset, c in ((x[i], 0, '#3b82f6'), (z[i], bar + 2, '#f59e0b')):
            yy = ypos(value)
            out.append(f'<rect x="{bx + offset:.1f}" y="{yy:.1f}" width="{bar:.1f}" height="{top + plot_h - yy:.1f}" rx="3" fill="{c}"/>')
            if value:
                out.append(f'<text x="{bx + offset + bar / 2:.1f}" y="{yy - 5:.1f}" font-size="10" fill="#475569" text-anchor="middle">{value}</text>')
        out.append(f'<text x="{left + i * step + step / 2:.1f}" y="{height - bottom + 20}" font-size="11" fill="#475569" text-anchor="middle">{year}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', help='把逐卷统计数据写到该路径')
    parser.add_argument('--svg', help='把 coverage-heatmap.svg / papers-by-year.svg 写到该目录')
    args = parser.parse_args()
    stats = summarize(load_rows())
    print(f'文件 {stats["files"]} · 槽位 {stats["slots"]} · 地区 {stats["areas"]} · '
          f'年份 {min(stats["years"])}–{max(stats["years"])}')
    print(f'科目 {stats["subject"]} · 题目 {stats["questions"]:,} · 图片引用 {stats["images"]:,} · 多层槽位 {stats["multi"]}')
    for name, tier_stats in stats['tiers'].items():
        print(f'{name} 槽位 {tier_stats["slots"]} · 文件 {tier_stats["files"]} · 题目 {tier_stats["questions"]:,}')
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=1)
        print('已写入', args.json)
    if args.svg:
        os.makedirs(args.svg, exist_ok=True)
        for name, content in (('coverage-heatmap.svg', heatmap_svg(stats)), ('papers-by-year.svg', year_svg(stats))):
            with open(os.path.join(args.svg, name), 'w', encoding='utf-8') as handle:
                handle.write(content + '\n')
            print('已写入', os.path.join(args.svg, name))
    return 0


if __name__ == '__main__':
    sys.exit(main())
