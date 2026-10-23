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
            anchors = rec.get('question_anchors')
            rows.append({
                'area': area,
                'year': rec['year'],
                'subject': rec['subject'],
                'pt': rec.get('paper_type') or '',
                'pt2': norm_pt(rec.get('paper_type')),
                'path': rec['path'],
                'q': anchors if isinstance(anchors, int) else len(anchors or []),
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
    areas = sorted(stats['by_area'], key=lambda a: ({'L1': 0, 'L2': 1}.get(stats['by_area'][a]['tier'], 2), a))
    years = [str(y) for y in range(min(stats['years']), max(stats['years']) + 1)]
    cw, ch, lw, th = 34, 24, 92, 64
    width = lw + len(years) * cw + 60
    height = th + len(areas) * ch + 90
    palette = ['#f1f5f9', '#dbeafe', '#93c5fd', '#3b82f6', '#1d4ed8', '#1e3a8a']
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="{FONT}">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<text x="20" y="30" font-size="18" font-weight="700" fill="#0f172a">库内试卷分布（地区 × 年份，单元格数字＝MD 份数）</text>',
           f'<text x="20" y="50" font-size="12" fill="#64748b">共 {stats["files"]} 份 · {stats["areas"]} 个地区 · '
           f'{min(stats["years"])}–{max(stats["years"])} · 数据取自 catalog/manifest.jsonl</text>']
    x0, y0 = lw, th
    for i, year in enumerate(years):
        out.append(f'<text x="{x0 + i * cw + cw / 2}" y="{y0 - 8}" font-size="11" fill="#475569" text-anchor="middle">{year}</text>')
    for r, area in enumerate(areas):
        yy = y0 + r * ch
        if r and stats['by_area'][area]['tier'] != stats['by_area'][areas[r - 1]]['tier']:
            out.append(f'<line x1="20" y1="{yy}" x2="{width - 30}" y2="{yy}" stroke="#cbd5e1" stroke-dasharray="3 3"/>')
        out.append(f'<text x="20" y="{yy + ch - 8}" font-size="11" fill="#334155">{area}</text>')
        for i, year in enumerate(years):
            n = stats['grid'].get(f'{area}|{year}', 0)
            out.append(f'<rect x="{x0 + i * cw + 2}" y="{yy + 2}" width="{cw - 4}" height="{ch - 4}" rx="4" '
                       f'fill="{palette[min(n, 5)] if n else "#f8fafc"}"/>')
            if n:
                out.append(f'<text x="{x0 + i * cw + cw / 2}" y="{yy + ch - 9}" font-size="10" '
                           f'fill="{"#ffffff" if n >= 3 else "#1e3a8a"}" text-anchor="middle">{n}</text>')
    ly = y0 + len(areas) * ch + 30
    out.append(f'<text x="20" y="{ly}" font-size="11" fill="#475569">份数</text>')
    for i, (label, color) in enumerate([('0', '#f1f5f9'), ('1', '#dbeafe'), ('2', '#93c5fd'), ('3–4', '#3b82f6'), ('5+', '#1e3a8a')]):
        xx = 60 + i * 62
        out.append(f'<rect x="{xx}" y="{ly - 11}" width="16" height="14" rx="3" fill="{color}" stroke="#e2e8f0"/>')
        out.append(f'<text x="{xx + 21}" y="{ly}" font-size="11" fill="#475569">{label}</text>')
    out.append(f'<text x="20" y="{ly + 28}" font-size="11" fill="#94a3b8">虚线以上：L1 浙江 / L2 国考与重点地区 / 其余为 L3</text>')
    out.append('</svg>')
    return '\n'.join(out)


def year_svg(stats):
    years = [str(y) for y in range(min(stats['years']), max(stats['years']) + 1)]
    x = [stats['by_year'].get(y, {}).get('行测', 0) for y in years]
    z = [stats['by_year'].get(y, {}).get('申论', 0) for y in years]
    peak = max(x + z + [1])
    width, height, left, bottom = 760, 360, 48, 70
    step = (width - left - 20) / len(years)
    top = height - bottom - 40
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="{FONT}">',
           '<rect width="100%" height="100%" fill="#fff"/>',
           f'<text x="16" y="26" font-size="16" font-weight="700" fill="#0f172a">逐年入库存量（份）</text>']
    for i, year in enumerate(years):
        bx = left + i * step
        for value, offset, color in ((x[i], 2, '#3b82f6'), (z[i], step / 2 + 1, '#f59e0b')):
            h = top * value / peak
            out.append(f'<rect x="{bx + offset}" y="{height - bottom - h}" width="{step / 2 - 3}" height="{h:.1f}" rx="2" fill="{color}"/>')
        out.append(f'<text x="{bx + step / 2}" y="{height - bottom + 16}" font-size="10" fill="#64748b" text-anchor="middle">{year}</text>')
    out.append(f'<line x1="{left}" y1="{height - bottom}" x2="{width - 12}" y2="{height - bottom}" stroke="#e2e8f0"/>')
    out.append(f'<rect x="{left}" y="{height - 28}" width="12" height="12" rx="2" fill="#3b82f6"/>'
               f'<text x="{left + 17}" y="{height - 18}" font-size="12" fill="#475569">行测 {sum(x)}</text>')
    out.append(f'<rect x="{left + 110}" y="{height - 28}" width="12" height="12" rx="2" fill="#f59e0b"/>'
               f'<text x="{left + 127}" y="{height - 18}" font-size="12" fill="#475569">申论 {sum(z)}</text>')
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
