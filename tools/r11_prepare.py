#!/usr/bin/env python3
"""Prepare immutable R11 writing requests. No text generation and no corpus mutation."""
from __future__ import annotations
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path
import round5_bulk as b
import round4_gap_repair as g
import r7_delivery as r7
from r7_reference_audit import assess, task_type, word_range

ROOT = Path(__file__).resolve().parents[1]
BASE = 'f0649b5c134a78bc9c5ffb38c6a8b719c369f268'
OUT = ROOT / 'reports/r11-work'

def clean_material(s):
    s = r7.strip_guide(s)
    s = re.sub(r'\A---\n[\s\S]*?\n---\n', '', s)
    s = re.sub(r'(?m)^# [^\n]*\n|^>\s*申论\s*·[^\n]*\n', '', s)
    return s.strip()

def signature(q, material, year):
    q = re.sub(r'^\s*(?:问题|题目|第)?[一二三四五六七八九十0-9]+(?:题)?[：:、.．]\s*', '', g.clean_q(q))
    # Keep material numbers and word limits: same topic is not the same task.
    return g.digest(str(year) + '\0' + b.norm(q) + '\0' + b.norm(clean_material(material)))

def main():
    papers=[]; bad=[]; expected=[]; aliases={}; units=[]
    for p in sorted([*ROOT.glob('国考/*/申论*.md'), *ROOT.glob('省考/*/*/申论*.md')]):
        rel=p.relative_to(ROOT).as_posix()
        old=subprocess.check_output(['git','show',BASE+':'+rel]).decode('utf-8')
        try:
            d=b.parse(old,rel)
            if not d: raise ValueError('Not an essay')
        except Exception as exc:
            bad.append({'path':rel,'reason':str(exc)})
            continue
        papers.append(d)
        ns=[n for n,q in d['questions'].items() if assess(q,d['answers'].get(n,''))['status']=='待补']
        if not ns: continue
        uid=f'{len(units)+1:03d}'
        tasks=[]
        for n in ns:
            q=d['questions'][n]; key=signature(q,d['materials'][n],d['identity'][1])
            target=f'{uid}-{n}'
            first=aliases.setdefault(key,target)
            t={'id':target,'unit':uid,'path':rel,'number':n,'question':q,
               'question_sha256':g.digest(q),'signature':key,'write_for':first,
               'kind':task_type(q),'word_range':list(word_range(q))}
            expected.append(t);tasks.append(t)
        mats=[]; hashes=set()
        for n in ns:
            material=clean_material(d['materials'][n]); h=g.digest(material)
            if h not in hashes:
                hashes.add(h);mats.append(material)
        unit={'unit':uid,'path':rel,'baseline_sha256':g.digest(old),
              'identity':list(d['identity']),'variant':d['variant'],
              'missing_numbers':ns,'tasks':tasks,'materials':mats,
              'source_metadata':g.field(old,'来源明细')}
        units.append(unit)
    if len(papers)!=729 or len(bad)!=9 or len(expected)!=568:
        raise ValueError('Unexpected R10 baseline '+str((len(papers),len(bad),len(expected))))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'inputs').mkdir(exist_ok=True)
    for u in units:
        text=['# R11 写作单元 '+u['unit'],'',u['path'],'',
              '原始来源说明：'+str(u['source_metadata']),'',
              '## 本单元作答任务','']
        for t in u['tasks']:
            text += ['### '+t['id']+'（'+t['kind']+'；同题首个位置 '+t['write_for']+'）','',t['question'],'']
        for i,material in enumerate(u['materials'],1):
            text += ['## 原材料区 '+str(i),'',material,'']
        (OUT/'inputs'/('unit-'+u['unit']+'.md')).write_text('\n'.join(text),encoding='utf-8')
    (OUT/'tasks.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'units.json').write_text(json.dumps([{k:v for k,v in u.items() if k not in ('materials','tasks')} for u in units],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    c=collections.Counter(t['kind'] for t in expected)
    summary={'baseline':BASE,'papers':len(units),'answer_positions':len(expected),
             'unique_exact_tasks':len(aliases),'duplicate_positions':len(expected)-len(aliases),
             'kinds':dict(c),'unparsed':bad}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# R11 全量写作索引','',json.dumps(summary,ensure_ascii=False),'',
           '| 单元 | 试卷 | 待补题号 | 首写/同题映射 |','|---|---|---|---|']
    for u in units:
        lines.append('| '+u['unit']+' | '+u['path']+' | '+','.join(map(str,u['missing_numbers']))+' | '+', '.join(t['id']+('='+t['write_for'] if t['id']!=t['write_for'] else '') for t in u['tasks'])+' |')
    (OUT/'INDEX.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('R11_PREPARED '+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
