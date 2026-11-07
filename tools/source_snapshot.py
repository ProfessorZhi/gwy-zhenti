#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture a source-side question snapshot for source_fill.py anchor validation.

The snapshot binds question numbers to their actual text/options/answers as read
from a public source page (or a text extraction of a public PDF).  It is stored
as JSON and hashed in the reviewed plan, so source_fill.py can verify that an
anchor really belongs to source_q, not merely that its text occurs somewhere in
a hand-written evidence file.

Usage:
  python3 -I tools/source_snapshot.py gkhenti --paper-url URL --answer-url URL --out snap.json
  python3 -I tools/source_snapshot.py gwyeasy --url URL --out snap.json
  python3 -I tools/source_snapshot.py text --file paper.txt --url URL --out snap.json
"""
import argparse, datetime, html, json, re, sys, urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9'})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = r.read()
        try: return data.decode('utf-8')
        except UnicodeDecodeError: return data.decode('gb18030', 'replace')

def strip_tags(s: str) -> str:
    s = re.sub(r'<br\s*/?>', '\n', s)
    s = re.sub(r'</(?:p|div|li|tr|h[1-6])\s*>', '\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).replace('\xa0', ' ').strip()

def clean(s: str) -> str:
    s = re.sub(r'[ \t]+', ' ', strip_tags(s))
    return re.sub(r'\n{3,}', '\n\n', s).strip()

def parse_gkhenti_paper(text: str) -> dict:
    blocks = re.findall(
        r'<div class="col-xs-1 left">\s*(\d+)\s*</div><div class="col-xs-11 right">(.*?)(?=<div class="col-xs-1 left">|$)',
        text, re.S)
    qs = {}
    for num, body in blocks:
        n = int(num)
        if n in qs:
            continue
        # split stem paragraphs from option divs
        opt_matches = list(re.finditer(r'<div class="col-xs-(?:3|6|12)">\s*([A-D])[、\.．]\s*(.*?)</div>', body, re.S))
        stem_body = body[:opt_matches[0].start()] if opt_matches else body
        stem = clean(stem_body)
        opts = {}
        for m in opt_matches:
            k = m.group(1); v = clean(m.group(2))
            if k not in opts: opts[k] = v
        if stem:
            qs[str(n)] = {'number': n, 'stem': stem, 'options': opts, 'answer': None}
    return qs

def parse_gkhenti_answers(text: str) -> dict:
    t = strip_tags(text)
    ans = {}
    for m in re.finditer(r'(?m)^\s*(\d+)\s*[、\.．]\s*([A-D])\s*$', t):
        ans[str(int(m.group(1)))] = m.group(2)
    return ans

def parse_gwyeasy(text: str) -> dict:
    # question paragraphs: <p><strong>95.</strong>stem...</p>
    starts = list(re.finditer(r'<p>\s*<strong>\s*(\d+)\s*[\.．]\s*</strong>', text))
    qs = {}
    for i, m in enumerate(starts):
        n = int(m.group(1))
        end = starts[i+1].start() if i+1 < len(starts) else len(text)
        body = text[m.end():end]
        # options are inline <strong>A.</strong> text, often several per <p>
        opt_matches = list(re.finditer(r'<strong>([A-D])[\.．]</strong>', body))
        stem_body = body[:opt_matches[0].start()] if opt_matches else body
        stem = clean(stem_body)
        opts = {}
        for j, om in enumerate(opt_matches):
            k = om.group(1)
            oend = opt_matches[j+1].start() if j+1 < len(opt_matches) else len(body)
            v = clean(body[om.end():oend])
            if k not in opts: opts[k] = v
        if stem and n not in qs:
            qs[str(n)] = {'number': n, 'stem': stem, 'options': opts, 'answer': None}
    return qs

def parse_text_questions(text: str) -> dict:
    lines = text.splitlines()
    starts = []
    for i, line in enumerate(lines):
        m = re.match(r'^\s*(\d+)\s*[\.．]\s*(.*)$', line)
        if m:
            starts.append((i, int(m.group(1)), m.group(2)))
    qs = {}
    for idx, (i, n, first) in enumerate(starts):
        end = starts[idx+1][0] if idx+1 < len(starts) else len(lines)
        chunk = [first] + lines[i+1:end]
        opts = {}
        stem_lines = []
        for line in chunk:
            # options may be one line with several A./B./C./D. markers
            parts = re.split(r'(?=(?<![A-Za-z])[A-D][\.．]\s*)', line)
            got = False
            for p in parts:
                m = re.match(r'^\s*([A-D])[\.．]\s*(.*)$', p)
                if m:
                    k = m.group(1); v = re.sub(r'\s+', ' ', m.group(2)).strip()
                    if k not in opts: opts[k] = v
                    got = True
            if not got:
                stem_lines.append(line)
        stem = re.sub(r'\s+', ' ', ' '.join(stem_lines)).strip()
        if stem and n not in qs:
            qs[str(n)] = {'number': n, 'stem': stem, 'options': opts, 'answer': None}
    return qs

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='mode', required=True)
    g = sub.add_parser('gkhenti')
    g.add_argument('--paper-url', required=True)
    g.add_argument('--answer-url', required=True)
    g.add_argument('--out', required=True)
    w = sub.add_parser('gwyeasy')
    w.add_argument('--url', required=True)
    w.add_argument('--out', required=True)
    t = sub.add_parser('text')
    t.add_argument('--file', required=True)
    t.add_argument('--url', required=True)
    t.add_argument('--out', required=True)
    a = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    if a.mode == 'gkhenti':
        paper = fetch(a.paper_url)
        answers = parse_gkhenti_answers(fetch(a.answer_url))
        qs = parse_gkhenti_paper(paper)
        for k, v in qs.items():
            v['answer'] = answers.get(k)
        title = re.search(r'<h3 align="center">(.*?)</h3>', paper, re.S)
        snap = {'schema_version': 1, 'capture_method': 'gkhenti_html', 'url': a.paper_url,
                'answer_url': a.answer_url, 'title': clean(title.group(1)) if title else '',
                'captured_at': now, 'question_count': len(qs), 'questions': qs}
    elif a.mode == 'gwyeasy':
        paper = fetch(a.url)
        qs = parse_gwyeasy(paper)
        title = re.search(r'<title>(.*?)</title>', paper, re.S)
        snap = {'schema_version': 1, 'capture_method': 'gwyeasy_html', 'url': a.url,
                'answer_url': '', 'title': clean(title.group(1)) if title else '',
                'captured_at': now, 'question_count': len(qs), 'questions': qs}
    else:
        text = Path(a.file).read_text(encoding='utf-8', errors='replace')
        qs = parse_text_questions(text)
        snap = {'schema_version': 1, 'capture_method': 'pdf_text', 'url': a.url,
                'answer_url': '', 'title': '', 'captured_at': now,
                'question_count': len(qs), 'questions': qs}
    Path(a.out).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'out': a.out, 'questions': len(qs),
                      'numbers': [min(map(int, qs)), max(map(int, qs))] if qs else []}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    sys.exit(main())
