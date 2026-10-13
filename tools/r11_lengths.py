#!/usr/bin/env python3
"""Read-only exact body length check for R11 writer submissions."""
import json,re,sys
from pathlib import Path
from r7_reference_audit import word_range,task_type
ROOT=Path(__file__).resolve().parents[1]

def limits(q):
    lo,hi=word_range(q)
    if not hi: raise ValueError('No explicit word limit')
    if lo!=hi: return lo,hi
    tail=q[-300:]
    if re.search(str(hi)+r'\s*字\s*左右',tail): return int(hi*.9),int(hi*1.1)
    if re.search(r'不少于\s*'+str(hi)+r'\s*字',tail): return hi,hi+300
    # No minimum was imposed for short answers. A substantial body is still required.
    return (max(500,int(hi*.75)) if task_type(q)=='作文范文' else 35),hi

def count(s): return len(re.sub(r'\s|\*','',s))

def main():
    tasks={t['id']:t for t in json.loads((ROOT/'reports/r11-work/tasks.json').read_text(encoding='utf-8'))}
    found={};bad=[]
    for p in sorted((ROOT/'reports/r11-drafts').glob('*.json')):
        entries=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(entries,list): raise ValueError('Draft file is not an array: '+str(p))
        for e in entries:
            k=e['id']
            if k not in tasks or k in found: raise ValueError('Unknown or duplicate task '+k)
            found[k]=e
            if not isinstance(e.get('answer'),str) or not e['answer'].strip(): raise ValueError('Empty answer '+k)
            lo,hi=limits(tasks[k]['question']);n=count(e['answer'])
            if not lo<=n<=hi: bad.append({'id':k,'characters':n,'min':lo,'max':hi,'file':p.name})
    print(json.dumps({'drafts':len(found),'target_positions':len(tasks),'length_failures':bad},ensure_ascii=False,indent=2),flush=True)
    if '--strict' in sys.argv and bad: raise SystemExit(1)

if __name__=='__main__': main()
