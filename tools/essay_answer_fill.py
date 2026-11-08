#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replace a GPT-6/unknown essay answer with a public, non-AI source answer.

Fail-closed: the plan carries a source snapshot (URL/title/text/SHA), answer and
scoring strings that must occur in that snapshot, >=2 anchors that must occur in
both the target question block and the snapshot, an expected old marker, and a
before_sha256.  A write requires the exact after_sha256 from a dry run.

Usage:
  python3 -I tools/essay_answer_fill.py --plan plan.json
  python3 -I tools/essay_answer_fill.py --plan plan.json --write --expect-after SHA
"""
import argparse, hashlib, html, json, os, re, sys, tempfile, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QRE = re.compile(r'^### 第 (\d+) 题[ \t]*$', re.M)

def sha(b): return hashlib.sha256(b).hexdigest()
def norm(s): return ''.join(c for c in unicodedata.normalize('NFKC', html.unescape(s)) if c.isalnum())
def fm_bounds(text):
    if not text.startswith('---\n'): raise ValueError('frontmatter missing')
    end = text.find('\n---', 4)
    if end < 0: raise ValueError('frontmatter unclosed')
    return 4, end

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--root', type=Path, default=ROOT)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--expect-after')
    args = ap.parse_args()
    root = args.root.resolve()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    for k in ('target','before_sha256','question','source_file','source_sha256','source_url',
              'source_title','answer_label','answer','scoring','anchors','expected_old_marker'):
        if k not in plan: raise ValueError('plan missing '+k)
    target = (root / plan['target']).resolve()
    if not target.is_relative_to(root / '省考') or not target.name.startswith('申论-'):
        raise ValueError('target must be a provincial essay paper')
    before = target.read_bytes()
    if sha(before) != plan['before_sha256']: raise ValueError('target changed since review')
    src_path = Path(plan['source_file'])
    if not src_path.is_absolute(): src_path = root / src_path
    src_raw = src_path.read_bytes()
    if sha(src_raw) != plan['source_sha256']: raise ValueError('source snapshot changed')
    src = json.loads(src_raw.decode('utf-8'))
    if src.get('url') != plan['source_url']: raise ValueError('source URL mismatch')
    if src.get('title') != plan['source_title']: raise ValueError('source title mismatch')
    text = src.get('text','')
    if sha(text.encode()) != src.get('sha256'): raise ValueError('source text checksum mismatch')
    evidence = (src.get('title','') + '\n' + text + '\n' +
                '\n'.join(str(v) for v in (src.get('scoring_summary') or {}).values()))
    if not plan['answer'].strip() or norm(plan['answer']) not in norm(evidence):
        raise ValueError('answer not found in source snapshot')
    if not plan['scoring'].strip() or norm(plan['scoring']) not in norm(evidence):
        raise ValueError('scoring not found in source snapshot')
    paper = before.decode('utf-8')
    ms = list(QRE.finditer(paper))
    hit = [m for m in ms if int(m.group(1)) == int(plan['question'])]
    if len(hit) != 1: raise ValueError('target question missing or duplicated')
    m = hit[0]
    end = ms[ms.index(m)+1].start() if ms.index(m)+1 < len(ms) else len(paper)
    block = paper[m.start():end]
    if block.count('<details>') != 1 or '</details>' not in block:
        raise ValueError('target block must contain exactly one details block')
    if norm(plan['expected_old_marker']) not in norm(block):
        raise ValueError('expected old marker not found')
    for a in plan['anchors']:
        snippet = norm(a.get('text',''))
        if len(snippet) < 8: raise ValueError('anchor too short')
        if snippet not in norm(block): raise ValueError('anchor not in target block: '+a.get('text','')[:30])
        if snippet not in norm(evidence): raise ValueError('anchor not in source snapshot: '+a.get('text','')[:30])
    details = ('<details>\n<summary>第 %d 题 · 答案与解析</summary>\n\n' % int(plan['question']) +
               '**参考答案（%s）**\n\n' % plan['answer_label'] +
               plan['answer'].strip() + '\n\n' +
               '**评分参考**：' + plan['scoring'].strip() + '\n\n' +
               '**来源**：' + plan['source_title'] + '（' + (src.get('institution') or '') + '）' +
               plan['source_url'] + '；' + (plan.get('note') or '非官方参考答案') + '\n\n</details>')
    pre = block[:block.find('<details>')]
    post = block[block.find('</details>')+len('</details>'):]
    new_block = pre + details + post
    new_paper = paper[:m.start()] + new_block + paper[end:]
    qn = int(plan['question'])
    new_paper = new_paper.replace(f'| {qn} | 小题参考作答 | GPT-6生成（非官方） |',
                                  f'| {qn} | 小题参考作答 | 华图网校参考答案（非官方） |')
    if qn == 4:
        new_paper = new_paper.replace('第 1、4 题为 GPT-6 生成草稿（非官方）',
                                      '第 1、4 题为华图网校参考答案（非官方）')
    # frontmatter: remove the question from GPT-6 list; update status/refs/source list
    fs, fe = fm_bounds(new_paper)
    front = new_paper[fs:fe]
    lines = front.splitlines()
    lines = [l for l in lines if not re.match(r'^GPT-6生成参考答案题号:\s*\[\s*\]\s*$', l)]
    for i,l in enumerate(lines):
        mm = re.match(r'^(GPT-6生成参考答案题号:\s*)\[(.*?)\]\s*$', l)
        if mm:
            nums = [x.strip() for x in mm.group(2).split(',') if x.strip()]
            nums = [x for x in nums if x != str(plan['question'])]
            if nums:
                lines[i] = mm.group(1) + '[' + ', '.join(nums) + ']'
            else:
                lines[i] = ''
    lines = [l for l in lines if l != '']
    for i,l in enumerate(lines):
        if l.startswith('校验状态:'):
            lines[i] = re.sub(r'第1、4题为GPT-6生成参考答案，非官方答案',
                              '第1、4题为华图网校参考答案，非官方', l)
    if not any(l.startswith('参考答案来源:') for l in lines):
        idx = next((i for i,l in enumerate(lines) if l.startswith('校验状态:')), len(lines)-1)
        lines.insert(idx, '参考答案来源: "华图网校 2019联考西藏申论（第%d题）"' % int(plan['question']))
    if not any(l.strip() == '来源清单:' for l in lines):
        idx = next((i for i,l in enumerate(lines) if l.startswith('题号口径:')), None)
        if idx is None: idx = len(lines)
        entry = ['来源清单:',
                 '  - 来源方: "原始来源（slb/shenlunhome）"',
                 '    定位: "shenlunhome.com tid=651"',
                 '    用途: "题面与材料"',
                 '  - 来源方: "华图网校"',
                 '    定位: "%s"' % plan['source_url'],
                 '    用途: "第%d题参考答案与评分标准"' % int(plan['question']),
                 '    核验: "2019联考西藏申论同卷；非官方；材料编号差异见正文"']
        lines[idx:idx] = entry
    front_new = '\n'.join(lines)
    new_paper = new_paper[:fs] + front_new + new_paper[fe:]
    # only target block + frontmatter may change
    old_body = paper[fm_bounds(paper)[1]+4:]
    new_body = new_paper[fm_bounds(new_paper)[1]+4:]
    def blocks_map(body):
        mm = list(QRE.finditer(body)); out = {}
        for i,x in enumerate(mm):
            e = mm[i+1].start() if i+1 < len(mm) else len(body)
            out[int(x.group(1))] = norm(body[x.start():e])
        return out
    ob, nb = blocks_map(old_body), blocks_map(new_body)
    if set(ob) != set(nb): raise ValueError('question set changed')
    for q in ob:
        if q != int(plan['question']) and ob[q] != nb[q]: raise ValueError('non-target question changed q%d' % q)
    after = new_paper.encode('utf-8')
    report = {'target': str(target.relative_to(root)), 'question': int(plan['question']),
              'before_sha256': sha(before), 'after_sha256': sha(after), 'written': False,
              'source_url': plan['source_url'], 'source_sha256': plan['source_sha256']}
    if args.write:
        if not args.expect_after: raise SystemExit('--write requires --expect-after')
        if args.expect_after != report['after_sha256']: raise SystemExit('expect-after mismatch')
        if target.read_bytes() != before: raise SystemExit('target changed during run')
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix='.essay-answer-', suffix='.tmp')
        with os.fdopen(fd, 'wb') as f:
            f.write(after); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, target)
        report['written'] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
