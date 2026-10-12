#!/usr/bin/env python3
"""Write genuinely authored answers into their original exam Markdown.
Before publication this branch may accumulate R9 drafts. Its R9 receipt is
recomputed against the same frozen R8 baseline; published R1-R8 receipts are
never rewritten. Old usable answers are never replaced.
"""
from __future__ import annotations
import argparse,collections,json,re
from pathlib import Path
import round4_gap_repair as g
import r7_delivery as layout
from r7_reference_audit import assess
from round4_delivery import operations,is_missing
from verify_round5_repairs import reverse
from r9_check_authored import ROOT,read_drafts
RECEIPT='ROUND9-AUTHORED-20261013.jsonl'
MARKER=re.compile(r'<!-- R9 authored answer ([A-Z0-9-]+) -->\n([\s\S]*?)\n<!-- /R9 authored answer -->')

def previous_records(root=ROOT):
    file=Path(root)/'reports'/RECEIPT
    if not file.exists():return []
    return [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip()]

def reference(row,previous):
    ident=row['id']
    body='**'+row['authorship']+'**\n\n'
    body+='<!-- R9 authored answer '+ident+' -->\n'+row['answer']+'\n<!-- /R9 authored answer -->\n\n'
    body+='> 来源说明：依据本卷给定材料和本题作答要求独立撰写的学习参考，不是机构原文，不具有实际考场得分证明。'
    if row.get('source_limit'):body+=' **题源限制：'+row['source_limit']+'**'
    if row.get('comparison_source'):
        body+='\n\n[同题说明对照]('+row['comparison_source']+')（不将该页内容冒称本文出处或考试评分依据）。'
    if previous and not is_missing(previous):
        body+='\n\n---\n\n**此前收录版本（完整保留；篇幅或正文问题另有标记）**\n\n'+previous
    return body

def render(old,path,rows):
    doc=layout.parse(old,path)
    if not doc:raise ValueError('Cannot parse original paper '+path)
    byid={r['task']['number']:r for r in rows}
    if len(byid)!=len(rows):raise ValueError('Duplicate original question number')
    for n,r in byid.items():
        t=r['task']
        if (g.digest(old)!=t['paper_sha256'] or n not in doc['questions'] or
            g.digest(doc['questions'][n])!=t['question_sha256']):
            raise ValueError('Original paper/question differs from frozen basis '+r['id'])
        if assess(doc['questions'][n],doc['answers'].get(n,''))['status']=='已收录':
            raise ValueError('Refuse to replace pre-existing complete answer '+r['id'])
    new=layout.strip_guide(old)
    if doc['answer_heading']:
        captured=[]
        def sub(m):
            n=int(m[2])
            if n not in byid:return m[0]
            captured.append(n)
            return m[1]+'\n\n'+reference(byid[n],doc['answers'].get(n,''))+'\n\n'+m[4]
        new=g.DETAIL.sub(sub,new)
        if sorted(captured)!=sorted(byid):raise ValueError('Required answer container absent '+path)
    else:
        if doc['mode']=='unstructured':
            for n,at in sorted(doc['question_spans'].items(),key=lambda x:x[1],reverse=True):
                new=new[:at]+f'\n<!-- R7 question anchor {n} -->\n## 第 {n} 题\n\n'+new[at:]
        parts=['## 答案与解析','> 下列原创学习参考均标明性质；尚未写出同题全文的题目继续留缺。']
        for n in doc['questions']:
            text=reference(byid[n],doc['answers'].get(n,'')) if n in byid else layout.PENDING
            parts.append(f'\n<a id="r7-reference-{n}"></a>\n<details>\n<summary>第 {n} 题</summary>\n\n'+text+'\n\n</details>')
        new=new.rstrip()+'\n\n'+'\n\n'.join(parts)+'\n'
    if layout.base_body(old)!=layout.base_body(new):raise ValueError('Original materials or requirements changed')
    updated=layout.parse(new,path)
    complete=[n for n,q in updated['questions'].items() if assess(q,updated['answers'].get(n,''))['status']=='已收录']
    new=g.set_fields(new,{'已收录参考答案题号':sorted(complete),
        '缺参考答案题号':sorted(set(updated['questions'])-set(complete)),
        '第九轮原创参考题号':sorted(byid),'第九轮原创参考凭据':'reports/'+RECEIPT},
        '2026-10-13：第九轮按本卷材料补入明确署名的原创学习参考；非实考高分认证')
    new=layout.insert_guide(new,updated)
    if layout.base_body(old)!=layout.base_body(new):raise ValueError('Metadata or guide altered original paper')
    actual=layout.parse(new,path)
    if set(doc['questions'])!=set(actual['questions']):raise ValueError('Original question identifiers changed')
    preserved={}
    for n,ans in doc['answers'].items():
        if is_missing(ans):continue
        if n not in byid and actual['answers'].get(n)!=ans:raise ValueError('Old answer changed')
        if n in byid and not actual['answers'][n].endswith(ans):raise ValueError('Old incomplete version lost')
        preserved[str(n)]=g.digest(ans)
    adds=[]
    for n,row in sorted(byid.items()):
        block=actual['answers'].get(n,'');matches=MARKER.findall(block)
        if matches!=[(row['id'],row['answer'])]:raise ValueError('Delivered draft text not exact '+row['id'])
        if assess(actual['questions'][n],block)['status']!='已收录':raise ValueError('Added text not considered full')
        adds.append({'id':row['id'],'number':n,'authorship':row['authorship'],
            'answer_sha256':row['answer_sha256'],'characters':row['characters'],
            'question_sha256':row['task']['question_sha256'],
            'material_sha256':g.digest(doc['materials'][n]),
            'source_limit':row.get('source_limit'),'comparison_source':row.get('comparison_source'),
            'prior_status':row['task']['old_status'],'delivered_block_sha256':g.digest(block)})
    rec={'path':path,'before_sha256':g.digest(old),'after_sha256':g.digest(new),
        'kind':'independently_authored_study_reference','body_sha256':g.digest(layout.base_body(old)),
        'questions_before':list(doc['questions']),'preserved_answers':preserved,
        'added_references':adds,'operations':operations(old,new)}
    return new,rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--require-all',action='store_true');args=ap.parse_args()
    tasks,drafts,issues,unparsed=read_drafts()
    if issues:raise ValueError('Draft checks failed: '+json.dumps(issues,ensure_ascii=False))
    if args.require_all and set(tasks)!=set(drafts):raise ValueError('Still missing authored answers')
    before={r['path']:r for r in previous_records()}
    grouped=collections.defaultdict(list)
    for row in drafts.values():grouped[row['task']['path']].append(row)
    if set(before)-set(grouped):raise ValueError('Prior R9 work disappeared')
    ready=[]
    for path,rows in sorted(grouped.items()):
        file=ROOT/path;current=file.read_text(encoding='utf-8')
        old=reverse(current,before[path]) if path in before else current
        new,receipt=render(old,path,rows)
        ready.append((file,current,new,receipt))
    summary={'status':'validated','apply':args.apply,'authored_reference_positions':len(drafts),
       'modified_essay_files':len(ready),'frozen_pending_positions':len(tasks),
       'remaining_frozen_positions':len(tasks)-len(drafts),'unparsed_documents':len(unparsed),
       'essays':sum(row['task']['kind']=='作文范文' for row in drafts.values()),
       'source_limit_positions':[row['id'] for row in drafts.values() if row.get('source_limit')],
       'boundary':'Full original text actually written; no institution attribution or exam-score claim.'}
    print('R9_APPLY_CHECK '+json.dumps(summary,ensure_ascii=False),flush=True)
    if not args.apply:return
    for file,current,new,rec in ready:
        if file.read_text(encoding='utf-8')!=current:raise ValueError('Concurrent current input changed')
    for file,current,new,rec in ready:
        file.write_text(new,encoding='utf-8',newline='\n')
        if g.digest(file.read_bytes())!=rec['after_sha256']:raise ValueError('Write readback mismatch')
    (ROOT/'reports'/RECEIPT).write_text(''.join(json.dumps(rec,ensure_ascii=False)+'\n' for _,_,_,rec in ready),encoding='utf-8')
    (ROOT/'reports/REPAIR-SUMMARY-20261013-R9.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
