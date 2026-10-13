#!/usr/bin/env python3
"""Find exact task + relevant-material matches in the user's existing corpus.
No similarity-only automatic transfer; no external answer reproduction.
"""
from __future__ import annotations
import collections
import json
import re
import subprocess
from pathlib import Path
import round5_bulk as b
import round4_gap_repair as g
from r7_reference_audit import assess,word_range
from r11_prepare import ROOT,BASE,OUT,clean_material

CN={c:i for i,c in enumerate('一二三四五六七八九十',1)}
def number(s):
    if s.isdigit(): return int(s)
    if s in CN: return CN[s]
    if s.startswith('十'): return 10+CN.get(s[1:],0)
    if '十' in s:
        a,z=s.split('十'); return CN.get(a,0)*10+CN.get(z,0)
    return None

MARK=re.compile(r'(?m)^[ \t\u3000]*(?:#{1,5}[ \t]*)?(?:给定资料|给定材料|材料|资料)[ \t]*([0-9一二三四五六七八九十]+)[ \t]*[：:、.．]?[ \t]*$')
REF=re.compile(r'(?:给定资料|给定材料|材料|资料)[\s“”"\'（(]*([0-9一二三四五六七八九十]+(?:[\s、,，及和与\-—~～至]+[0-9一二三四五六七八九十]+)*)')

def relevant(q,raw):
    s=clean_material(raw)
    ms=list(MARK.finditer(s)); parts={}
    for i,m in enumerate(ms):
        n=number(m[1]); end=ms[i+1].start() if i+1<len(ms) else len(s)
        if n is None or n in parts: return None
        part=s[m.end():end]
        part=re.sub(r'(?m)^\s*(?:作答要求|答题要求)\s*$', '', part)
        parts[n]=b.norm(part)
    refs=[]
    for m in REF.finditer(g.clean_q(q).split('要求')[0]):
        v=m[1].strip()
        rg=re.fullmatch(r'([0-9一二三四五六七八九十]+)\s*[-—~～至]\s*([0-9一二三四五六七八九十]+)',v)
        if rg:
            lo,hi=number(rg[1]),number(rg[2])
            if lo is None or hi is None or not 1<=lo<=hi<=30: return None
            refs.extend(range(lo,hi+1))
        else:
            vals=re.findall(r'[0-9一二三四五六七八九十]+',v)
            refs.extend(number(x) for x in vals)
    if None in refs: return None
    if parts:
        if refs:
            if not set(refs)<=set(parts): return None
            chosen=[parts[n] for n in sorted(set(refs))]
        else: chosen=list(parts.values())
        joined='\0'.join(chosen)
    elif refs:
        # Unnumbered local material is not enough evidence for automatic transfer.
        return None
    else: joined=b.norm(s)
    return joined if len(joined)>=100 else None

def main():
    tasks=json.loads((OUT/'tasks.json').read_text(encoding='utf-8'))
    needed={(t['path'],t['number']):t for t in tasks}
    donors=collections.defaultdict(list); missing=collections.defaultdict(list)
    for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
        rel=p.relative_to(ROOT).as_posix()
        text=subprocess.check_output(['git','show',BASE+':'+rel]).decode('utf-8')
        try: d=b.parse(text,rel)
        except Exception: continue
        if not d: continue
        for n,q in d['questions'].items():
            key=b.qkey(q); mat=relevant(q,d['materials'][n])
            if len(key)<22 or mat is None: continue
            sig=(str(d['identity'][1]),key,word_range(q),g.digest(mat))
            if (rel,n) in needed:
                missing[sig].append(needed[(rel,n)])
            elif assess(q,d['answers'].get(n,''))['status']=='已收录':
                donors[sig].append({'path':rel,'number':n,'answer':d['answers'][n],
                    'source_file_sha256':g.digest(text),'question_sha256':g.digest(q),
                    'answer_sha256':g.digest(d['answers'][n]),'relevant_material_sha256':g.digest(mat),
                    'relevant_material_chars':len(mat)})
    reuse=[]; aliases=[]
    for sig,ts in missing.items():
        pool=donors.get(sig,[])
        if pool:
            # Conflicting substantive versions are left for a writer rather than chosen by vote.
            bodies={b.norm(x['answer']) for x in pool}
            if len(bodies)==1:
                source=sorted(pool,key=lambda x:(x['path'],x['number']))[0]
                for t in ts:
                    reuse.append({'id':t['id'],'path':t['path'],'number':t['number'],
                                  'target_question_sha256':t['question_sha256'],
                                  'relevant_material_sha256':sig[3], 'donor':source})
                continue
        first=sorted(ts,key=lambda t:t['id'])[0]
        for t in ts:
            if t['id']!=first['id']:
                aliases.append({'id':t['id'],'write_for':first['id'],
                                'relevant_material_sha256':sig[3],
                                'target_question_sha256':t['question_sha256']})
    reused={x['id'] for x in reuse}; aliased={x['id'] for x in aliases}
    remaining=[t for t in tasks if t['id'] not in reused|aliased]
    report={'baseline':BASE,'reuse_positions':len(reuse),'alias_positions':len(aliases),
            'independent_tasks_to_write':len(remaining),'boundary':'Exact task key, word limit, year and complete explicitly relevant material required; no near-match transfer.'}
    (OUT/'reuse.json').write_text(json.dumps(reuse,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'aliases.json').write_text(json.dumps(aliases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'to-write.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# R11 精确局部材料匹配','',json.dumps(report,ensure_ascii=False),'',
           '## 已有本库答案可复用','']
    lines.extend(x['id']+' <- '+x['donor']['path']+'#'+str(x['donor']['number']) for x in reuse)
    lines+=['','## 缺项间同题同材料映射','']
    lines.extend(x['id']+' = '+x['write_for'] for x in aliases)
    lines+=['','## 仍需独立编写','']
    for uid,ts in __import__('itertools').groupby(remaining,key=lambda t:t['unit']):
        ts=list(ts);lines.append(uid+' '+ts[0]['path']+' '+','.join(t['id'] for t in ts))
    (OUT/'MATCHES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('R11_EXACT_REUSE '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
