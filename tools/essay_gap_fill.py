#!/usr/bin/env python3
"""Conservative, source-backed essay material gap repair; preview by default.

The JSON plan and source text must be local files. The plan contains:
  target: repository-relative essay file, before_sha256: its expected hash;
  source_file, source_sha256, source_url, source_title;
  anchors: >=2 {kind: "material"|"question", text: verbatim shared snippet};
  renumber: optional {"2": 3, ...} for existing material headings;
  renumber_checks: {"2": "shared excerpt", ...} for every renamed section;
  additions: [{number, text, source_start, source_end}], copied from the source;
  repair_references: boolean (recompute explicitly stated material references).

No network or inferred material/answers. A write requires --write and the exact
after_sha256 printed by a previous dry run via --expect-after.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAT = re.compile(r'^### 材料 (\d+)[ \t]*$', re.M)
QUESTION = re.compile(r'^### 第 (\d+) 题[ \t]*$', re.M)

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def norm(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if c.isalnum())

def material_norm(text: str) -> str:
    """Ignore only whitespace and Unicode width; punctuation remains evidence."""
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if not c.isspace())

def explicit_refs(prompt: str) -> list[int]:
    text = prompt.replace('\\-', '-').replace('—', '-').replace('–', '-')
    result = set()
    for match in re.finditer(r'(?:给定)?(?:材料|资料)\s*(\d+)\s*(?:-\s*(\d+))?', text):
        a = int(match[1]); b = int(match[2] or a)
        if not 1 <= a <= b <= 50: raise ValueError('Invalid material reference range')
        result.update(range(a, b + 1))
    return sorted(result)

def preview(plan: dict, target: bytes, source: bytes) -> bytes:
    if digest(target) != plan['before_sha256']: raise ValueError('Target changed since review')
    if digest(source) != plan['source_sha256']: raise ValueError('Source snapshot changed')
    url = urlsplit(plan['source_url'])
    host = url.hostname or ''
    is_huatu = host.endswith('.huatu.com')
    is_public_paper = host == 'gwy.gkzhenti.cn' and bool(re.fullmatch(r'/paper/\d+', url.path))
    if url.scheme != 'https' or not (is_huatu or is_public_paper) or url.query or url.fragment:
        raise ValueError('Source must be a supported public query-free paper URL')
    provider = '华图教育' if is_huatu else '公开真题库'
    text = target.decode('utf-8'); evidence = source.decode('utf-8')
    if evidence.lstrip().startswith('{'):
        snapshot = json.loads(evidence)
        if snapshot.get('url') != plan['source_url'] or not isinstance(snapshot.get('text'), str):
            raise ValueError('Snapshot source identity mismatch')
        if digest(snapshot['text'].encode('utf-8')) != snapshot.get('sha256'):
            raise ValueError('Snapshot text checksum mismatch')
        evidence = snapshot.get('title', '') + '\n' + snapshot['text']
    if norm(plan['source_title']) not in norm(evidence): raise ValueError('Source title absent')
    for field in ('地区', '年份', '科目', '卷型'):
        match = re.search(r'^' + field + r':\s*"?([^"\n]+?)"?\s*$', text, re.M)
        if not match: raise ValueError('Missing target identity: ' + field)
        value = match.group(1).strip()
        if field == '年份' and is_public_paper and int(value) < 2016:
            raise ValueError('Third-party evidence is limited to 2016 onward')
        if field == '卷型' and value in ('统考', '综合'): continue
        if field == '卷型': value = value.removesuffix('卷')
        if norm(value) not in norm(plan['source_title']): raise ValueError('Source and target identity mismatch: ' + field)
    m_start = text.find('## 给定材料'); q_start = text.find('## 题目')
    if m_start < 0 or q_start <= m_start: raise ValueError('Missing essay section markers')
    material, questions = text[m_start:q_start], text[q_start:]
    anchors = plan.get('anchors', [])
    if len(anchors) < 2 or {a['kind'] for a in anchors} != {'material', 'question'}:
        raise ValueError('Need shared material and question anchors')
    for anchor in anchors:
        snippet = norm(anchor['text'])
        if len(snippet) < 20: raise ValueError('Anchor too short')
        section = material if anchor['kind'] == 'material' else questions
        if snippet not in norm(section) or snippet not in norm(evidence): raise ValueError('Anchor mismatch')
    headings = list(MAT.finditer(material))
    if not headings: raise ValueError('No material headings')
    renumber = {int(k): int(v) for k, v in plan.get('renumber', {}).items()}
    existing = [int(x[1]) for x in headings]
    if not set(renumber).issubset(existing): raise ValueError('Renumber target absent')
    final_numbers = [renumber.get(n, n) for n in existing]
    if final_numbers != sorted(set(final_numbers)): raise ValueError('Renumber is not strictly increasing')
    blocks = []
    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(material)
        n = int(match[1]); block = material[match.start():end]
        if n in renumber:
            snippet = norm(plan.get('renumber_checks', {}).get(str(n), ''))
            if len(snippet) < 20 or snippet not in norm(block) or snippet not in norm(evidence):
                raise ValueError('Renumbered material lacks same-source evidence')
        blocks.append((renumber.get(n, n), MAT.sub(f'### 材料 {renumber.get(n, n)}', block, count=1)))
    for addition in plan['additions']:
        n = int(addition['number']); body = addition['text'].strip()
        if n in final_numbers or n in [x[0] for x in blocks]: raise ValueError('Cannot replace existing material')
        start, end = addition['source_start'], addition['source_end']
        start_hits = list(re.finditer(r'(?m)^[ \t\u3000]*' + re.escape(start), evidence))
        end_hits = list(re.finditer(r'(?m)^[ \t\u3000]*' + re.escape(end), evidence))
        if len(start_hits) != 1 or len(end_hits) != 1: raise ValueError('Material source boundaries not unique')
        a, b = start_hits[0].start(), end_hits[0].start()
        if a >= b or not re.match(rf'\s*(?:(?:给定)?(?:材料|资料)\s*{n}\b|{n}[.．、])', start):
            raise ValueError('Material source label or boundaries mismatch')
        # The start marker itself names the material and must not be included in
        # its body.  Equality (not containment) rejects missing first/last
        # paragraphs as well as edits in the middle.
        source_body = evidence[start_hits[0].end():b]
        if len(norm(body)) < 40 or material_norm(body) != material_norm(source_body):
            raise ValueError('Material differs from the complete source section')
        blocks.append((n, f'### 材料 {n}\n\n{body}\n\n'))
    numbers = sorted(n for n, _ in blocks)
    if len(numbers) != len(set(numbers)): raise ValueError('Duplicate material numbers')
    prefix = material[:headings[0].start()]
    material_out = prefix + ''.join(b for _, b in sorted(blocks))
    if plan.get('repair_references'):
        matches = list(QUESTION.finditer(questions)); pieces = []
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(questions)
            block = questions[match.start():end]
            line = re.search(r'^关联材料：[^\n]*$', block, re.M)
            if not line: raise ValueError('Question lacks association line')
            prompt = block[:line.start()]; refs = explicit_refs(prompt)
            if not refs or not set(refs).issubset(numbers): raise ValueError('Unverifiable association')
            replacement = '关联材料：' + '、'.join('材料 '+str(n) for n in refs)
            block = block[:line.start()] + replacement + block[line.end():]
            pieces.append(block)
        if not matches: raise ValueError('No question headings')
        questions = questions[:matches[0].start()] + ''.join(pieces)
    fm_end = text.find('\n---\n', 4)
    if not text.startswith('---\n') or fm_end < 0: raise ValueError('Missing frontmatter')
    front = text[:fm_end]
    if re.search(r'^来源清单:', front, re.M): raise ValueError('Existing source list requires manual review')
    original = re.search(r'^来源:\s*("(?:[^"\\]|\\.)*")\s*$', front, re.M)
    if not original or not isinstance(json.loads(original[1]), str): raise ValueError('Expected an existing scalar source')
    entry = ('\n来源清单:\n  - 来源方: "原有来源"\n    定位: ' + original[1] +
             '\n    用途: "原有试卷内容"\n  - 来源方: "' + provider + '"\n    定位: "' + plan['source_url'] +
             '"\n    用途: "补充缺失申论材料"\n    核验: "同卷回忆整理，题目和材料锚点对应；原文异文保留、非官方原卷"')
    return (front + entry + text[fm_end:m_start] + material_out + questions).encode('utf-8')

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan', required=True)
    parser.add_argument('--write', action='store_true'); parser.add_argument('--expect-after')
    args = parser.parse_args(); plan_path = Path(args.plan).resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    target = (ROOT / plan['target']).resolve()
    if not target.is_relative_to(ROOT / '省考') or not target.name.startswith('申论-'):
        raise ValueError('Target outside provincial essay papers')
    source = Path(plan['source_file']).resolve()
    before = target.read_bytes(); after = preview(plan, before, source.read_bytes()); after_hash = digest(after)
    print(json.dumps({'target': str(target.relative_to(ROOT)), 'before_sha256': digest(before),
                      'after_sha256': after_hash, 'write': args.write}, ensure_ascii=False))
    if not args.write:
        print(''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), fromfile='before', tofile='after')))
        return
    if args.expect_after != after_hash: raise ValueError('Dry-run after hash required')
    if target.read_bytes() != before: raise ValueError('Target changed during run')
    fd, name = tempfile.mkstemp(dir=target.parent, prefix='.essay-gap-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f: f.write(after)
        os.replace(name, target)
    finally:
        if os.path.exists(name): os.unlink(name)

if __name__ == '__main__': main()
