#!/usr/bin/env python3
"""Find demonstrably identical remaining tasks; never create new answer prose.
A candidate is valid only with identical normalized question, genre, score and
word limit plus near-exact full material containment. It is a proposal, not a
claimed completed answer. Source-limited drafts are deliberately excluded.
"""
from __future__ import annotations
import collections,hashlib,json,re
from pathlib import Path
import r7_delivery as layout
import round5_bulk as b
import round4_gap_repair as g
from r9_check_authored import ROOT,read_drafts

def normalized_question(q):
    # Existing parser removes only numbering, material references and punctuation.
    return b.qkey(q)

def run():
    tasks,drafts,issues,unparsed=read_drafts()
    if issues:raise ValueError('Correct draft defects before considering reuse')
    cache={}
    def doc(path):
        if path not in cache:
            text=(ROOT/path).read_text(encoding='utf-8')
            cache[path]=layout.parse(text,path)
        return cache[path]
    candidates=collections.defaultdict(list)
    sources=[]
    for key,d in drafts.items():
        if d.get('source_limit'):continue
        t=d['task'];p=doc(t['path']);n=t['number'];question=p['questions'][n]
        if g.digest(question)!=t['question_sha256']:raise ValueError('Source question changed '+key)
        content=b.norm(layout.strip_guide(p['materials'][n]))
        if len(content)<800:continue
        grams={content[i:i+32] for i in range(0,len(content)-31,16)}
        sources.append((key,t,d,normalized_question(question),grams))
    for key,t in tasks.items():
        if key in drafts:continue
        p=doc(t['path']);n=t['number'];question=p['questions'][n]
        if g.digest(question)!=t['question_sha256']:raise ValueError('Target question changed '+key)
        q=normalized_question(question);year=p['identity'][1]
        material=b.norm(layout.strip_guide(p['materials'][n]))
        for sid,st,d,source_q,grams in sources:
            sp=doc(st['path'])
            if year!=sp['identity'][1] or t['kind']!=st['kind'] or t['word_range']!=st['word_range']:continue
            if len(q)<18 or q!=source_q:continue
            if g.SCORE.findall(question.split('要求')[0])!=g.SCORE.findall(sp['questions'][st['number']].split('要求')[0]):continue
            hit=sum(segment in material for segment in grams)
            coverage=hit/len(grams)
            if len(grams)<25 or coverage<0.985:continue
            candidates[key].append({'target':key,'source':sid,'path':t['path'],'number':n,
                'source_path':st['path'],'source_number':st['number'],'material_coverage':round(coverage,8),
                'material_samples':len(grams),'material_hits':hit,'question_sha256':t['question_sha256'],
                'source_question_sha256':st['question_sha256'],'answer_sha256':d['answer_sha256']})
    chosen=[]
    for key,options in sorted(candidates.items()):
        options.sort(key=lambda x:(-x['material_coverage'],x['source']))
        chosen.append(options[0])
    print('R9_REUSE_CANDIDATES '+json.dumps({'candidates':len(chosen),'authored':len(drafts),
         'all_pending':len(tasks),'entries':chosen},ensure_ascii=False),flush=True)
    out=ROOT/'reports/r9-reuse-candidates.json'
    out.write_text(json.dumps({'status':'candidate_only','entries':chosen},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':run()
