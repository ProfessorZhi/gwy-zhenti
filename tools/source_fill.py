#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write a single reviewed A1 question from a non-Huatu public source.

Fail-closed source-side validation
----------------------------------
A plan must carry a `source_snapshot` captured from the public source URL by
`tools/source_snapshot.py`.  The snapshot binds every question number to its
actual stem/options/answer.  The tool verifies that:

  * the snapshot file hash matches the plan;
  * the snapshot URL matches `source_url` (normalized);
  * the snapshot contains source_q-1, source_q and source_q+1;
  * the target stem/options/answer match the source_q record;
  * every anchor's source_text occurs in the named anchor source_q record;
  * at least one anchor is before and one after the target.

A free-text evidence file alone is NOT sufficient any more.

Other operations
----------------
  --metadata-only   sync frontmatter 题号 and the body **来源** 第N题 line
  --verify-existing verify an already-written block against the snapshot
  --withdraw        restore the stub and remove the source entry (fail-closed)

Usage:
  python3 -I tools/source_fill.py --plan plan.json
  python3 -I tools/source_fill.py --plan plan.json --write --expect-after <sha>
  python3 -I tools/source_fill.py --plan plan.json --metadata-only --write --expect-after <sha>
  python3 -I tools/source_fill.py --plan plan.json --verify-existing
  python3 -I tools/source_fill.py --plan plan.json --withdraw --write --expect-after <sha>
"""
import argparse
import datetime
import difflib
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QRE = re.compile(r'^#{2,3}[ \t]*第[ \t]*(\d+)[ \t]*题.*$', re.M)
STUB = '粉笔暂未收录本题'
PLACEHOLDER = re.compile(r'题目正在全力以赴征集|暂未收录|题目暂缺|题目缺失|来源未提供|暂无答案|暂无解析|^(?:缺|缺失|暂缺)$')
DATE = datetime.date.today().isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm(text):
    text = re.sub(r'\{\{IMG\d+\}\}', '', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)|<[^>]+>', '', html.unescape(text))
    return re.sub(r'[\W_]+', '', text)


def normalize_url(url):
    url = str(url).strip()
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe='/%:@')
    query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe='=&%:@/?')
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def frontmatter_bounds(text):
    if not text.startswith('---\n'):
        raise ValueError('试卷缺少 frontmatter')
    end = text.find('\n---', 4)
    if end < 0:
        raise ValueError('试卷 frontmatter 未闭合')
    return 4, end


def split_questions(text):
    ms = list(QRE.finditer(text))
    return [(int(m.group(1)), m.start(), ms[i + 1].start() if i + 1 < len(ms) else len(text), m.group(0))
            for i, m in enumerate(ms)]


def load_json(path, expected_sha, label):
    p = Path(path)
    if not p.is_file():
        raise ValueError(label + ' 文件不存在: ' + str(p))
    data = p.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError(label + ' 哈希不匹配: ' + str(p))
    try:
        obj = json.loads(data.decode('utf-8'))
    except Exception as exc:
        raise ValueError(label + ' 不是合法 JSON: ' + str(p)) from exc
    if obj.get('schema_version') != 1 or not isinstance(obj.get('questions'), dict):
        raise ValueError(label + ' schema/问题表不合法: ' + str(p))
    return obj


def snapshot_question(snap, q, label='source_snapshot'):
    rec = snap['questions'].get(str(int(q)))
    if not isinstance(rec, dict):
        raise ValueError(f'{label} 缺少源题号 q{q}')
    if not rec.get('stem'):
        raise ValueError(f'{label} q{q} 题干为空')
    if not isinstance(rec.get('options'), dict):
        raise ValueError(f'{label} q{q} 选项不是对象')
    return rec


def check_snapshot_url(snap, plan_url, label='source_snapshot'):
    if normalize_url(snap.get('url', '')) != normalize_url(plan_url):
        raise ValueError(f'{label} URL 与 source_url 不一致: {snap.get("url")!r} != {plan_url!r}')


def check_target_against_snapshot(plan, snap):
    sq = int(plan['source_q'])
    check_snapshot_url(snap, plan['source_url'])
    # source-side neighbours are mandatory
    for n in (sq - 1, sq, sq + 1):
        if n < 1:
            raise ValueError('source_q 过小，无法提供 source_q-1')
        snapshot_question(snap, n)
    rec = snapshot_question(snap, sq)
    if set(rec['options']) != set('ABCD'):
        raise ValueError(f'source_snapshot q{sq} 选项不完整')
    if norm(plan['stem']) != norm(rec['stem']):
        if plan.get('stem_equivalence') != 'minor_wording':
            raise ValueError(f'plan 题干与 source_snapshot q{sq} 题干不一致')
        if not plan.get('stem_equivalence_note'):
            raise ValueError('stem_equivalence=minor_wording 必须写 stem_equivalence_note')
        ratio = difflib.SequenceMatcher(None, norm(plan['stem']), norm(rec['stem'])).ratio()
        if ratio < 0.90:
            raise ValueError(f'plan 题干与 source_snapshot q{sq} 相似度 {ratio:.3f} < 0.90')
    for k in 'ABCD':
        if norm(plan['options'][k]) != norm(rec['options'][k]):
            raise ValueError(f'plan 选项 {k} 与 source_snapshot q{sq} 不一致')
    answer = rec.get('answer')
    if answer and answer != plan['answer']:
        raise ValueError(f'source_snapshot q{sq} 答案 {answer} 与 plan 答案 {plan["answer"]} 不一致')
    if not answer:
        ansnap = plan.get('answer_snapshot')
        if not ansnap:
            raise ValueError(f'source_snapshot q{sq} 无答案，且未提供 answer_snapshot')
        asnap = load_json(ansnap['path'], ansnap['sha256'], 'answer_snapshot')
        check_snapshot_url(asnap, ansnap.get('url') or plan['source_url'], 'answer_snapshot')
        aq = int(ansnap['source_q'])
        for n in (aq - 1, aq, aq + 1):
            if n < 1:
                raise ValueError('answer_snapshot source_q 过小')
            snapshot_question(asnap, n, 'answer_snapshot')
        arec = snapshot_question(asnap, aq, 'answer_snapshot')
        if arec.get('answer') != plan['answer']:
            raise ValueError(f'answer_snapshot q{aq} 答案 {arec.get("answer")} 与 plan 答案 {plan["answer"]} 不一致')
        eq = ansnap.get('equivalence', 'exact')
        left = norm(rec['stem'] + ' ' + ' '.join(rec['options'][k] for k in 'ABCD'))
        right = norm(arec['stem'] + ' ' + ' '.join(arec['options'].get(k, '') for k in 'ABCD'))
        if eq == 'exact':
            if left != right:
                raise ValueError('answer_snapshot 同题文本不相等（equivalence=exact）')
        elif eq == 'minor_wording':
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio < 0.90:
                raise ValueError(f'answer_snapshot 同题相似度 {ratio:.3f} < 0.90')
            if not ansnap.get('note'):
                raise ValueError('answer_snapshot equivalence=minor_wording 必须写 note')
        else:
            raise ValueError('answer_snapshot equivalence 必须为 exact 或 minor_wording')
    return rec


def check_anchors(plan, snap, text):
    sq = int(plan['source_q'])
    blocks = {n: text[s:e] for n, s, e, _ in split_questions(text) if STUB not in text[s:e]}
    for a in plan['anchors']:
        lq = int(a['local_q']); aq = int(a['source_q'])
        if lq not in blocks:
            raise ValueError(f'本地锚点 q{lq} 不存在或仍为占位')
        if norm(a['local_text']) not in norm(blocks[lq]):
            raise ValueError(f'本地锚点 q{lq} 文本不匹配')
        rec = snapshot_question(snap, aq)
        corpus = norm(rec['stem'] + ' ' + ' '.join(rec['options'].get(k, '') for k in 'ABCD'))
        if norm(a['source_text']) not in corpus:
            raise ValueError(f'来源锚点 q{aq} 文本不在 source_snapshot 的 q{aq} 记录中')
    if not any(int(a['source_q']) < sq for a in plan['anchors']) or \
       not any(int(a['source_q']) > sq for a in plan['anchors']):
        raise ValueError('锚点必须覆盖目标题前后')


def parse_filled_block(block):
    body = block.split('<details>')[0]
    lines = [l.rstrip() for l in body.splitlines()]
    if lines and lines[0].startswith('#'):
        lines = lines[1:]
    oi = next((i for i, l in enumerate(lines) if re.match(r'^\s*(?:\*\*)?A(?:\*\*)?[\.．、]', l)), None)
    if oi is None:
        raise ValueError('已写题块没有 A 选项')
    stem = '\n'.join(l for l in lines[:oi] if l.strip()).strip()
    opts = {}
    cur = None; buf = []
    for l in lines[oi:]:
        m = re.match(r'^\s*(?:\*\*)?([A-D])(?:\*\*)?[\.．、]\s*(.*)$', l)
        if m:
            if cur: opts[cur] = ' '.join(buf).strip()
            cur = m.group(1); buf = [m.group(2).strip()]
        elif l.strip() and cur:
            buf.append(l.strip())
    if cur: opts[cur] = ' '.join(buf).strip()
    am = re.search(r'\*\*参考答案（公开题本站补录；非官方）\*\*\s*\n+\s*([A-D])', block)
    if not am:
        raise ValueError('已写题块没有补录答案')
    return stem, opts, am.group(1)


def _safe_assets_dir(plan):
    assets = str(plan.get('assets_dir') or '')
    if not assets or assets.startswith('/') or '..' in Path(assets).parts or '/' in assets or '\\' in assets:
        raise ValueError('assets_dir 必须是试卷同目录下的单个相对目录名，不得含路径分隔符或 ..')
    if not Path(assets).name.startswith('assets-'):
        raise ValueError('assets_dir 必须以 assets- 开头')
    return assets


def check_images(plan, root):
    """Validate image evidence and target paths; return [(source, target)]."""
    if not plan.get('images'):
        return []
    assets = _safe_assets_dir(plan)
    paper_dir = (root / plan['paper']).parent
    assets_dir = paper_dir / '图片' / assets
    spdf = plan['source_pdf']
    if not str(spdf.get('url', '')).startswith(('http://', 'https://')):
        raise ValueError('source_pdf.url 必须是公开 http(s) 地址')
    for key in ('sha256', 'answer_sha256'):
        if spdf.get(key) and not re.fullmatch(r'[0-9a-f]{64}', str(spdf[key])):
            raise ValueError('source_pdf.' + key + ' 必须是 64 位小写 sha256')
    if spdf.get('path'):
        p = Path(spdf['path'])
        if not p.is_file():
            raise ValueError('source_pdf.path 不存在: ' + str(p))
        if sha(p.read_bytes()) != spdf.get('sha256'):
            raise ValueError('source_pdf 哈希不匹配')
    ops = []
    markers = []
    for img in plan['images']:
        for key in ('source_path', 'sha256', 'filename', 'alt', 'marker'):
            if key not in img:
                raise ValueError('image 缺少字段 ' + key)
        src = Path(img['source_path'])
        if not src.is_file():
            raise ValueError('图片源文件不存在: ' + str(src))
        data = src.read_bytes()
        if sha(data) != img['sha256']:
            raise ValueError('图片哈希不匹配: ' + str(src))
        name = str(img['filename'])
        if Path(name).name != name or name in ('.', '..') or not re.search(r'\.(?:png|jpe?g|webp)$', name, re.I):
            raise ValueError('图片 filename 必须是无路径的安全文件名: ' + name)
        marker = str(img['marker'])
        if not re.fullmatch(r'\{\{IMG\d+\}\}', marker):
            raise ValueError('图片 marker 必须形如 {{IMG1}}')
        if plan['stem'].count(marker) != 1:
            raise ValueError(f'题干中 marker {marker} 必须恰好出现一次')
        markers.append(marker)
        target = assets_dir / name
        if target.exists() and sha(target.read_bytes()) != img['sha256']:
            raise ValueError('目标图片已存在且哈希不同，拒绝覆盖: ' + str(target))
        ops.append((src, target))
    if len(markers) != len(set(markers)):
        raise ValueError('图片 marker 重复')
    return ops


def render_stem(plan):
    stem = plan['stem']
    if not plan.get('images'):
        return stem
    assets = _safe_assets_dir(plan)
    for img in plan['images']:
        stem = stem.replace(img['marker'], f"![{img['alt']}](图片/{assets}/{img['filename']})")
    if re.search(r'\{\{IMG\d+\}\}', stem):
        raise ValueError('题干仍有未替换的图片 marker')
    return stem


def copy_images(plan, root):
    for src, target in check_images(plan, root):
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=target.name + '.', dir=str(target.parent))
        with os.fdopen(fd, 'wb') as f:
            f.write(src.read_bytes()); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, target)



def load_plan(path):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if plan.get('schema_version') != 1:
        raise ValueError('plan schema_version 必须为 1')
    base = ('paper', 'paper_sha256', 'target_q', 'reviewer', 'reviewed_at')
    for key in base:
        if key not in plan:
            raise ValueError('plan 缺少字段 ' + key)
    if plan.get('withdraw'):
        for key in ('reason', 'expected_current'):
            if key not in plan:
                raise ValueError('withdraw plan 缺少字段 ' + key)
        return plan, raw
    if plan.get('metadata_only'):
        for key in ('source_q', 'old_source_q', 'source_platform', 'source_url', 'source_title',
                    'source_region', 'source_year', 'source_variant', 'source_snapshot'):
            if key not in plan:
                raise ValueError('metadata plan 缺少字段 ' + key)
        return plan, raw
    for key in ('source_q', 'source_platform', 'source_url', 'source_title', 'source_region',
                'source_year', 'source_variant', 'source_snapshot', 'anchors', 'stem', 'options', 'answer'):
        if key not in plan:
            raise ValueError('plan 缺少字段 ' + key)
    if not str(plan['source_url']).startswith(('http://', 'https://')):
        raise ValueError('source_url 必须是公开 http(s) 地址')
    if plan['answer'] not in list('ABCD'):
        raise ValueError('answer 必须为 A-D')
    if set(plan['options']) != set('ABCD'):
        raise ValueError('options 必须恰好为 A-D')
    if len(plan['anchors']) < 2:
        raise ValueError('至少需要两个锚点')
    if not any(a.get('local_q', 0) < plan['target_q'] for a in plan['anchors']) or \
       not any(a.get('local_q', 0) > plan['target_q'] for a in plan['anchors']):
        raise ValueError('锚点必须覆盖目标题前后')
    if plan.get('images'):
        if not plan.get('assets_dir'):
            raise ValueError('含图片题必须提供 assets_dir')
        if not plan.get('source_pdf'):
            raise ValueError('含图片题必须提供 source_pdf')
        if not isinstance(plan['images'], list) or not plan['images']:
            raise ValueError('images 必须是非空数组')
    return plan, raw


def validate(plan, raw, root):
    paper = root / plan['paper']
    if not paper.is_file():
        raise ValueError('试卷不存在: ' + plan['paper'])
    before = paper.read_bytes()
    if sha(before) != plan['paper_sha256']:
        raise ValueError('试卷在计划后已变化（paper_sha256 不匹配）')
    text = before.decode('utf-8')
    blocks = split_questions(text)
    target = [b for b in blocks if b[0] == plan['target_q']]
    if len(target) != 1:
        raise ValueError('目标题号不存在或不唯一')
    q, start, end, heading = target[0]
    block = text[start:end]
    if STUB not in block:
        raise ValueError('目标题不是“粉笔暂未收录”占位')
    if PLACEHOLDER.search(norm(plan['stem'])) or PLACEHOLDER.search(norm(' '.join(plan['options'].values()))):
        raise ValueError('来源题干/选项仍含占位词')
    if len(norm(plan['stem'])) < 5:
        raise ValueError('题干过短')
    for letter, value in plan['options'].items():
        if len(norm(value)) < 1:
            raise ValueError('选项为空: ' + letter)
    snap = load_json(plan['source_snapshot']['path'], plan['source_snapshot']['sha256'], 'source_snapshot')
    check_target_against_snapshot(plan, snap)
    check_anchors(plan, snap, text)
    check_images(plan, root)
    # Build replacement, preserving heading and all other blocks byte-for-byte.
    opts = '\n\n'.join(f'**{k}**. {v}' for k, v in plan['options'].items())
    note = plan.get('source_note') or '网友回忆版/机构整理，非官方'
    url = normalize_url(plan['source_url'])
    new_block = (heading + '\n\n' + render_stem(plan).strip() + '\n\n' + opts +
                 '\n\n<details><summary>第 ' + str(plan['target_q']) + ' 题 · 答案与解析</summary>\n\n'
                 '**参考答案（公开题本站补录；非官方）**\n\n' + plan['answer'] + '\n\n'
                 '**解析**\n\n' + (plan.get('explanation') or '来源未提供文字解析。').strip() + '\n\n'
                 '**来源**：' + plan['source_platform'] + '《' + plan['source_title'] + '》' +
                 url + ' 第' + str(plan['source_q']) + '题；' + note + '\n\n</details>\n\n')
    new_text = text[:start] + new_block + text[end:]
    before_body = text[frontmatter_bounds(text)[1] + 4:]
    after_body = new_text[frontmatter_bounds(new_text)[1] + 4:]
    bb = {n: norm(before_body[s:e]) for n, s, e, _ in split_questions(before_body)}
    ab = {n: norm(after_body[s:e]) for n, s, e, _ in split_questions(after_body)}
    if set(bb) != set(ab):
        raise ValueError('写入改变了题号集合')
    for n in bb:
        if n != plan['target_q'] and bb[n] != ab[n]:
            raise ValueError(f'写入影响了非目标题 q{n}')
    fm_start, fm_end = frontmatter_bounds(new_text)
    fm = new_text[fm_start:fm_end]
    entry = ('  - 来源方: "' + plan['source_platform'].replace('"', "'") + '"\n'
             '    定位: "' + url + '"\n'
             '    题号: [' + str(plan['source_q']) + ']\n'
             '    用途: "补第 ' + str(plan['target_q']) + ' 题题干、选项、参考答案"\n'
             '    证据: "' + plan['source_title'].replace('"', "'") + '；' + note.replace('"', "'") + '"\n'
             '    核验: "' + plan['reviewer'].replace('"', "'") + '；' + plan['reviewed_at'] + ' 逐题对照来源正文与前后锚点"\n')
    if '来源清单:' in fm:
        lines = fm.splitlines()
        idx = next(i for i, l in enumerate(lines) if l.strip() == '来源清单:')
        j = idx + 1
        while j < len(lines) and (not lines[j] or lines[j].startswith(' ')):
            j += 1
        lines[j:j] = entry.rstrip('\n').splitlines()
        fm = '\n'.join(lines)
    else:
        lines = fm.splitlines()
        idx = next((i for i, l in enumerate(lines) if l.startswith('来源:')), None)
        if idx is None:
            raise ValueError('frontmatter 缺少 来源/来源清单，无法登记')
        lines[idx + 1:idx + 1] = ('来源清单:\n' + entry).rstrip('\n').splitlines()
        fm = '\n'.join(lines)
    lines = fm.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith('校验状态:')), None)
    if idx is None:
        lines.append('校验状态: "' + (plan.get('reviewed_at') or DATE) + ' 公开题本站补入第 ' + str(plan['target_q']) + ' 题；来源见来源清单；非官方"')
    else:
        old = lines[idx]
        add = '；' + (plan.get('reviewed_at') or DATE) + ' 公开题本站补入第 ' + str(plan['target_q']) + ' 题（非官方，来源见来源清单）'
        lines[idx] = old.rstrip()[:-1] + add + '"' if old.rstrip().endswith('"') else old + add
    fm = '\n'.join(lines)
    new_text = new_text[:fm_start] + fm + new_text[fm_end:]
    after = new_text.encode('utf-8')
    return before, after, sha(after), paper


def metadata_update(plan, raw, root):
    paper = root / plan['paper']
    before = paper.read_bytes()
    if sha(before) != plan['paper_sha256']:
        raise ValueError('试卷在计划后已变化（paper_sha256 不匹配）')
    snap = load_json(plan['source_snapshot']['path'], plan['source_snapshot']['sha256'], 'source_snapshot')
    text = before.decode('utf-8')
    _tmp_blocks = split_questions(text)
    _t = [b for b in _tmp_blocks if b[0] == plan['target_q']]
    if len(_t) != 1:
        raise ValueError('目标题号不存在或不唯一')
    _stem, _opts, _ans = parse_filled_block(text[_t[0][1]:_t[0][2]])
    _check = dict(plan); _check.update({'stem': _stem, 'options': _opts, 'answer': _ans})
    check_target_against_snapshot(_check, snap)
    blocks = split_questions(text)
    target = [b for b in blocks if b[0] == plan['target_q']]
    if len(target) != 1:
        raise ValueError('目标题号不存在或不唯一')
    q, start, end, heading = target[0]
    block = text[start:end]
    if STUB in block:
        raise ValueError('目标题仍为占位，不能做 metadata-only')
    old_q = int(plan['old_source_q'])
    new_q = int(plan['source_q'])
    src_lines = [l for l in block.splitlines() if l.lstrip().startswith('**来源**')]
    if len(src_lines) != 1:
        raise ValueError('目标题的 **来源** 行不唯一')
    src = src_lines[0]
    m = re.search(r'第\s*(\d+)\s*题', src)
    if not m or int(m.group(1)) != old_q:
        raise ValueError(f'正文 **来源** 行不是第{old_q}题: {src[:120]}')
    new_src = src[:m.start()] + f'第{new_q}题' + src[m.end():]
    new_block = block.replace(src, new_src, 1)
    new_text = text[:start] + new_block + text[end:]
    # frontmatter source entry
    fm_start, fm_end = frontmatter_bounds(new_text)
    lines = new_text[fm_start:fm_end].splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip().startswith('- 来源方:')]
    hit = None
    for i, st in enumerate(starts):
        en = starts[i + 1] if i + 1 < len(starts) else len(lines)
        if any(('补第 ' + str(plan['target_q']) + ' 题') in x for x in lines[st:en]):
            hit = (st, en); break
    if not hit:
        raise ValueError('未找到目标题的来源清单条目')
    st, en = hit
    replaced = False
    for i in range(st, en):
        if re.match(r'^\s*题号:', lines[i]):
            lines[i] = '    题号: [' + str(new_q) + ']'
            replaced = True; break
    if not replaced:
        raise ValueError('目标来源条目没有题号字段')
    fm = '\n'.join(lines)
    after = (new_text[:fm_start] + fm + new_text[fm_end:]).encode('utf-8')
    return before, after, sha(after), paper


def verify_existing(plan, root):
    paper = root / plan['paper']
    if not paper.is_file():
        raise ValueError('试卷不存在')
    text = paper.read_bytes().decode('utf-8')
    blocks = split_questions(text)
    target = [b for b in blocks if b[0] == plan['target_q']]
    if len(target) != 1:
        raise ValueError('目标题号不存在或不唯一')
    q, start, end, heading = target[0]
    block = text[start:end]
    if STUB in block:
        raise ValueError('目标题仍为占位')
    if norm(plan['stem']) not in norm(block):
        raise ValueError('已写题干与 plan 不一致')
    for k, v in plan['options'].items():
        if norm(v) not in norm(block):
            raise ValueError(f'已写选项 {k} 与 plan 不一致')
    if not re.search(r'\*\*参考答案（公开题本站补录；非官方）\*\*\s*\n+\s*' + plan['answer'], block):
        raise ValueError('已写答案与 plan 不一致')
    snap = load_json(plan['source_snapshot']['path'], plan['source_snapshot']['sha256'], 'source_snapshot')
    check_target_against_snapshot(plan, snap)
    check_anchors(plan, snap, text)
    check_images(plan, root)
    return True


def withdraw_block(plan, raw, root):
    paper = root / plan['paper']
    before = paper.read_bytes()
    if sha(before) != plan['paper_sha256']:
        raise ValueError('试卷在计划后已变化（paper_sha256 不匹配）')
    text = before.decode('utf-8')
    blocks = split_questions(text)
    target = [b for b in blocks if b[0] == plan['target_q']]
    if len(target) != 1:
        raise ValueError('目标题号不存在或不唯一')
    q, start, end, heading = target[0]
    block = text[start:end]
    if STUB in block:
        raise ValueError('目标题已是占位，无需撤回')
    exp = plan['expected_current']
    if norm(exp['stem']) not in norm(block):
        raise ValueError('当前题干与 expected_current 不一致，拒绝撤回')
    for k, v in exp['options'].items():
        if norm(v) not in norm(block):
            raise ValueError(f'当前选项 {k} 与 expected_current 不一致')
    if not re.search(r'\*\*参考答案（公开题本站补录；非官方）\*\*\s*\n+\s*' + exp['answer'], block):
        raise ValueError('当前答案与 expected_current 不一致')
    stub = (heading + '\n\n' + STUB + '（来源缺题，题位保留）\n\n'
            '<details><summary>第 ' + str(plan['target_q']) + ' 题 · 答案与解析</summary>\n\n'
            '**答案状态：unknown（来源未提供）**\n\n'
            '**解析状态：unknown（来源未提供）**\n\n</details>\n\n')
    new_text = text[:start] + stub + text[end:]
    fm_start, fm_end = frontmatter_bounds(new_text)
    lines = new_text[fm_start:fm_end].splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip().startswith('- 来源方:')]
    hit = None
    for i, st in enumerate(starts):
        en = starts[i + 1] if i + 1 < len(starts) else len(lines)
        if any(('补第 ' + str(plan['target_q']) + ' 题') in x for x in lines[st:en]):
            hit = (st, en); break
    if not hit:
        raise ValueError('未找到目标题的来源清单条目')
    st, en = hit
    del lines[st:en]
    # If 来源清单 became empty, remove the key.
    try:
        key = next(i for i, l in enumerate(lines) if l.strip() == '来源清单:')
        if key + 1 >= len(lines) or not lines[key + 1].startswith(' '):
            del lines[key]
    except StopIteration:
        pass
    idx = next((i for i, l in enumerate(lines) if l.startswith('校验状态:')), None)
    note = '；' + (plan.get('reviewed_at') or DATE) + ' 撤回第 ' + str(plan['target_q']) + ' 题：' + plan['reason']
    if idx is None:
        lines.append('校验状态: "' + note.lstrip('；') + '"')
    else:
        old = lines[idx]
        lines[idx] = old.rstrip()[:-1] + note + '"' if old.rstrip().endswith('"') else old + note
    fm = '\n'.join(lines)
    after = (new_text[:fm_start] + fm + new_text[fm_end:]).encode('utf-8')
    # only the target block and frontmatter may change
    before_body = text[frontmatter_bounds(text)[1] + 4:]
    after_body = after.decode('utf-8')[frontmatter_bounds(after.decode('utf-8'))[1] + 4:]
    bb = {n: norm(before_body[s:e]) for n, s, e, _ in split_questions(before_body)}
    ab = {n: norm(after_body[s:e]) for n, s, e, _ in split_questions(after_body)}
    if set(bb) != set(ab):
        raise ValueError('撤回改变了题号集合')
    for n in bb:
        if n != plan['target_q'] and bb[n] != ab[n]:
            raise ValueError(f'撤回影响了非目标题 q{n}')
    return before, after, sha(after), paper


def write_receipt(path, action, plan, raw, before_sha, after_sha):
    if not path:
        return
    rec = {
        'action': action, 'target': f"{plan['paper']} q{plan['target_q']}",
        'source_q': plan.get('source_q'), 'source_url': normalize_url(plan.get('source_url', '')),
        'source_snapshot_sha256': (plan.get('source_snapshot') or {}).get('sha256'),
        'answer_snapshot_sha256': (plan.get('answer_snapshot') or {}).get('sha256'),
        'plan_sha256': sha(raw), 'before_sha256': before_sha, 'after_sha256': after_sha,
        'at': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
    }
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--metadata-only', action='store_true')
    ap.add_argument('--verify-existing', action='store_true')
    ap.add_argument('--withdraw', action='store_true')
    ap.add_argument('--expect-after')
    ap.add_argument('--receipt')
    args = ap.parse_args()
    plan, raw = load_plan(args.plan)
    root = args.root.resolve()
    if args.verify_existing:
        verify_existing(plan, root)
        paper_path = root / plan['paper']
        cur = sha(paper_path.read_bytes())
        if args.receipt:
            write_receipt(args.receipt, 'verify', plan, raw, cur, cur)
        print(json.dumps({'verified': True, 'paper': plan['paper'], 'target_q': plan['target_q'],
                          'source_q': plan['source_q'],
                          'source_snapshot': plan['source_snapshot']['path'],
                          'paper_sha256': cur}, ensure_ascii=False, indent=2))
        return 0
    if args.withdraw:
        before, after, after_sha, paper = withdraw_block(plan, raw, root)
        action = 'withdrawn'
    elif args.metadata_only:
        before, after, after_sha, paper = metadata_update(plan, raw, root)
        action = 'metadata'
    else:
        before, after, after_sha, paper = validate(plan, raw, root)
        action = 'write'
    report = {
        'plan': str(Path(args.plan).resolve()), 'plan_sha256': sha(raw),
        'paper': plan['paper'], 'target_q': plan['target_q'], 'source_q': plan.get('source_q'),
        'source_platform': plan.get('source_platform',''), 'source_url': normalize_url(plan.get('source_url','')) if plan.get('source_url') else '',
        'before_sha256': sha(before), 'after_sha256': after_sha, 'written': False,
        'images': len(plan.get('images') or []), 'action': action,
    }
    if args.write:
        if not args.expect_after:
            raise SystemExit('--write 必须同时提供 --expect-after')
        if args.expect_after != after_sha:
            raise SystemExit('--expect-after 与预检 after_sha256 不一致')
        if sha(paper.read_bytes()) != sha(before):
            raise SystemExit('预检后试卷已变化，拒绝写入')
        if plan.get('images'):
            copy_images(plan, root)
        lock = root / 'catalog/.source-fill.lock'
        try:
            handle = lock.open('x', encoding='utf8')
        except FileExistsError:
            raise SystemExit('存在 source-fill 锁，拒绝并发写入')
        try:
            fd, tmp = tempfile.mkstemp(prefix=paper.name + '.', dir=str(paper.parent))
            with os.fdopen(fd, 'wb') as f:
                f.write(after); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, paper)
            report['written'] = True
            write_receipt(args.receipt, action, plan, raw, sha(before), after_sha)
        finally:
            handle.close()
            lock.unlink(missing_ok=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
