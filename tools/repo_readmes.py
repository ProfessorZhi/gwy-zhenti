#!/usr/bin/env python3
"""从 catalog/manifest.jsonl 生成仓库的导航页与首页横幅。

写出：
    docs/assets/banner.svg          首页横幅（规模数字随清单更新）
    国考/README.md                  国考逐年卷表
    省考/README.md                  省考地区总览
    省考/<地区>/README.md            该地区逐年卷表
    README.md 中 <!-- gwy:regions --> 区块   首页地区入口

用法：
    python3 -I tools/repo_readmes.py            # 写文件
    python3 -I tools/repo_readmes.py --check    # 只检查是否最新，不写

输出不含时间戳，同一清单重复运行结果完全一致。缺题数取试卷里"粉笔暂未收录本题"占位的个数。
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'catalog' / 'manifest.jsonl'
PLACEHOLDER = '粉笔暂未收录本题'
SUBJECTS = ('行测', '申论')
# 首页与省考总览的地区分组（不在表里的地区归入"其他"）。
GROUPS = [
    ('华东', ['浙江', '江苏', '上海', '安徽', '福建', '江西', '山东']),
    ('华北', ['北京', '天津', '河北', '山西', '内蒙古']),
    ('华中 · 华南', ['河南', '湖北', '湖南', '广东', '广州', '深圳', '广西', '海南']),
    ('西南', ['重庆', '四川', '贵州', '云南', '西藏']),
    ('西北', ['陕西', '甘肃', '青海', '宁夏', '新疆', '新疆兵团']),
    ('东北', ['辽宁', '吉林', '黑龙江']),
]
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',sans-serif"


def link(path):
    # 中文路径原样保留（GitHub 能直接解析，源码也好读），只转义会打断 Markdown 链接的字符。
    return path.replace('%', '%25').replace(' ', '%20').replace('(', '%28').replace(')', '%29')


def load():
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding='utf-8').splitlines() if line.strip()]
    for r in rows:
        text = (ROOT / r['path']).read_text(encoding='utf-8')
        r['_missing'] = text.count(PLACEHOLDER)
        r['_questions'] = int(r.get('declared_questions') or 0)
        r['_label'] = Path(r['path']).stem.split('-', 1)[1] if '-' in Path(r['path']).stem else Path(r['path']).stem
    return rows


def stats(rows):
    years = sorted({int(r['year']) for r in rows})
    return {
        'papers': len(rows),
        'xingce': sum(r['subject'] == '行测' for r in rows),
        'shenlun': sum(r['subject'] == '申论' for r in rows),
        'questions': sum(r['_questions'] for r in rows),
        'areas': len({r['area'] for r in rows}),
        'years': (years[0], years[-1]),
    }


def banner_svg(s):
    tiles = [(f"{s['papers']:,}", '份试卷'), (f"{s['questions']:,}", '道题位'),
             (str(s['areas']), '个地区'), (f"{s['years'][0]}–{s['years'][1]}", '年份跨度')]
    w, h = 1200, 300
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{FONT}">',
           '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
           '<stop offset="0" stop-color="#0f2a4a"/><stop offset="1" stop-color="#1e4f8a"/></linearGradient>'
           '<pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">'
           '<path d="M28 0H0V28" fill="none" stroke="#ffffff" stroke-opacity="0.05"/></pattern></defs>',
           f'<rect width="{w}" height="{h}" rx="18" fill="url(#bg)"/>',
           f'<rect width="{w}" height="{h}" rx="18" fill="url(#grid)"/>',
           # 右侧装饰：叠放的试卷
           '<g transform="translate(965 46) rotate(6)"><rect width="170" height="210" rx="10" fill="#ffffff" fill-opacity="0.10"/></g>',
           '<g transform="translate(950 40)"><rect width="170" height="210" rx="10" fill="#ffffff" fill-opacity="0.92"/>'
           '<rect x="20" y="24" width="96" height="10" rx="5" fill="#1e4f8a"/>'
           '<rect x="20" y="48" width="130" height="6" rx="3" fill="#cbd5e1"/><rect x="20" y="62" width="112" height="6" rx="3" fill="#cbd5e1"/>'
           '<rect x="20" y="86" width="60" height="6" rx="3" fill="#94a3b8"/>'
           '<rect x="20" y="104" width="130" height="6" rx="3" fill="#cbd5e1"/><rect x="20" y="118" width="98" height="6" rx="3" fill="#cbd5e1"/>'
           '<rect x="20" y="146" width="130" height="34" rx="6" fill="#fef3c7"/>'
           '<text x="32" y="168" font-size="13" fill="#92400e">▸ 答案与解析</text></g>',
           '<text x="56" y="96" font-size="46" font-weight="800" fill="#ffffff">全国公务员考试真题库</text>',
           '<text x="58" y="136" font-size="20" fill="#bfdbfe">国考 · 省考 ｜ 行测 · 申论 ｜ Markdown 整卷 · 题图 · 答案解析随题折叠</text>']
    for i, (num, label) in enumerate(tiles):
        x = 56 + i * 212
        out += [f'<rect x="{x}" y="176" width="196" height="84" rx="12" fill="#ffffff" fill-opacity="0.09" stroke="#ffffff" stroke-opacity="0.18"/>',
                f'<text x="{x + 18}" y="220" font-size="{30 if len(num) <= 7 else 26}" font-weight="700" fill="#ffffff">{num}</text>',
                f'<text x="{x + 18}" y="246" font-size="14" fill="#bfdbfe">{label}</text>']
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def cell(papers, base):
    """一个年份×科目格：卷型链接，有缺题的标出来。"""
    items = []
    for r in sorted(papers, key=lambda r: r['_label']):
        rel = os.path.relpath(r['path'], base.relative_to(ROOT)).replace(os.sep, '/')
        mark = f" <sup>缺{r['_missing']}</sup>" if r['_missing'] else ''
        items.append(f"[{r['_label']}]({link(rel)}){mark}")
    return ' · '.join(items) if items else '—'


def year_table(rows, base):
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[int(r['year'])][r['subject']].append(r)
    lines = ['| 年份 | 行测 | 申论 |', '| :---: | --- | --- |']
    for year in sorted(by, reverse=True):
        lines.append(f"| **{year}** | {cell(by[year]['行测'], base)} | {cell(by[year]['申论'], base)} |")
    return lines


def area_page(area, rows, base, title, back):
    s = stats(rows)
    missing = sum(r['_missing'] for r in rows)
    note = f'，其中 {missing} 个题位粉笔暂未收录（表中以 <sup>缺N</sup> 标出）' if missing else ''
    lines = [f'# {title}', '',
             f"> {s['papers']} 份试卷（行测 {s['xingce']} · 申论 {s['shenlun']}）· {s['years'][0]}–{s['years'][1]} · {s['questions']:,} 个题位{note}。",
             '', f'{back}', '', '<!-- 由 tools/repo_readmes.py 生成，勿手改 -->', '']
    lines += year_table(rows, base)
    lines += ['', '每份试卷：题目在前，**答案与解析**折叠在每题下方，点开即看。图片与试卷同目录存放。', '']
    return '\n'.join(lines)


def grouped(by_area, href):
    """地区分组表：每组一行，地区名带链接和份数。"""
    seen = set()
    lines = ['| 区域 | 地区（试卷份数） |', '| --- | --- |']
    for name, areas in GROUPS + [('其他', sorted(a for a in by_area if a not in {x for _, g in GROUPS for x in g} and a != '国考'))]:
        present = [a for a in areas if a in by_area]
        if not present:
            continue
        seen.update(present)
        lines.append(f'| **{name}** | ' + ' · '.join(f'[{a}]({href(a)}) {len(by_area[a])}' for a in present) + ' |')
    return lines


def province_index(by_area):
    lines = ['# 省考', '', '> 按地区浏览；点进地区即可看到逐年、逐卷型的试卷表。', '',
             '[← 返回首页](../README.md) · [国考](../国考/README.md) · [全部试卷索引](../catalog/INDEX.md)', '',
             '<!-- 由 tools/repo_readmes.py 生成，勿手改 -->', '']
    lines += grouped({a: v for a, v in by_area.items() if a != '国考'}, lambda a: link(a) + '/')
    lines += ['', '| 地区 | 份数 | 行测 | 申论 | 年份 | 缺题位 |', '| --- | ---: | ---: | ---: | :---: | ---: |']
    for area in sorted((a for a in by_area if a != '国考'), key=lambda a: (-len(by_area[a]), a)):
        s = stats(by_area[area])
        miss = sum(r['_missing'] for r in by_area[area])
        lines.append(f"| [{area}]({link(area)}/) | {s['papers']} | {s['xingce']} | {s['shenlun']} | {s['years'][0]}–{s['years'][1]} | {miss or '—'} |")
    return '\n'.join(lines) + '\n'


def regions_block(by_area):
    lines = ['<!-- gwy:regions:start -->',
             f"**[国考](国考/README.md)** {len(by_area.get('国考', []))} 份 ｜ **[省考总览](省考/README.md)** ｜ [全部试卷索引](catalog/INDEX.md)", '']
    lines += grouped({a: v for a, v in by_area.items() if a != '国考'}, lambda a: '省考/' + link(a) + '/')
    lines.append('<!-- gwy:regions:end -->')
    return '\n'.join(lines)


def outputs(rows):
    by_area = defaultdict(list)
    for r in rows:
        by_area[r['area']].append(r)
    files = {ROOT / 'docs/assets/banner.svg': banner_svg(stats(rows))}
    files[ROOT / '国考/README.md'] = area_page('国考', by_area['国考'], ROOT / '国考', '国考',
                                              '[← 返回首页](../README.md) · [省考](../省考/README.md) · [全部试卷索引](../catalog/INDEX.md)')
    files[ROOT / '省考/README.md'] = province_index(by_area)
    for area, items in by_area.items():
        if area == '国考':
            continue
        base = ROOT / '省考' / area
        if not base.is_dir():
            continue
        files[base / 'README.md'] = area_page(area, items, base, f'{area} · 省考',
                                              '[← 省考总览](../README.md) · [返回首页](../../README.md)')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    block = regions_block(by_area)
    pattern = re.compile(r'<!-- gwy:regions:start -->.*?<!-- gwy:regions:end -->', re.S)
    if pattern.search(readme):
        files[ROOT / 'README.md'] = pattern.sub(lambda _: block, readme)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for path, content in outputs(load()).items():
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current != content:
            stale.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.write_text(content, encoding='utf-8')
    if args.check:
        print('最新' if not stale else '需要重新生成：' + '、'.join(stale))
        return 1 if stale else 0
    print(f'写入 {len(stale)} 个文件')
    return 0


if __name__ == '__main__':
    sys.exit(main())
