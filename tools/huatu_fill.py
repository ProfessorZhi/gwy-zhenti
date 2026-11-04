#!/usr/bin/env python3
"""用华图同卷数据补入行测试卷中「粉笔暂未收录」的题目与材料（离线，不联网）。

输入是 Dell 上采集的华图试卷缓存目录（格式见 docs/workflow/HUATU-FILL.md）：
    <缓存>/paper.json      试卷身份、题目、材料、图片清单
    <缓存>/images/...      已下载的图片

流程：
    1. 对齐：本库已有题与华图题逐题比对，求整卷偏移（华图题号 − 本库题号）；「卷级锚点」= 按该偏移对上的已有题占比，须 ≥ 0.8。
    2. 定位：每道缺题取前后各 2 道已对齐的已有题推算华图题号（邻题夹逼），至少 3 票一致且前后两侧都有支持才补；
       卷尾缺题（其后已无题）要求前侧 2 题一致，且华图总题量与本库对齐到最后一题。
    3. 写入（--write）：替换题目占位与其所在题组的材料占位；图片复制到 assets-huatu-<paperId>/；
       更新文件头「来源清单」「校验状态」与 catalog/manifest.jsonl。
    4. 校验：题号不变；除被补题目与材料外，其余内容逐字节不变；引用图片均存在。

用法：
    python3 -I tools/huatu_fill.py --paper 省考/北京/2023/行测-统考.md --cache <缓存目录>            # 只出对齐报告
    python3 -I tools/huatu_fill.py --paper 省考/北京/2023/行测-统考.md --cache <缓存目录> --write    # 写入
"""

import argparse
import datetime
import difflib
import hashlib
import html
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB = '粉笔暂未收录本题（来源缺题，题位保留）'
MATERIAL_STUB = '题目正在全力以赴征集，将会在征集到后第一时间上传'
QUESTION = re.compile(r'^### 第 (\d+) 题[^\n]*\n', re.M)
SECTION = re.compile(r'^(#{2,3}) ', re.M)
MIN_ANCHOR = 0.8
MIN_MATCH = 0.85


# ---------- 文本 ----------

def norm(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)|<[^>]+>', '', html.unescape(text))
    return re.sub(r'[\W_]+', '', text)[:160]


def similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def html_to_md(fragment, image_map, prefix):
    """把华图题面 HTML 转成本库 Markdown；图片改为本地相对路径。"""
    s = fragment or ''

    def img(m):
        src = html.unescape(m.group(1))
        if src not in image_map:
            raise ValueError(f'图片未下载：{src}')
        return f'![]({prefix}/{image_map[src]})'

    s = re.sub(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\'][^>]*>', img, s, flags=re.I)

    def table(m):
        rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', m.group(0), flags=re.I | re.S)
        cells = [[re.sub(r'<[^>]+>', '', c).strip().replace('|', '\\|')
                  for c in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', r, flags=re.I | re.S)] for r in rows]
        if not cells:
            return ''
        width = max(len(r) for r in cells)
        cells = [r + [''] * (width - len(r)) for r in cells]
        lines = ['| ' + ' | '.join(cells[0]) + ' |', '| ' + ' | '.join(['---'] * width) + ' |']
        lines += ['| ' + ' | '.join(r) + ' |' for r in cells[1:]]
        return '\n\n' + '\n'.join(lines) + '\n\n'

    s = re.sub(r'<table\b.*?</table>', table, s, flags=re.I | re.S)
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
    s = re.sub(r'</(p|div|li|h\d)>', '\n\n', s, flags=re.I)
    s = re.sub(r'<li\b[^>]*>', '- ', s, flags=re.I)
    s = re.sub(r'</?(strong|b)\b[^>]*>', '**', s, flags=re.I)
    s = re.sub(r'<(?!/?(u|sub|sup)\b)[^>]+>', '', s, flags=re.I)
    s = html.unescape(s).replace(' ', ' ').replace('​', '')
    s = re.sub(r'[ \t]+\n', '\n', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def ranges(nums):
    nums, out = sorted(nums), []
    for i, n in enumerate(nums):
        if i == 0 or nums[i - 1] != n - 1:
            start = n
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f'{start}–{n}')
    return '、'.join(out)


# ---------- 试卷解析 ----------

def split_questions(text):
    """返回 [(题号, 起始偏移, 结束偏移)]；结束于下一个 ##/### 标题之前。"""
    heads = [(int(m.group(1)), m.start()) for m in QUESTION.finditer(text)]
    sections = [m.start() for m in SECTION.finditer(text)]
    out = []
    for num, start in heads:
        end = next((p for p in sections if p > start), len(text))
        out.append((num, start, end))
    return out


def stem_text(block):
    body = block.split('\n', 1)[1].split('<details')[0]
    return norm(body)


def frontmatter(text):
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        raise ValueError('试卷缺少 frontmatter')
    return m


# ---------- 对齐 ----------

def monotone(matched):
    """{本库题号: 华图题序} 中题序单调递增的最大子集（最长递增子序列）。"""
    items = sorted(matched.items())
    best = []                                   # best[i]：以 items[i] 结尾的最长链
    for i, (n, h) in enumerate(items):
        prev = max((best[j] for j in range(i) if items[j][1] < h), key=len, default=[])
        best.append(prev + [i])
    chain = max(best, key=len, default=[])
    return {items[i][0]: items[i][1] for i in chain}


def align(text, hq):
    """hq: 华图题目列表。返回 (报告, {本库题号: 华图题序})。"""
    blocks = split_questions(text)
    present, missing = {}, []
    for num, a, b in blocks:
        block = text[a:b]
        if STUB in block:
            missing.append(num)
        else:
            present[num] = stem_text(block)
    hu = [norm(q.get('stem_html', '') + ''.join(o.get('html', '') for o in q.get('options', []))) for q in hq]
    hu_stem = [norm(q.get('stem_html', '')) for q in hq]
    matched = {}
    for num, st in present.items():
        scores = [max(similar(st, hu_stem[i]), similar(st, hu[i])) for i in range(len(hq))]
        best = max(range(len(hq)), key=scores.__getitem__) if hq else None
        if best is not None and scores[best] >= MIN_MATCH:
            matched[num] = best
    # 回忆卷常有增删题，题序会局部错位：只保留题序单调递增的匹配（最长递增子序列）作锚点，
    # 每道缺题按前后最近锚点的局部偏移推算，不要求整卷同一偏移。
    anchors = monotone(matched)
    anchor = len(anchors) / len(present) if present else 0.0
    offsets = Counter(h - n for n, h in anchors.items())
    offset = offsets.most_common(1)[0][0] if offsets else 0
    taken = set(anchors.values())
    report = {'questions': len(blocks), 'present': len(present), 'missing': missing,
              'huatu_questions': len(hq), 'offset': offset + 1, 'anchor': round(anchor, 3), 'fills': [], 'skipped': []}
    plan = {}
    if anchor < MIN_ANCHOR:
        report['skipped'] = [{'q': q, 'reason': f'卷级锚点 {anchor:.3f} 低于 {MIN_ANCHOR}，不是同一份卷'} for q in missing]
        return report, plan
    keys = sorted(anchors)
    last = max(n for n, _, _ in blocks)
    for q in missing:
        before = [n for n in keys if n < q][-2:]
        after = [n for n in keys if n > q][:2]
        preds = [(n, anchors[n] + (q - n)) for n in before + after]
        tally = Counter(p for _, p in preds)
        h, k = tally.most_common(1)[0] if tally else (None, 0)
        sides = {('前' if n < q else '后') for n, p in preds if p == h}
        # 卷尾缺题：后面已无题可夹逼时，要求前侧 2 题一致，且华图总题量与本库对齐到最后一题。
        local = (h - q) if h is not None else 0
        tail = not after and all(n in missing for n in range(q, last + 1)) and last + local == len(hq) - 1
        reason = None
        if tail and k == 2 and len(before) == 2:
            pass
        elif k < 3 or len(sides) < 2:
            reason = f'邻题夹逼 {k}/{len(preds)}，前后两侧未同时支持'
        elif not 0 <= h < len(hq):
            reason = f'推算的华图题序 {h + 1} 超出范围'
        elif h in taken:
            reason = f'华图第 {h + 1} 题已与本库另一题对上'
        elif not norm(hq[h].get('stem_html', '')) and not hq[h].get('options'):
            reason = f'华图第 {h + 1} 题为空'
        elif not hq[h].get('answer'):
            reason = f'华图第 {h + 1} 题无答案'
        if reason:
            report['skipped'].append({'q': q, 'reason': reason})
        else:
            plan[q] = h
            report['fills'].append({'q': q, 'huatu': h + 1, 'sandwich': f'{k}/{len(preds)}' + ('（卷尾对齐）' if tail and not after else '')})
    return report, plan


# ---------- 写入 ----------

def question_md(q, h, hq, meta, report, image_map, prefix, sandwich):
    item = hq[h]
    lines = [f'### 第 {q} 题', '', html_to_md(item.get('stem_html', ''), image_map, prefix), '']
    for o in item.get('options', []):
        lines += [f"{o['label']}. {html_to_md(o.get('html', ''), image_map, prefix)}", '']
    note = (f"**参考答案（华图在线，{meta['capturedAt'][:10]} 采集；paperId {meta['paperId']}，对齐 hu{h + 1}，"
            f"卷级锚点 {report['anchor']}，邻题夹逼 {sandwich}）**")
    lines += [f'<details><summary>第 {q} 题 · 答案与解析</summary>', '', note, '', item['answer'].strip(), '']
    analysis = html_to_md(item.get('analysis_html', ''), image_map, prefix)
    lines += ['**解析**', '', analysis, ''] if analysis else ['**解析状态：unknown（来源未提供）**', '']
    lines += ['</details>', '', '']
    return '\n'.join(lines)


def update_frontmatter(text, meta, filled):
    m = frontmatter(text)
    fm = m.group(1)
    nums = ', '.join(str(q) for q in filled)
    entry = ('  - 来源方: "华图在线"\n'
             f'    来源试卷ID: "{meta["paperId"]}"\n'
             f'    题号: [{nums}]\n'
             '    用途: "补题干、选项、参考答案及解析"\n'
             '    证据: "本卷对应题号的华图参考答案块（含 paperId、卷级锚点、邻题夹逼）"\n'
             '    核验: "逐题对齐记录在答案块；整卷未完成人工验收"\n')
    if '\n来源清单:' not in '\n' + fm:
        src = re.search(r'^来源: (.*)$', fm, re.M)
        base = ('来源清单:\n  - 来源方: "粉笔"\n'
                f'    定位: {src.group(1) if src else "未记录"}\n'
                '    用途: "题面基础及原始参考内容；明确由华图补充的题目除外"\n'
                '    核验: "沿用原有来源记录；未因本次修改重新验证整卷"\n')
        fm = re.sub(r'^(来源: .*\n)', lambda x: x.group(1) + base + entry, fm + '\n', count=1, flags=re.M).rstrip('\n')
    else:
        # 插到来源清单最后一项之后（来源清单的条目均以两个空格缩进）
        fm = re.sub(r'(^来源清单:\n(?:  .*\n)+)', lambda x: x.group(1) + entry, fm + '\n', count=1, flags=re.M).rstrip('\n')
    stamp = f'；{meta["capturedAt"][:10]} 由华图同卷补入 {len(filled)} 题（题 {ranges(filled)}）题干/选项/答案/解析，附 paperId 与对齐证据'
    fm = re.sub(r'^(校验状态: ".*?)"$', lambda x: x.group(1) + stamp + '"', fm, count=1, flags=re.M)
    return '---\n' + fm + '\n---\n' + text[m.end():]


def fill(paper, cache, write=False, root=ROOT):
    path = root / paper
    text = path.read_text(encoding='utf-8')
    meta = json.loads((cache / 'paper.json').read_text(encoding='utf-8'))
    hq = meta['questions']
    report, plan = align(text, hq)
    report.update({'paper': paper, 'paperId': meta['paperId']})
    if not write or not plan:
        report['written'] = False
        return report
    prefix = f'assets-huatu-{meta["paperId"]}'
    image_map, copies = {}, []
    for img in meta.get('images', []):
        data = (cache / img['file']).read_bytes()
        name = hashlib.sha256(data).hexdigest() + Path(img['file']).suffix.lower()
        image_map[img['url']] = name
        copies.append((data, path.parent / prefix / name))
    materials = {m['id']: m for m in meta.get('materials', [])}
    fills = {f['q']: f for f in report['fills']}
    # 从后往前替换，偏移量不受影响
    edits = []
    blocks = split_questions(text)
    for num, a, b in blocks:
        if num in plan:
            edits.append((a, b, question_md(num, plan[num], hq, meta, report, image_map, prefix, fills[num]['sandwich'])))
    # 材料占位：取其后第一道被补题目所属的华图材料
    for m in re.finditer(r'^(## 材料 \d+)\n\n' + re.escape(MATERIAL_STUB) + r'\n\n', text, re.M):
        nxt = next(((n, a) for n, a, _ in blocks if a > m.start()), None)
        if nxt and nxt[0] in plan:
            mid = hq[plan[nxt[0]]].get('material_id')
            if mid in materials:
                body = html_to_md(materials[mid].get('html', ''), image_map, prefix)
                edits.append((m.start(), m.end(), f'{m.group(1)}\n\n{body}\n\n'))
                report.setdefault('materials', []).append(m.group(1).removeprefix('## '))
    new = text
    for a, b, rep in sorted(edits, reverse=True):
        new = new[:a] + rep + new[b:]
    body = new[frontmatter(new).end():]
    new = update_frontmatter(new, meta, sorted(plan))
    if new[frontmatter(new).end():] != body:
        raise RuntimeError('更新文件头时改动了正文')
    verify(text, new, plan)
    for data, dest in copies:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    path.write_text(new, encoding='utf-8')
    for ref in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', new):
        if not (path.parent / ref).exists():
            raise RuntimeError(f'图片缺失：{ref}')
    update_manifest(paper, new, root)
    report['written'] = True
    return report


def verify(old, new, plan):
    before, after = split_questions(old), split_questions(new)
    if [n for n, _, _ in before] != [n for n, _, _ in after]:
        raise RuntimeError('题号发生变化')
    for (n, a, b), (_, c, d) in zip(before, after):
        if n not in plan and old[a:b] != new[c:d] and MATERIAL_STUB not in old[a:b]:
            raise RuntimeError(f'第 {n} 题被意外修改')
        if n in plan and STUB in new[c:d]:
            raise RuntimeError(f'第 {n} 题仍是占位')


def update_manifest(paper, text, root=ROOT):
    manifest = root / 'catalog/manifest.jsonl'
    rows = [json.loads(l) for l in manifest.read_text(encoding='utf-8').splitlines() if l.strip()]
    data = text.encode('utf-8')
    for r in rows:
        if r['path'] == paper:
            r['sha256'] = hashlib.sha256(data).hexdigest()
            r['bytes'] = len(data)
            r['image_references'] = len(re.findall(r'!\[[^\]]*\]\(|<img\b', text))
    manifest.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--paper', required=True, help='试卷路径，相对仓库根目录')
    parser.add_argument('--cache', required=True, type=Path, help='华图试卷缓存目录（含 paper.json）')
    parser.add_argument('--write', action='store_true', help='写入试卷；不加只输出对齐报告')
    args = parser.parse_args()
    report = fill(args.paper, args.cache.resolve(), args.write)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
