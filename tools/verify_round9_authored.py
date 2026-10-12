#!/usr/bin/env python3
"""Verify delivered R9 prose independently, then reconstruct the immutable R8 corpus."""
from __future__ import annotations
import json,shutil
from pathlib import Path
import round4_gap_repair as g
import r7_delivery as layout
from r7_reference_audit import assess
from round4_delivery import is_missing
from verify_round5_repairs import reverse
from r9_check_authored import ROOT,read_drafts,characters
from r9_apply_authored import RECEIPT,MARKER

def records(root):
    return [json.loads(x) for x in (Path(root)/'reports'/RECEIPT).read_text(encoding='utf-8').splitlines() if x.strip()]

def verify(root):
    root=Path(root).resolve();rs=records(root)
    tasks,drafts,issues,unparsed=read_drafts()
    if issues:raise ValueError('Authored content checks no longer pass')
    paths=set();ids=set();preserved=0;questions=0;warnings=[]
    for r in rs:
        path=r['path'];file=(root/path).resolve()
        if path in paths or not file.is_relative_to(root) or not file.is_file():
            raise ValueError('Unsafe or duplicated delivery path')
        paths.add(path)
        new=file.read_text(encoding='utf-8');old=reverse(new,r)
        before=layout.parse(old,path);after=layout.parse(new,path)
        if g.digest(layout.base_body(old))!=r['body_sha256'] or layout.base_body(old)!=layout.base_body(new):
            raise ValueError('Original task/material content changed '+path)
        if list(before['questions'])!=r['questions_before'] or set(before['questions'])!=set(after['questions']):
            raise ValueError('Question set changed '+path)
        questions+=len(before['questions'])
        altered={a['number']:a for a in r['added_references']}
        for n,answer in before['answers'].items():
            if is_missing(answer):continue
            if g.digest(answer)!=r['preserved_answers'].get(str(n)):
                raise ValueError('Preservation evidence mismatch')
            if n in altered:
                if assess(before['questions'][n],answer)['status']=='已收录':raise ValueError('Previously usable answer was overwritten')
                if not after['answers'][n].endswith(answer):raise ValueError('Prior imperfect answer not preserved')
            elif after['answers'].get(n)!=answer:raise ValueError('Untouched answer changed')
            preserved+=1
        for a in r['added_references']:
            key=a['id'];n=a['number']
            if key in ids or key not in drafts:raise ValueError('Missing/duplicate authored ID')
            ids.add(key);row=drafts[key];task=tasks[key]
            if task['path']!=path or task['number']!=n or g.digest(old)!=task['paper_sha256']:
                raise ValueError('Wrong source paper identity')
            if (g.digest(before['questions'][n])!=task['question_sha256'] or
                a['question_sha256']!=task['question_sha256'] or
                g.digest(before['materials'][n])!=a['material_sha256']):
                raise ValueError('Wrong source task or materials')
            actual=after['answers'].get(n,'')
            if MARKER.findall(actual)!=[(key,row['answer'])] or g.digest(actual)!=a['delivered_block_sha256']:
                raise ValueError('Actual original answer bytes differ')
            if (g.digest(row['answer'])!=a['answer_sha256'] or characters(row['answer'])!=a['characters'] or
                row['authorship'] not in actual or '不具有实际考场得分证明' not in actual):
                raise ValueError('Authorship/length/hash not preserved')
            if row.get('source_limit'):
                if row['source_limit'] not in actual:raise ValueError('Source limitation hidden')
                warnings.append({'id':key,'path':path,'number':n,'source_limit':row['source_limit']})
            if assess(after['questions'][n],actual)['status']!='已收录':
                raise ValueError('Delivered answer is still not readable/full')
    if ids!=set(drafts):raise ValueError('Not all accepted drafts actually delivered')
    return {'status':'passed','modified_papers':len(paths),'actual_original_answer_positions':len(ids),
        'original_question_blocks_preserved':questions,'nonempty_previous_answers_preserved':preserved,
        'frozen_pending_positions':len(tasks),'not_yet_written':len(tasks)-len(ids),
        'source_limitations':warnings,'unparsed_documents':len(unparsed),
        'boundary':'Verified full draft bytes, word limits and source alignment; not an exam score or automatic semantic certification.'}

def snapshot(root,dest):
    root=Path(root).resolve();dest=Path(dest).resolve()
    shutil.copytree(root/'reports',dest/'reports')
    for top in ('国考','省考'):
        if (root/top).is_dir():shutil.copytree(root/top,dest/top)
    for r in records(root):
        file=dest/r['path'];file.write_text(reverse(file.read_text(encoding='utf-8'),r),encoding='utf-8',newline='\n')
    from verify_repair_receipts import RECEIPTS
    names=RECEIPTS+('ROUND4-ANSWERS-20261012.jsonl','ROUND5-ANSWERS-20261012.jsonl',
        'ROUND6-OWNED-ANSWERS-20261013.jsonl','ROUND7-REFERENCES-20261013.jsonl',
        'ROUND8-ORIGINAL-ANSWERS-20261013.jsonl')
    for name in names:
        prior=root/'reports'/name
        if not prior.is_file():continue
        for line in prior.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            rel=json.loads(line)['path'];src=(root/rel).resolve();out=(dest/rel).resolve()
            if not src.is_relative_to(root) or not out.is_relative_to(dest) or not src.is_file():
                raise ValueError('Unsafe/absent older receipt source')
            if not out.exists():out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
    (dest/'reports'/RECEIPT).unlink()
if __name__=='__main__':print(json.dumps(verify(ROOT),ensure_ascii=False))
