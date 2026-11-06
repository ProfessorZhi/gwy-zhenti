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
import runpy
import shutil
import sys
from urllib.parse import urlsplit, urlunsplit
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB = '粉笔暂未收录本题（来源缺题，题位保留）'
MATERIAL_STUB = '题目正在全力以赴征集，将会在征集到后第一时间上传'
QUESTION = re.compile(r'^#{2,3} 第 (\d+) 题[^\n]*\n', re.M)
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
    # Even a match excluded from the monotone chain denotes existing content;
    # using it as a fill would duplicate another question in a reordered paper.
    taken = set(matched.values())
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
        if not (tail and k == 2 and len(before) == 2) and (k < 3 or len(sides) < 2):
            reason = f'邻题夹逼 {k}/{len(preds)}，前后两侧未同时支持'
        if reason is None and not 0 <= h < len(hq):
            reason = f'推算的华图题序 {h + 1} 超出范围'
        elif reason is None and h in taken:
            reason = f'华图第 {h + 1} 题已与本库另一题对上'
        elif reason is None and not norm(hq[h].get('stem_html', '')) and not hq[h].get('options'):
            reason = f'华图第 {h + 1} 题为空'
        elif reason is None and not hq[h].get('answer'):
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
    if report.get('mode') == 'reviewed-A1':
        note = (f"**参考答案（华图在线，{meta['capturedAt'][:10]} 采集；paperId {meta['paperId']}，对齐 hu{h + 1}，"
                f"卷级锚点 {report['anchor']}；显式人工复核）**\n\n"
                f"[逐题复核依据与来源哈希]({prefix}/review-{report['review_plan_sha256']}.json)")
    lines += [f'<details><summary>第 {q} 题 · 答案与解析</summary>', '', note, '', item['answer'].strip(), '']
    analysis = html_to_md(item.get('analysis_html', ''), image_map, prefix)
    lines += ['**解析**', '', analysis, ''] if analysis else ['**解析状态：unknown（来源未提供）**', '']
    lines += ['</details>', '', '']
    return '\n'.join(lines)


def update_frontmatter(text, meta, filled, mode='A1'):
    m = frontmatter(text)
    fm = m.group(1)
    nums = ', '.join(str(q) for q in filled)
    u = urlsplit(meta.get('url', ''))
    if u.scheme != 'https' or not u.hostname or not (u.hostname == 'huatu.com' or u.hostname.endswith('.huatu.com')) or u.username or u.password:
        raise ValueError('华图来源链接缺失或不合法')
    locator = urlunsplit((u.scheme, u.netloc, u.path, '', ''))
    purpose = '补选项、参考答案及解析' if mode in ('A2', 'reviewed-A2') else '补题干、选项、参考答案及解析'
    evidence = '含 paperId、卷级锚点、显式人工复核计划链接' if mode.startswith('reviewed-') else '含 paperId、卷级锚点、邻题夹逼'
    entry = ('  - 来源方: "华图在线"\n'
             f'    来源试卷ID: "{meta["paperId"]}"\n'
             f'    定位: {json.dumps(locator, ensure_ascii=False)}\n'
             f'    题号: [{nums}]\n'
             f'    用途: "{purpose}"\n'
             f'    证据: "本卷对应题号的华图参考答案块（{evidence}）"\n'
             '    核验: "逐题对齐记录在答案块；整卷未完成人工验收"\n')
    if '\n来源清单:' not in '\n' + fm:
        src = re.search(r'^来源: (.*)$', fm, re.M)
        if not src:
            raise ValueError('未记录原有来源')
        raw = src.group(1).strip()
        try:
            original = json.loads(raw)
        except json.JSONDecodeError:
            if raw.startswith(('[', '{', '"', "'")):
                raise ValueError('不支持的原有来源格式')
            original = raw
        origins = original if isinstance(original, list) else [original]
        if not origins or not all(isinstance(v, str) and v.strip() for v in origins):
            raise ValueError('原有来源无效')
        base = '来源清单:\n'
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                host = parsed.hostname or ''
                name = '粉笔' if host == 'fenbi.com' or host.endswith('.fenbi.com') else '原有来源'
                base += ('  - 来源方: ' + json.dumps(name, ensure_ascii=False) + '\n'
                         '    定位: ' + json.dumps(origin, ensure_ascii=False) + '\n')
            else:
                base += ('  - 来源方: ' + json.dumps(origin, ensure_ascii=False) + '\n'
                         '    证据: "原有来源字段所列标识"\n')
            base += ('    用途: "原有题面和参考内容"\n'
                     '    核验: "沿用原有来源记录，未重新验证整卷"\n')
        fm = re.sub(r'^(来源: .*\n)', lambda x: x.group(1) + base + entry, fm + '\n', count=1, flags=re.M).rstrip('\n')
    else:
        # 插到来源清单最后一项之后（来源清单的条目均以两个空格缩进）
        fm = re.sub(r'(^来源清单:\n(?:  .*\n)+)', lambda x: x.group(1) + entry, fm + '\n', count=1, flags=re.M).rstrip('\n')
    details = '选项/答案/解析' if mode in ('A2', 'reviewed-A2') else '题干/选项/答案/解析'
    stamp = f'；{meta["capturedAt"][:10]} 由华图同卷补入 {len(filled)} 题（题 {ranges(filled)}）{details}，附 paperId 与对齐证据'
    fm = re.sub(r'^(校验状态: ".*?)"$', lambda x: x.group(1) + stamp + '"', fm, count=1, flags=re.M)
    return '---\n' + fm + '\n---\n' + text[m.end():]


OPTION_LINE = re.compile(r'^\s*(?:-\s*)?(?:\*\*)?([A-D])(?:\*\*)?\s*[.．、]\s*(.*)$', re.M)


def equivalent_law_stem(old, source, old_options, source_options):
    """Allow a narrow law-title reformulation only with two exact common options."""
    def signature(text):
        text = html.unescape(re.sub(r'<[^>]*>', '', text))
        laws = re.findall(r'《([^》]+)》', text)
        if len(laws) != 1 or not laws[0].endswith('法'):
            return None
        law = re.sub(r'^中华人民共和国', '', laws[0])
        if re.search(r'错误|不正确|不恰当', text):
            polarity = 'negative'
        elif re.search(r'正确|恰当', text):
            polarity = 'positive'
        else:
            return None
        return law, polarity
    a, b = signature(old), signature(source)
    if not a or a != b:
        return False
    old_set = {norm(m.group(2)) for m in old_options if not re.search(r'缺失|暂缺|征集', m.group(2))}
    source_set = {norm(o.get('html', '')) for o in source_options}
    return len({s for s in old_set & source_set if len(s) >= 4}) >= 2


def fill_option_gap(paper, cache, text, meta, target, write, root, reviewed_plan=None, expect_after=None):
    """Explicit A2 repair: whole source option sequence, never mixed versions."""
    if not str(meta.get('paperId', '')).isdigit():
        raise ValueError('华图试卷编号无效')
    path = root / paper
    blocks = split_questions(text)
    target_blocks = [(a, b) for n, a, b in blocks if n == target]
    if len(target_blocks) != 1:
        raise ValueError('选项缺口题号不存在或不唯一')
    a, b = target_blocks[0]
    original = text[a:b]
    body = original.split('<details', 1)[0]
    options = list(OPTION_LINE.finditer(body))
    if not options or not any(re.match(r'^\s*(?:缺失|暂缺)(?:\s*$|题目正在)', m.group(2)) for m in options):
        raise ValueError('指定题未发现选项占位，拒绝更改')
    # Mark only this explicitly selected question missing; existing monotone
    # alignment supplies the same bidirectional neighbor safeguards as A1.
    heading = original.splitlines(keepends=True)[0]
    trial = text[:a] + heading + '\n' + STUB + '\n\n' + text[b:]
    report, plan = align(trial, meta['questions'])
    report.update({'paper': paper, 'paperId': meta['paperId'], 'mode': 'A2', 'written': False})
    review_tools, review_raw = None, None
    if reviewed_plan:
        review_tools = runpy.run_path(str(Path(__file__).with_name('huatu_reviewed_plan.py')))
        plan, review_raw = review_tools['validate'](Path(reviewed_plan), paper, path, cache, trial, meta, report, sys.modules[__name__], option_q=target)
    # Other missing questions are irrelevant in explicit A2 mode.
    report['fills'] = [x for x in report['fills'] if x['q'] == target]
    report['skipped'] = [x for x in report['skipped'] if x['q'] == target]
    if target not in plan:
        return report
    q = meta['questions'][plan[target]]
    stem = body.split('\n', 1)[1][:options[0].start() - len(heading)]
    if (similar(norm(stem), norm(q.get('stem_html', ''))) < MIN_MATCH
            and not equivalent_law_stem(stem, q.get('stem_html', ''), options, q.get('options', []))):
        report['fills'] = []
        report['skipped'] = [{'q': target, 'reason': '目标题干与华图题干不匹配'}]
        return report
    source_opts = q.get('options', [])
    if [o.get('label') for o in source_opts] != list('ABCD') or any(
            not norm(o.get('html', '')) and '<img' not in o.get('html', '').lower()
            or re.search(r'缺失|暂缺|征集|占位', re.sub(r'<[^>]*>', '', o.get('html', '')))
            for o in source_opts) or q.get('answer', '').strip() not in 'ABCD' or len(q.get('answer', '').strip()) != 1:
        report['fills'] = []
        report['skipped'] = [{'q': target, 'reason': '华图选项顺序不完整或答案缺失'}]
        return report
    # Text-only "as shown" options require an explicitly identified shared figure.
    figure = q.get('option_figure_html', '')
    if any(re.search(r'如(?:上|下|左|右)?图', re.sub(r'<[^>]*>', '', o['html'])) for o in source_opts) and '<img' not in figure.lower():
        report['fills'] = []
        report['skipped'] = [{'q': target, 'reason': '图形选项缺共享图'}]
        return report
    prefix = f'assets-huatu-{meta["paperId"]}'
    image_map, copies = {}, []
    fragments = [figure, q.get('analysis_html', '')] + [o['html'] for o in source_opts]
    needed = {html.unescape(src) for fragment in fragments for src in re.findall(
        r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\'][^>]*>', fragment or '', flags=re.I)}
    for img in meta.get('images', []):
        if img['url'] not in needed:
            continue
        if img['url'] in image_map:
            raise ValueError('图片地址存在重复映射')
        source = (cache / img['file']).resolve()
        if not source.is_relative_to(cache.resolve()):
            raise ValueError('图片路径超出缓存')
        if not source.is_file():
            raise ValueError('图片文件缺失：' + img['file'])
        data = source.read_bytes()
        if reviewed_plan and img.get('sha256') != hashlib.sha256(data).hexdigest():
            raise ValueError('人工复核来源图片哈希不匹配')
        name = hashlib.sha256(data).hexdigest() + Path(img['file']).suffix.lower()
        image_map[img['url']] = name
        copies.append((data, path.parent / prefix / name))
    # All referenced images must exist in the archive before any file is written.
    for fragment in fragments:
        rendered = html_to_md(fragment, image_map, prefix)
        if reviewed_plan and fragment and not norm(rendered) and '![](' not in rendered:
            raise ValueError('人工复核 A2 选项或解析渲染后为空')
    original_name = hashlib.sha256(original.encode('utf-8')).hexdigest() + '-original.txt'
    output = [heading.rstrip(), '', stem.strip(), '',
              f'> 本题采用华图整组选项与参考答案；原题块保存在 [{original_name}]({prefix}/{original_name})。', '']
    if figure:
        output += [html_to_md(figure, image_map, prefix), '']
    for o in source_opts:
        output += [f"{o['label']}. {html_to_md(o['html'], image_map, prefix)}", '']
    sandwich = next(f['sandwich'] for f in report['fills'] if f['q'] == target)
    review_note = ''
    alignment_note = f'邻题夹逼 {sandwich}'
    if reviewed_plan:
        review_note = f"\n\n[逐题复核依据与来源哈希]({prefix}/review-{report['review_plan_sha256']}.json)"
        alignment_note = '显式人工复核'
    output += [f'<details><summary>第 {target} 题 · 答案与解析</summary>', '',
               f'**参考答案（华图在线，paperId {meta["paperId"]}；卷级锚点 {report["anchor"]}，{alignment_note}；题序与原版本可能不同）**' + review_note, '',
               q['answer'].strip(), '', '**解析**', '',
               html_to_md(q.get('analysis_html', ''), image_map, prefix) or '来源未提供解析。', '', '</details>', '', '']
    new = text[:a] + '\n'.join(output) + text[b:]
    body_after = new[frontmatter(new).end():]
    new = update_frontmatter(new, meta, [target], mode='reviewed-A2' if reviewed_plan else 'A2')
    if new[frontmatter(new).end():] != body_after:
        raise RuntimeError('更新文件头时改动正文')
    verify(text, new, {target: plan[target]})
    planned = {dest.resolve() for _, dest in copies}
    for ref in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', new):
        resolved = (path.parent / ref).resolve()
        if resolved not in planned and not resolved.is_file():
            raise ValueError(f'引用图片缺失：{ref}')
    manifest = (root / 'catalog/manifest.jsonl').resolve()
    if not manifest.is_relative_to(root.resolve()):
        raise ValueError('清单路径超出仓库')
    try:
        rows = [json.loads(line) for line in manifest.read_text(encoding='utf8').splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise ValueError('清单不存在或无效') from exc
    if sum(isinstance(row, dict) and row.get('path') == paper for row in rows) != 1:
        raise ValueError('试卷在清单中不存在或不唯一')
    if reviewed_plan:
        report['after_sha256'] = hashlib.sha256(new.encode('utf8')).hexdigest()
        if not write:
            return report
        if expect_after != report['after_sha256']:
            raise ValueError('人工复核写入必须提供与预检一致的 --expect-after')
        copies.extend([(original.encode('utf8'), path.parent / prefix / original_name),
                       (review_raw, path.parent / prefix / f"review-{report['review_plan_sha256']}.json")])
        review_tools['commit'](path, paper, new, root, copies, json.loads(review_raw)['paper_sha256'])
        report['written'] = True
        return report
    if not write:
        return report
    for data, dest in copies:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    original_path = path.parent / prefix / original_name
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(original.encode('utf8'))
    path.write_bytes(new.encode('utf8'))
    update_manifest(paper, new, root)
    report['written'] = True
    return report


def fill(paper, cache, write=False, root=ROOT, option_q=None, reviewed_plan=None, expect_after=None):
    root = root.resolve()
    path = (root / paper).resolve()
    if not any(path.is_relative_to(root / section) for section in ('省考', '国考')) or path.suffix.lower() != '.md':
        raise ValueError('试卷路径必须在省考或国考目录内')
    paper = path.relative_to(root).as_posix()
    text = path.read_text(encoding='utf-8')
    meta = json.loads((cache / 'paper.json').read_text(encoding='utf-8'))
    if option_q is not None:
        return fill_option_gap(paper, cache, text, meta, option_q, write, root, reviewed_plan, expect_after)
    hq = meta['questions']
    report, plan = align(text, hq)
    report.update({'paper': paper, 'paperId': meta['paperId']})
    review_tools, review_raw = None, None
    if reviewed_plan:
        review_tools = runpy.run_path(str(Path(__file__).with_name('huatu_reviewed_plan.py')))
        plan, review_raw = review_tools['validate'](Path(reviewed_plan), paper, path, cache, text, meta, report, sys.modules[__name__])
    if (not write and not reviewed_plan) or not plan:
        report['written'] = False
        return report
    prefix = f'assets-huatu-{meta["paperId"]}'
    image_map, copies = {}, []
    needed = set()
    if reviewed_plan:
        fragments = []
        for h in plan.values():
            source = hq[h]
            fragments.extend([source.get('stem_html', ''), source.get('analysis_html', '')])
            fragments.extend(o.get('html', '') for o in source.get('options', []))
        if MATERIAL_STUB in text:
            material_ids = {hq[h].get('material_id') for h in plan.values()}
            fragments.extend(m['html'] for m in meta.get('materials', []) if m['id'] in material_ids)
        needed = {html.unescape(src) for fragment in fragments for src in re.findall(
            r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\'][^>]*>', fragment, flags=re.I)}
    for img in meta.get('images', []):
        if reviewed_plan and img['url'] not in needed:
            continue
        source_path = (cache / img['file']).resolve()
        if reviewed_plan and not source_path.is_relative_to(cache.resolve()):
            raise ValueError('图片路径超出缓存')
        data = source_path.read_bytes()
        if reviewed_plan and (img['url'] in image_map or img.get('sha256') != hashlib.sha256(data).hexdigest()):
            raise ValueError('人工复核来源图片映射重复或哈希不匹配')
        name = hashlib.sha256(data).hexdigest() + Path(img['file']).suffix.lower()
        image_map[img['url']] = name
        copies.append((data, path.parent / prefix / name))
    if reviewed_plan:
        for h in plan.values():
            source = hq[h]
            fragments = [source.get('stem_html', '')] + [o.get('html', '') for o in source.get('options', [])]
            rendered = [html_to_md(fragment, image_map, prefix) for fragment in fragments]
            rendered_analysis = html_to_md(source.get('analysis_html', ''), image_map, prefix)
            if any(not norm(fragment) and '![](' not in fragment for fragment in rendered + [rendered_analysis]):
                raise ValueError(f'华图第 {h + 1} 题渲染后题干、选项或解析为空')
            if any(re.search(r'如(?:上|下|左|右)?图', fragment) for fragment in rendered[1:]) and not any('![](' in fragment for fragment in rendered):
                raise ValueError(f'华图第 {h + 1} 题图形选项缺共享图')
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
    new = update_frontmatter(new, meta, sorted(plan), mode='reviewed-A1' if reviewed_plan else 'A1')
    if new[frontmatter(new).end():] != body:
        raise RuntimeError('更新文件头时改动了正文')
    verify(text, new, plan)
    if reviewed_plan:
        copies.append((review_raw, path.parent / prefix / f"review-{report['review_plan_sha256']}.json"))
        planned = {dest.resolve() for _, dest in copies}
        for ref in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', new):
            resolved = (path.parent / ref).resolve()
            if resolved not in planned and not resolved.is_file():
                raise ValueError(f'图片缺失：{ref}')
        report.update({'after_sha256': hashlib.sha256(new.encode('utf8')).hexdigest(), 'written': False})
        if not write:
            return report
        if expect_after != report['after_sha256']:
            raise ValueError('人工复核写入必须提供与预检一致的 --expect-after')
        review_tools['commit'](path, paper, new, root, copies, json.loads(review_raw)['paper_sha256'])
        report['written'] = True
        return report
    for data, dest in copies:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    path.write_bytes(new.encode('utf-8'))
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
    parser.add_argument('--paper', help='试卷路径，相对仓库根目录')
    parser.add_argument('--cache', type=Path, help='华图试卷缓存目录（含 paper.json）')
    parser.add_argument('--essay-plan', help='申论材料补录计划 JSON')
    parser.add_argument('--expect-after', help='申论写入时必须与预检后 SHA256 一致')
    parser.add_argument('--write', action='store_true', help='写入试卷；不加只输出对齐报告')
    parser.add_argument('--option-q', type=int, help='显式指定一处 A2 选项缺口题号；采用来源整组选项')
    parser.add_argument('--reviewed-plan', type=Path, help='显式人工复核 A1 计划 JSON；锁定来源和原卷哈希')
    args = parser.parse_args()
    if args.essay_plan:
        if args.paper or args.cache or args.option_q is not None or args.reviewed_plan:
            parser.error('申论计划不能与行测参数同时使用')
        previous = sys.argv
        sys.argv = ['essay_gap_fill.py', '--plan', args.essay_plan]
        if args.write:
            sys.argv.append('--write')
        if args.expect_after:
            sys.argv.extend(['--expect-after', args.expect_after])
        try:
            runpy.run_path(str(Path(__file__).with_name('essay_gap_fill.py')), run_name='__main__')
        finally:
            sys.argv = previous
        return 0
    if not args.paper or not args.cache:
        parser.error('行测模式需要 --paper 和 --cache')
    if args.expect_after and not args.reviewed_plan:
        parser.error('--expect-after 仅适用于 --essay-plan 或 --reviewed-plan')
    report = fill(args.paper, args.cache.resolve(), args.write, option_q=args.option_q,
                  reviewed_plan=args.reviewed_plan, expect_after=args.expect_after)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
