#!/usr/bin/env python3
"""Write a single reviewed A1 question from a non-Huatu public source.

This is a generic, fail-closed alternative to huatu_fill.py.  It never
pretends a non-Huatu source is a Huatu cache: the plan carries its own
source identity, evidence files and hashes.

Plan schema (JSON):
{
  "schema_version": 1,
  "paper": "省考/.../行测-....md",
  "paper_sha256": "<sha256 of paper before edit>",
  "target_q": 35,
  "source_q": 34,
  "source_platform": "星光公考",
  "source_url": "https://...",
  "source_title": "...",
  "source_region": "云南",
  "source_year": 2025,
  "source_variant": "统考",
  "source_evidence": [
     {"path": "...txt", "sha256": "...", "role": "stem_options"},
     {"path": "...txt", "sha256": "...", "role": "answer"}
  ],
  "anchors": [
     {"local_q": 33, "source_q": 33, "local_text": "...", "source_text": "..."},
     {"local_q": 36, "source_q": 36, "local_text": "...", "source_text": "..."}
  ],
  "stem": "...",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "D",
  "explanation": "...",
  "source_note": "网友回忆版/机构整理，非官方",
  "reviewer": "...",
  "reviewed_at": "2026-11-07",
  "images": []
}

Usage:
  python3 -I tools/source_fill.py --plan plan.json
  python3 -I tools/source_fill.py --plan plan.json --write --expect-after <sha>
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QRE = re.compile(r'^#{2,3}[ \t]*第[ \t]*(\d+)[ \t]*题.*$', re.M)
STUB = '粉笔暂未收录本题'
PLACEHOLDER = re.compile(r'题目正在全力以赴征集|暂未收录|题目暂缺|题目缺失|来源未提供|暂无答案|暂无解析|^(?:缺|缺失|暂缺)$')
OPT = re.compile(r'^([A-D])[\.．、]\s*(.*)$', re.M)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)|<[^>]+>', '', html.unescape(text))
    return re.sub(r'[\W_]+', '', text)


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


def load_plan(path):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if plan.get('schema_version') != 1:
        raise ValueError('plan schema_version 必须为 1')
    for key in ('paper', 'paper_sha256', 'target_q', 'source_q', 'source_platform', 'source_url',
                'source_title', 'source_region', 'source_year', 'source_variant', 'source_evidence',
                'anchors', 'stem', 'options', 'answer', 'reviewer', 'reviewed_at'):
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
    for a in plan['anchors']:
        for k in ('local_q', 'source_q', 'local_text', 'source_text'):
            if k not in a:
                raise ValueError('锚点缺少 ' + k)
    if plan.get('images'):
        raise ValueError('本工具当前只接受无图片题；含图片请先扩展图片校验')
    return plan, raw


def evidence_text(plan):
    chunks = []
    for item in plan['source_evidence']:
        p = Path(item['path'])
        if not p.is_file():
            raise ValueError('来源证据文件不存在: ' + str(p))
        data = p.read_bytes()
        if sha(data) != item.get('sha256'):
            raise ValueError('来源证据哈希不匹配: ' + str(p))
        chunks.append(data.decode('utf-8', 'replace'))
    return '\n'.join(chunks)


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
    corpus = norm(evidence_text(plan))
    if norm(plan['stem']) not in corpus:
        raise ValueError('来源证据中找不到题干')
    for value in plan['options'].values():
        if norm(value) not in corpus:
            raise ValueError('来源证据中找不到选项: ' + value[:20])
    if norm(plan['answer']) not in corpus:
        raise ValueError('来源证据中找不到答案')
    # anchors: local text must be present in the named non-stub block; source text in evidence
    present = {n: text[s:e] for n, s, e, _ in blocks if STUB not in text[s:e]}
    for a in plan['anchors']:
        lq = int(a['local_q'])
        if lq not in present:
            raise ValueError(f'本地锚点 q{lq} 不存在或仍为占位')
        if norm(a['local_text']) not in norm(present[lq]):
            raise ValueError(f'本地锚点 q{lq} 文本不匹配')
        if norm(a['source_text']) not in corpus:
            raise ValueError(f'来源锚点 q{a["source_q"]} 文本不在证据中')
    # Build replacement, preserving heading and all other blocks byte-for-byte.
    opts = '\n\n'.join(f'**{k}**. {v}' for k, v in plan['options'].items())
    note = plan.get('source_note') or '网友回忆版/机构整理，非官方'
    new_block = (heading + '\n\n' + plan['stem'].strip() + '\n\n' + opts +
                 '\n\n<details><summary>第 ' + str(plan['target_q']) + ' 题 · 答案与解析</summary>\n\n'
                 '**参考答案（公开题本站补录；非官方）**\n\n' + plan['answer'] + '\n\n'
                 '**解析**\n\n' + (plan.get('explanation') or '来源未提供文字解析。').strip() + '\n\n'
                 '**来源**：' + plan['source_platform'] + '《' + plan['source_title'] + '》' +
                 plan['source_url'] + ' 第' + str(plan['source_q']) + '题；' + note + '\n\n</details>\n\n')
    new_text = text[:start] + new_block + text[end:]
    # Only the target block and frontmatter may change.
    before_body = text[frontmatter_bounds(text)[1] + 4:]
    after_body = new_text[frontmatter_bounds(new_text)[1] + 4:]
    bb = {n: norm(before_body[s:e]) for n, s, e, _ in split_questions(before_body)}
    ab = {n: norm(after_body[s:e]) for n, s, e, _ in split_questions(after_body)}
    if set(bb) != set(ab):
        raise ValueError('写入改变了题号集合')
    for n in bb:
        if n != plan['target_q'] and bb[n] != ab[n]:
            raise ValueError(f'写入影响了非目标题 q{n}')
    # frontmatter source registration
    fm_start, fm_end = frontmatter_bounds(new_text)
    fm = new_text[fm_start:fm_end]
    entry = ('  - 来源方: "' + plan['source_platform'].replace('"', "'") + '"\n'
             '    定位: "' + plan['source_url'] + '"\n'
             '    题号: [' + str(plan['source_q']) + ']\n'
             '    用途: "补第 ' + str(plan['target_q']) + ' 题题干、选项、参考答案"\n'
             '    证据: "' + plan['source_title'].replace('"', "'") + '；' + note.replace('"', "'") + '"\n'
             '    核验: "' + plan['reviewer'].replace('"', "'") + '；' + plan['reviewed_at'] + ' 逐题对照来源正文与前后锚点"\n')
    if '来源清单:' in fm:
        # insert before the next top-level frontmatter key after 来源清单
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
        block = ('来源清单:\n' + entry).rstrip('\n').splitlines()
        lines[idx + 1:idx + 1] = block
        fm = '\n'.join(lines)
    # status note
    lines = fm.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith('校验状态:')), None)
    if idx is None:
        lines.append('校验状态: "' + (plan.get('reviewed_at') or '2026-11-08') + ' 公开题本站补入第 ' + str(plan['target_q']) + ' 题；来源见来源清单；非官方"')
    else:
        old = lines[idx]
        if old.rstrip().endswith('"'):
            lines[idx] = old.rstrip()[:-1] + '；' + (plan.get('reviewed_at') or '2026-11-08') + ' 公开题本站补入第 ' + str(plan['target_q']) + ' 题（非官方，来源见来源清单）"'
        else:
            lines[idx] = old + '；' + (plan.get('reviewed_at') or '2026-11-08') + ' 公开题本站补入第 ' + str(plan['target_q']) + ' 题（非官方，来源见来源清单）'
    fm = '\n'.join(lines)
    new_text = new_text[:fm_start] + fm + new_text[fm_end:]
    after = new_text.encode('utf-8')
    return before, after, sha(after), paper



def metadata_update(plan, raw, root):
    paper = root / plan['paper']
    before = paper.read_bytes()
    if sha(before) != plan['paper_sha256']:
        raise ValueError('试卷在计划后已变化（paper_sha256 不匹配）')
    evidence_text(plan)  # validates evidence hashes
    text = before.decode('utf-8')
    fm_start, fm_end = frontmatter_bounds(text)
    lines = text[fm_start:fm_end].splitlines()
    target = str(plan['target_q'])
    starts = [i for i, l in enumerate(lines) if l.strip().startswith('- 来源方:')]
    hit = None
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        block = lines[st:end]
        if any(('补第 ' + target + ' 题') in x for x in block):
            hit = (st, end); break
    if not hit:
        raise ValueError('未找到目标题的来源清单条目')
    st, end = hit
    replaced = False
    for i in range(st, end):
        if re.match(r'^\s*题号:', lines[i]):
            lines[i] = '    题号: [' + str(plan['source_q']) + ']'
            replaced = True
            break
    if not replaced:
        raise ValueError('目标来源条目没有题号字段')
    fm = '\n'.join(lines)
    after = (text[:fm_start] + fm + text[fm_end:]).encode('utf-8')
    return before, after, sha(after), paper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--metadata-only', action='store_true')
    ap.add_argument('--expect-after')
    args = ap.parse_args()
    plan, raw = load_plan(args.plan)
    if args.metadata_only:
        before, after, after_sha, paper = metadata_update(plan, raw, args.root.resolve())
    else:
        before, after, after_sha, paper = validate(plan, raw, args.root.resolve())
    report = {
        'plan': str(Path(args.plan).resolve()), 'plan_sha256': sha(raw),
        'paper': plan['paper'], 'target_q': plan['target_q'], 'source_q': plan['source_q'],
        'source_platform': plan['source_platform'], 'source_url': plan['source_url'],
        'before_sha256': sha(before), 'after_sha256': after_sha,
        'written': False, 'images': len(plan.get('images') or []),
    }
    if args.write:
        if not args.expect_after:
            raise SystemExit('--write 必须同时提供 --expect-after')
        if args.expect_after != after_sha:
            raise SystemExit('--expect-after 与预检 after_sha256 不一致')
        if sha(paper.read_bytes()) != sha(before):
            raise SystemExit('预检后试卷已变化，拒绝写入')
        lock = args.root / 'catalog/.source-fill.lock'
        try:
            handle = lock.open('x', encoding='utf8')
        except FileExistsError:
            raise SystemExit('存在 source-fill 锁，拒绝并发写入')
        try:
            fd, tmp = tempfile.mkstemp(prefix=paper.name + '.', dir=str(paper.parent))
            with os.fdopen(fd, 'wb') as f:
                f.write(after)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, paper)
            report['written'] = True
        finally:
            handle.close()
            lock.unlink(missing_ok=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
