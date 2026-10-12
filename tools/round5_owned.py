#!/usr/bin/env python3
"""Read checksummed user-owned data packets, not arbitrary executable sources."""
import base64,collections,gzip,hashlib,json,re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
import round5_bulk as b
import round4_gap_repair as g
from round4_delivery import is_missing
PACK=b.ROOT/'tools/data/round5-owned'
SOURCE_REPO='ProfessorZhi/gwy-material-ops'
SOURCE_REV='710cb9f85b9ae5e4167cbdd5172c59309a51c80e'

def load_pack():
 manifest=PACK/'manifest.json'
 if not manifest.exists():return None
 m=json.loads(manifest.read_text());parts=[]
 for i,h in enumerate(m['part_sha256']):
  p=json.loads((PACK/f'part-{i:03}.json').read_text())
  if p['index']!=i or g.digest(p['data'])!=h:raise ValueError('Private source packet corrupted')
  parts.append(p['data'])
 compressed=base64.b64decode(''.join(parts),validate=True)
 if len(compressed)>3000000 or g.digest(compressed)!=m['gzip_sha256']:raise ValueError('Invalid source packet hash/size')
 raw=gzip.decompress(compressed)
 if len(raw)>20000000 or g.digest(raw)!=m['raw_sha256']:raise ValueError('Invalid decompressed source packet')
 data=json.loads(raw)
 if data['source_repository']!=SOURCE_REPO or data['source_revision']!=SOURCE_REV:raise ValueError('Unexpected source repository/revision')
 if len(data['sources'])!=m['source_files'] or len(data['answers'])!=m['answers']:raise ValueError('Source inventory count mismatch')
 return data

def limits(q):
 return (g.SCORE.findall(q.split('要求')[0]),re.findall(r'(\d+)\s*(?:[-—～~]\s*\d+\s*)?字',q))
def evidence(t,n,source,row):
 if str(source['year'])!=t['identity'][1]:return None
 q=re.sub(r'(?m)^\s*#+\s*','',row['question']).replace('**','')
 k=b.qkey(t['questions'][n]);sk=b.qkey(q)
 same=source['area']==t['identity'][0]
 sim=1. if k==sk else SequenceMatcher(None,k,sk,autojunk=False).ratio()
 if len(k)<22 or sim<(.97 if same else 1.):return None
 ts,tw=limits(t['questions'][n]);ss,sw=limits(q)
 if ts and ss and ts!=ss:return None
 if tw and sw and tw!=sw:return None
 samples=[b.norm(s) for s in source['material_samples'] if len(b.norm(s))>=20]
 tm=b.norm(t['materials'][n]);hits=sum(s in tm for s in samples)
 if len(samples)<24 or hits<(max(10,int(len(samples)*.7)) if same else int(len(samples)*.9)):return None
 a=row['answer']
 if g.digest(a)!=row['answer_sha256'] or not g.suitable_answer(a):return None
 if re.search(r'【(?:试题|问题)[一二三四五六七八九十\d]+|\nTB[:：]|javascript:|<script',a,re.I):return None
 return {'stem_similarity':sim,'material_sample_hits':hits,'material_samples_total':len(samples),'cross_province':not same,'source_question':q}

def extend(papers,plans,unresolved):
 data=load_pack()
 if data is None:return plans,unresolved,{'available':False}
 selected={t['path']:(t,list(a)) for t,a in plans};byyear=collections.defaultdict(list)
 for i,row in enumerate(data['answers']):
  source=data['sources'][row['source']]
  byyear[str(source['year'])].append((i,source,row))
 added=0;ambiguous=[]
 for t in papers:
  existing={a['number'] for a in selected.get(t['path'],(None,[]))[1]}
  for n in t['missing']:
   if n in existing:continue
   matches=[]
   for idx,source,row in byyear[t['identity'][1]]:
    proof=evidence(t,n,source,row)
    if proof:matches.append((proof['stem_similarity'],proof['material_sample_hits'],idx,source,row,proof))
   if not matches:continue
   matches.sort(key=lambda x:(x[0],x[1],not x[5]['cross_province']),reverse=True)
   _,_,idx,source,row,proof=matches[0]
   # Different source-published answers are allowed as distinct reference versions;
   # choose one intact version by strongest identity evidence, never splice them.
   a={'number':n,'answer':row['answer'],'kind':'user_owned_transcript','source_url':'https://github.com/'+SOURCE_REPO+'/blob/'+SOURCE_REV+'/'+quote(source['path'],safe='/'),'source_variant':source['title'],'source_repository':SOURCE_REPO,'source_revision':SOURCE_REV,'source_path':source['path'],'source_blob':source['blob'],'source_sha256':source['sha256'],'source_answer_sha256':row['answer_sha256'],'source_packet_row':idx,'target_question_sha256':g.digest(t['questions'][n]),'proof':proof,'alternative_supported_versions':len(matches)}
   selected.setdefault(t['path'],(t,[]))[1].append(a);added+=1
 fixed={(t['path'],a['number']) for t,aa in selected.values() for a in aa}
 left=[x for x in unresolved if (x['path'],x['number']) not in fixed]
 return list(selected.values()),left,{'available':True,'source_files':len(data['sources']),'source_answer_candidates':len(data['answers']),'added_user_source_answers':added}
