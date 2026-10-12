#!/usr/bin/env python3
"""Verify authored examples, exact source bodies and historical preservation; no fake score claim."""
from __future__ import annotations
import json,shutil
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing
from round7_reference_delivery import ROOT,RECEIPT,draft_entries,content_body,count_chars
from verify_round5_repairs import reverse

def records(root):
    p=Path(root)/'reports'/RECEIPT
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def verify(root):
    root=Path(root).resolve()
    rs=records(root);existing= {(x['path'],x['n']):x for x in draft_entries()}
    paths=set();count=0;preserved=0;questions=0
    if len(rs)!=4:raise ValueError('Unexpected authored file count')
    for r in rs:
        path=r['path'];p=(root/path).resolve()
        if not p.is_relative_to(root) or path in paths or not p.is_file():
            raise ValueError('Unsafe or repeated authored file')
        paths.add(path)
        new=p.read_text(encoding='utf-8');old=reverse(new,r)
        prior=b.parse(old,path);current=b.parse(new,path)
        if g.digest(content_body(old))!=r['before_body_sha256'] or content_body(old)!=content_body(new):
            raise ValueError('Given materials or task text was mutated')
        if len(prior['questions'])!=r['question_count'] or set(prior['questions'])!=set(current['questions']):
            raise ValueError('Task list changed')
        questions+=len(prior['questions'])
        for n,a in prior['answers'].items():
            if not is_missing(a):
                if current['answers'].get(n)!=a:raise ValueError('Overwrote prior reference answer')
                preserved+=1
        for a in r['added_answers']:
            n=a['number'];key=(path,n)
            if key not in existing or not a['model_authored']:
                raise ValueError('Reference text identity/labeling changed')
            e=existing.pop(key)
            if a['chars']!=count_chars(e['answer']) or a['text_sha256']!=g.digest(e['answer']):
                raise ValueError('Draft evidence SHA mismatch')
            if not is_missing(prior['answers'].get(n,'')):
                raise ValueError('Added answer was not missing')
            cur=current['answers'][n]
            if e['answer'].strip() not in cur or g.digest(cur)!=a['delivered_answer_sha256']:
                raise ValueError('Delivered authored answer changed')
            if 'AI辅助编写' not in cur or '未经实考评分' not in cur or e['source'] not in cur:
                raise ValueError('Authorship/score-source disclosure missing')
            count+=1
    if existing or count!=7:raise ValueError('Expected exactly 7 independently authored complete answers')
    return {'status':'passed','modified_papers':len(rs),'answers_added':count,
            'original_question_blocks_preserved':questions,'existing_reference_answers_preserved':preserved,
            'boundary':'AI-assisted independently written study references, NOT scored exam scripts or copied institutional answer texts.'}

def historical_snapshot(root,dest):
    root=Path(root).resolve();dest=Path(dest).resolve()
    shutil.copytree(root/'reports',dest/'reports')
    for top in ('国考','省考'):
        if (root/top).is_dir():shutil.copytree(root/top,dest/top)
    for r in records(root):
        p=dest/r['path']
        p.write_text(reverse(p.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
    from verify_repair_receipts import RECEIPTS
    # Preserve images and other paths named by prior R1-R6 receipts inside the snapshot.
    names=RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl','ROUND5-ANSWERS-20261012.jsonl',
                    'ROUND6-OWNED-ANSWERS-20261013.jsonl')
    for name in names:
        src_receipt=root/'reports'/name
        if not src_receipt.is_file():continue
        for line in src_receipt.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            rel=json.loads(line)['path'];src=(root/rel).resolve();out=(dest/rel).resolve()
            if not src.is_relative_to(root) or not out.is_relative_to(dest) or not src.is_file():
                raise ValueError('Unsafe/absent historical receipt source')
            if not out.exists():
                out.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,out)
    (dest/'reports'/RECEIPT).unlink()

if __name__=='__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False))
