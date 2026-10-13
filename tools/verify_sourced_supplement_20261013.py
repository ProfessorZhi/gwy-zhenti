#!/usr/bin/env python3
"""Verify sourced supplement and restore its exact preimage for historical gates."""
from __future__ import annotations
import hashlib, json, shutil, tempfile
from pathlib import Path
from unittest.mock import patch
import round5_bulk as parser
from round4_delivery import is_missing
from r7_reference_audit import audit, assess
from source_supplement_20261013 import cleaned, norm, exam_body, formatted, source_packet

ROOT=Path(__file__).resolve().parents[1]
RECEIPT='SOURCED-SUPPLEMENT-20261013.jsonl'
FULL='SOURCED-SUPPLEMENT-FULL-20261013.json'
SUMMARY='SOURCED-SUPPLEMENT-20261013.json'
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def records(root):
    return [json.loads(s) for s in (root/'reports'/RECEIPT).read_text(encoding='utf-8').splitlines() if s.strip()]
def reverse(text,row):
    if sha(text)!=row['after_sha256']:raise ValueError('Supplement after hash changed: '+row['path'])
    for op in sorted(row['operations'],key=lambda x:x['new_start'],reverse=True):
        a,b=op['new_start'],op['new_end']
        if text[a:b]!=op['new']:raise ValueError('Changed supplement operation')
        text=text[:a]+op['old']+text[b:]
    if sha(text)!=row['before_sha256']:raise ValueError('Supplement preimage restoration failed')
    return text
def historical_snapshot(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    shutil.copytree(root/'reports',destination/'reports')
    for top in ('国考','省考'):
        shutil.copytree(root/top,destination/top)
    for r in records(root):
        p=destination/r['path'];p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
    from verify_repair_receipts import RECEIPTS
    for name in RECEIPTS:
        f=root/'reports'/name
        if not f.exists():continue
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            rel=json.loads(line)['path'];src=(root/rel).resolve();dst=(destination/rel).resolve()
            if not src.is_relative_to(root) or not dst.is_relative_to(destination):raise ValueError('Unsafe receipt path')
            if not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    (destination/'reports'/RECEIPT).unlink()
def verify(root):
    root=Path(root).resolve();rows=records(root)
    full=json.loads((root/'reports'/FULL).read_text(encoding='utf-8'))
    summary=json.loads((root/'reports'/SUMMARY).read_text(encoding='utf-8'))
    sources=source_packet();pending={(a['path'],a['number']):a for a in full};seen=set()
    if len(pending)!=len(full) or summary['new_AI_answers']!=0:raise ValueError('Invalid or authored supplement')
    total=0;old_answers=0
    for r in rows:
        rel=r['path'];p=(root/rel).resolve()
        if rel in seen or not p.is_relative_to(root) or '/申论-' not in rel:raise ValueError('Invalid supplement target')
        seen.add(rel);text=p.read_text(encoding='utf-8');old=reverse(text,r)
        if sha(exam_body(old))!=r['exam_body_sha256'] or exam_body(old)!=exam_body(text):raise ValueError('Changed exam material/task body')
        before=parser.parse(old,rel);after=parser.parse(text,rel)
        if before['questions']!=after['questions']:raise ValueError('Changed task')
        for n,a in before['answers'].items():
            if not is_missing(a):
                if after['answers'].get(n)!=a:raise ValueError('Existing answer overwritten')
                old_answers+=1
        for n in r['added_numbers']:
            e=pending.pop((rel,n));src=sources[e['full_source_path']]
            if src['blob']!=e['source_blob'] or sha(src['text'])!=e['source_sha256']:raise ValueError('Source content changed')
            if sha(e['answer'])!=e['answer_sha256'] or norm(e['answer']) not in norm(cleaned(src['text'])):raise ValueError('Untraceable answer text')
            if not is_missing(before['answers'].get(n,'')):raise ValueError('Filled an existing answer')
            if parser.qkey(before['questions'][n])!=parser.qkey(e['question']):raise ValueError('Wrong task mapping')
            answer=after['answers'].get(n,'')
            if formatted(e) not in answer or e['original_author'] not in answer or src['revision'] not in answer:raise ValueError('Lost source text or authorship')
            if assess(after['questions'][n],answer)['status']!='已收录':raise ValueError('Unreadable reference')
            total+=1
    if pending or total!=summary['source_answer_positions_added'] or len(rows)!=summary['papers_modified']:raise ValueError('Delivery count mismatch')
    current,bad,_,counts=audit()
    actual=sum(v for k,v in counts.items() if k.endswith('/待补'))
    if len(current)!=729 or len(bad)!=9 or actual!=summary['known_missing_answers_after']:raise ValueError('Current corpus count mismatch')
    with tempfile.TemporaryDirectory(prefix='gwy-source-before-') as tmp:
        historical_snapshot(root,Path(tmp))
        with patch('r7_reference_audit.ROOT',Path(tmp)):
            baseline,oldbad,_,oldcounts=audit()
        oldmissing=sum(v for k,v in oldcounts.items() if k.endswith('/待补'))
    if oldmissing!=568 or oldmissing-actual!=total or len(oldbad)!=9:raise ValueError('Historical corpus count mismatch')
    return {'status':'passed','source_reference_positions':total,'papers_modified':len(rows),
            'preserved_existing_answers':old_answers,'known_missing_answers_after':actual,
            'source_authorship':'Existing source answers only; original authors remain as stated',
            'material_preservation':'All original materials/tasks and previous answers retained; exact preimage restoration verified'}
if __name__=='__main__':print(json.dumps(verify(ROOT),ensure_ascii=False))
