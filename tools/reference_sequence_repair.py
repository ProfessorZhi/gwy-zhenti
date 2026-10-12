#!/usr/bin/env python3
"""Apply an explicit, hash-pinned question/answer/material identity plan.

No inferred renumbering and no guessed original questions. A third-party order
is identified as such; successful reconstruction is not official certification.
Old question, option, answer and material bodies must survive byte-for-byte after
block-edge whitespace. Missing original numbers remain missing.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re
from pathlib import Path
from paper_integrity_repair import split_paper, set_fields
from cloud_quality import image_refs

PLACEHOLDER = re.compile(r'正在.{0,15}征集|全力以赴征集|正确答案.{0,12}默认|本题暂缺|题目暂缺|题目缺失|暂无题目|未回忆|未收集')
def sha(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def validate_plan(old: dict, spec: dict) -> tuple[dict, dict]:
    mp={int(k):int(v) for k,v in spec['old_to_source'].items()}
    if set(mp)!=set(old['qs']) or len(set(mp.values()))!=len(mp):
        raise ValueError('Old questions require a complete bijective identity map')
    expected=set(range(1,spec['expected_questions']+1))
    if not set(mp.values())<=expected:raise ValueError('Mapped number outside reference')
    additions={int(a['number']):a for a in spec['additions']}
    if len(additions)!=len(spec['additions']) or set(additions)&set(mp.values()):
        raise ValueError('Duplicate/new question overwrites an old question')
    if not set(additions)<=expected:raise ValueError('Addition outside reference')
    for a in additions.values():
        if PLACEHOLDER.search(a['text']):raise ValueError('Source placeholder is not a question')
        if not a['text'].strip() or not a['answer'].strip():raise ValueError('Empty new question/answer record')
        if not a.get('provenance'):raise ValueError('New question lacks provenance')
    if set(spec['material_map'])!=set(old['materials']):raise ValueError('Material map is incomplete')
    if len(set(spec['material_map'].values()))!=len(spec['material_map']):raise ValueError('Materials would be merged or dropped')
    groupmap={int(k):v for k,v in spec['question_groups'].items()}
    if set(groupmap)!=expected:raise ValueError('Reference material memberships incomplete')
    if any(g and g not in spec['material_map'].values() for n,g in groupmap.items() if n in set(mp.values())|set(additions)):
        raise ValueError('Unresolved material body')
    for group in spec['material_map'].values():
        members=sorted(n for n,g in groupmap.items() if g==group)
        if not members or members!=list(range(min(members),max(members)+1)):
            raise ValueError('Noncontiguous source material group')
    return mp,additions

def reconstruct(original: str, spec: dict) -> tuple[str,dict]:
    if sha(original)!=spec['before_sha256']:raise ValueError('Base file changed; refusing overwrite')
    old=split_paper(original);mp,adds=validate_plan(old,spec)
    groups={int(k):v for k,v in spec['question_groups'].items()}
    matreverse={v:k for k,v in spec['material_map'].items()}
    qs={mp[n]:dict(q) for n,q in old['qs'].items()}
    answers={mp[n]:v for n,v in old['answers'].items()}
    for n,a in adds.items():
        qs[n]=dict(header='## 第 '+str(n)+' 题　<sub>qid '+str(a['qid'])+' · 据同题来源补录</sub>',text=a['text'],material=None)
        answers[n]=a['answer']
    missing=sorted(set(range(1,spec['expected_questions']+1))-set(qs))
    fields={'题号口径':'固定版本同题ID对照顺序（回忆题本，保留缺号）','对照题本题量':spec['expected_questions'],'实有题数':len(qs),'缺失原题号':missing,'题序证据':'reports/REFERENCE-SEQUENCE-20261012.jsonl','题序对照来源':spec['source']['url'],'整卷核验状态':('仍缺题，保留来源缺号' if missing else '题目ID与参考题序对照；非官方原卷逐字验真'),'新增答案性质':sorted({a.get('answer_kind','来源参考答案') for a in adds.values()})}
    clean_prefix=re.sub(r'\n> \*\*当前实有 [^\n]*\n> 顺序依据为同题题库的固定回忆版本[^\n]*\n', '\n', old['prefix'])
    prefix=set_fields(clean_prefix,fields,'2026-10-12 按固定版本逐题ID映射恢复顺序，答案及材料联动；既有正文逐块保留。')
    prefix=re.sub(r'(>\s*行测\s*·\s*)\d+(\s*题)',lambda m:m[1]+str(len(qs))+m[2],prefix,count=1)
    # Older per-round notes remain history, while this immediately visible summary is current.
    prefix+='\n> **当前实有 '+str(len(qs))+' / 参考题本 '+str(spec['expected_questions'])+' 题**。'+('仍缺原题号：'+ '、'.join(map(str,missing))+'。' if missing else '本次对应题目ID无缺号。')+'\n> 顺序依据为同题题库的固定回忆版本，不等于官方印刷原卷逐字认证；既有题干、选项、材料和解析不作静默改写。新增校算答案与来源答案分别标明。\n\n'
    chunks=[prefix.rstrip()];emitted=set()
    for n,q in sorted(qs.items()):
        group=groups[n]
        if group and group not in emitted:
            members=sorted(i for i in qs if groups[i]==group)
            chunks+=['## 材料 '+str(len(emitted)+1)+'（第'+str(min(members))+'—'+str(max(members))+'题共用）',old['materials'][matreverse[group]]['text']]
            emitted.add(group)
        h=re.sub(r'^#{2,3} 第 \d+ 题',('###' if group else '##')+' 第 '+str(n)+' 题',q['header'])
        chunks.extend([h,q['text']])
    chunks.append('## 答案与解析')
    for n,a in sorted(answers.items()):chunks.append('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+a+'\n\n</details>')
    result='\n\n'.join(chunks).rstrip()+'\n';check=split_paper(result)
    for n,q in old['qs'].items():
        if check['qs'][mp[n]]['text']!=q['text'] or check['answers'][mp[n]]!=old['answers'][n]:raise AssertionError('Existing question/answer body changed')
    if collections.Counter(x['text'] for x in check['materials'].values())!=collections.Counter(x['text'] for x in old['materials'].values()):raise AssertionError('Material body changed or dropped')
    if collections.Counter(image_refs(original))-collections.Counter(image_refs(result)):raise AssertionError('Existing image reference dropped')
    if set(check['qs'])!=set(check['answers']) or len(check['qs'])!=len(old['qs'])+len(adds):raise AssertionError('Output identity mismatch')
    report={k:v for k,v in spec.items() if k!='additions'}
    report.update(after_sha256=sha(result),old_count=len(old['qs']),current_count=len(qs),missing_original_numbers=missing,preserved_question_bodies=len(old['qs']),preserved_answer_bodies=len(old['answers']),preserved_material_bodies=len(old['materials']),additions=[dict(number=n,qid=a['qid'],question_sha256=sha(a['text']),answer_sha256=sha(a['answer']),answer_kind=a.get('answer_kind'),provenance=a['provenance']) for n,a in sorted(adds.items())],boundary='Reference-source identity/order audit; not independent official original-paper certification. Existing answer correctness is not certified by byte preservation.')
    return result,report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--apply',action='store_true');args=ap.parse_args()
    root=args.root.resolve();plan=json.loads(args.plan.read_text(encoding='utf-8'));candidates={};reports=[]
    for spec in plan:
        p=(root/spec['path']).resolve()
        if not p.is_relative_to(root) or not (spec['path'].startswith('国考/') or spec['path'].startswith('省考/')) or p.suffix!='.md':raise ValueError('Unsafe paper path')
        if spec['path'] in candidates:raise ValueError('Repeated destination')
        text,report=reconstruct(p.read_text(encoding='utf-8'),spec);candidates[spec['path']]=text;reports.append(report)
    if args.apply:
        for spec in plan:
            if sha((root/spec['path']).read_text(encoding='utf-8'))!=spec['before_sha256']:raise ValueError('Concurrent edit before write')
        for p,t in candidates.items():(root/p).write_text(t,encoding='utf-8',newline='\n')
        (root/'reports/REFERENCE-SEQUENCE-20261012.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in reports),encoding='utf-8')
    print(json.dumps(dict(applied=args.apply,papers=len(reports),new_questions=sum(len(r['additions']) for r in reports),preserved_questions=sum(r['old_count'] for r in reports),remaining_missing=sum(len(r['missing_original_numbers']) for r in reports)),ensure_ascii=False))
if __name__=='__main__':main()
