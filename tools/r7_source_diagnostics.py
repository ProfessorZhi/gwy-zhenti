#!/usr/bin/env python3
"""Read-only diagnostic of source-to-target matching; it never approves a repair."""
import json
from difflib import SequenceMatcher
import r7_reference_matching as m
import r7_owned_matching as o
from r7_reference_audit import assess

def main():
 papers,_=m.read_all();rows,_=o.load()
 for r in rows:
  s=r['source'];k=m.qkey(r['question']);rank=[]
  for t in papers:
   if (str(s['area']),str(s['year']))!=t['identity']:continue
   for n,q in t['questions'].items():
    if assess(q,t['answers'].get(n,''))['status']=='已收录':continue
    sim=SequenceMatcher(None,k,m.qkey(q),autojunk=False).ratio()
    rank.append((sim,t,n))
  if not rank:continue
  sim,t,n=max(rank,key=lambda x:x[0]);hits=sum(h in o.material_samples(t['materials'][n]) for h in s['material_sample_hashes'])
  print('SOURCE_MATCH_DIAGNOSTIC',json.dumps({'part':r['_part'],'row':r['_row'],'source':s['title'],'target':t['path'],'n':n,'sim':sim,'material_hits':hits,'source_stem':r['question'].split('要求')[0][:220],'target_stem':t['questions'][n].split('要求')[0][:220],'reference_type':assess(t['questions'][n],r['answer'])},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
