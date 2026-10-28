#!/usr/bin/env python3
"""Compact multi-paper reading view."""
import json, os, re, sys
HERE=os.path.dirname(os.path.abspath(__file__))
sample={json.loads(l)['rank']:json.loads(l) for l in open(os.path.join(HERE,'sample.jsonl'),encoding='utf-8')}
rows={json.loads(l)['path']:json.loads(l) for l in open(os.path.join(HERE,'sweep-all.jsonl'),encoding='utf-8')}
ranks=[int(x) for x in sys.argv[1].split(',')]
for rank in ranks:
    s=sample[rank]
    r=rows[s['path']]
    print(f"### {rank} {r['path']} [{s['role']}] {r['area']}/{r['year']}/{r['subject']}/{r['variant']}")
    print(f"  q={r['qcount']} h2={r['h2']} h3={r['h3']} tbl={r['tables']} img={r['images']} $={r['latex_dollars']} ph={r['placeholder_marks']} ansEmpty={r['answers_empty']} multi={r['multi_answers']} noAna={r['no_analysis_marker']} dupJiexi={r['dup_jiexi_label']} hr={r['hr_inside_details']} longest={r['longest_line']} flags={r['flags']} src={r['source_class']} pr140={'same' if r['pr140_same'] else 'DIFF'}")
    print(f"  opts={r['opt_label_hist']}")
    pk=os.path.join(HERE, r['packet'])
    txt=open(pk,encoding='utf-8').read()
    # anomaly rows from question table
    qrows=[l for l in txt.split('\n') if l.startswith('  Q')]
    anomalies=[]
    mode=max(set(x.strip().split()[2].split('=')[1] for x in qrows), key=lambda v: sum(1 for x in qrows if x.strip().split()[2].split('=')[1]==v)) if qrows else ''
    for l in qrows:
        parts=l.split()
        opt=parts[2].split('=')[1]; ans=parts[3].split('=')[1]; ana=parts[4].split('=')[1]
        if opt!=mode or ans=='-' or ana=='N':
            anomalies.append(l.strip())
    if anomalies:
        print("  ANOMALIES:")
        for a in anomalies[:6]: print("   ",a[:110])
    # one excerpt (middle)
    ex=re.search(r"## SAMPLED EXCERPTS.*?\n(--- Q.*?)(?=\n--- Q|\Z)", txt, re.S)
    if ex:
        body=' '.join(ex.group(1).split())
        print("  EX:", body[:330])
