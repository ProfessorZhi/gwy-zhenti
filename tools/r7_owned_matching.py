#!/usr/bin/env python3
"""Match copied user-owned source candidates; never treat a candidate as a delivery."""
import base64,collections,hashlib,json,lzma,re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
import round4_gap_repair as g
from round4_delivery import is_missing
import r7_reference_matching as m
from r7_reference_audit import assess,main_answer
ROOT=m.ROOT
SOURCE_REPO='ProfessorZhi/gwy-material-ops';SOURCE_REV='710cb9f85b9ae5e4167cbdd5172c59309a51c80e'
PART_SHA={0:'065c7cfa87668e4737b54fa7f053c70af375c5e6abc3dd0fe513fadfa8edc955',1:'521737abcaca2afa9b7dea30dce0b27d1978ffd9acc147a5e537a93c384391a1',2:'f0f5c79a35c96a7f51e8de2d2cd528755cf8da4a818d2659b47f17b9a5b290fc',3:'d82e830bae5dd861499dcb38d39d51b0a48c7b9aa089accefd16067f00ec7912',4:'2e7b256ed8e4cabdeb86fcdce1084aeb3537ad63ffa31f3f85e5a41c5696daaa',5:'e1bf9aa9183631cf567fe4d8003984eda6bb309c9fd7850c6335ab388faad9eb',6:'9c475866144a2a6258f7155e764150ad67afa44eae2a63f8a4cd4a3b83df8f52',7:'1196807d4832da2d11e8830c22acbb7382d5e573ca8c26ce00b61f97a4e1a02d',8:'13376b454c7d9781bd521adf01410c574e0c1236611f820ab435d75af356eec0',9:'b7a504a312666a97cfce520125e5821c75c2724da75bb863849981b06a39d1e8',10:'bdd469ab010ded71ba4ae2fa27365011968bf99e82c10218d3dec4e790396f68',11:'5b969cfcdabbef995e34767301fb49b746954de815f0167e16f277dd3f6048ea',12:'e3ae59807be8ae482c5f6851f75cab163c007bd5eab72083c70c0cfbbd3843a4',13:'449c2760ad789b022ee20cca341af07c0aa6712de17b6f679062cf537486773a',14:'6737203dbcf4e4b08057aa418f5b19e88de057456f5d209d112163150034d6fb'}

def load():
 out=[];seen=set()
 for p in sorted((ROOT/'tools/data/r7-owned').glob('part-*.json')):
  data=p.read_bytes();obj=json.loads(data);i=obj['index']
  if i not in PART_SHA or i in seen or g.digest(data)!=PART_SHA[i]:raise ValueError('Source part failed immutable checksum: '+p.name)
  seen.add(i)
  if obj['encoding']!='utf-16le' or obj['compression']!='xz':raise ValueError('Invalid data codec')
  dec=lzma.LZMADecompressor();raw=dec.decompress(base64.b64decode(obj['data'],validate=True),max_length=2000001)
  if len(raw)>2000000 or not dec.eof or g.digest(raw)!=obj['raw_sha256']:raise ValueError('Source decompression/hash failed')
  rows=json.loads(raw.decode('utf-16le'))
  if len(rows)!=obj['records']:raise ValueError('Source item count mismatch')
  for j,r in enumerate(rows):
   if g.digest(r['answer'])!=r['answer_sha256']:raise ValueError('Source answer changed')
   r['_part']=i;r['_row']=j;out.append(r)
 return out,sorted(seen)
MAT={}
def material_samples(text):
 plain=m.plain(text);h=g.digest(plain)
 if h not in MAT:MAT[h]={hashlib.sha256(plain[i:i+24].encode()).hexdigest()[:16] for i in range(max(0,len(plain)-23))}
 return MAT[h]
def match(papers,plans):
 rows,parts=load();byyear=collections.defaultdict(list)
 for r in rows:byyear[str(r['source']['year'])].append((m.qkey(r['question']),r))
 chosen={t['path']:(t,list(aa)) for t,aa in plans};reasons=collections.Counter();proposals=0
 for t in papers:
  fixed={a['number'] for a in chosen.get(t['path'],(None,[]))[1]}
  for n,q in t['questions'].items():
   if n in fixed or assess(q,t['answers'].get(n,''))['status']=='已收录':continue
   key=m.qkey(q);rank=[];why='no_source_question'
   for source_key,r in byyear[t['identity'][1]]:
    s=r['source'];same=s['area']==t['identity'][0]
    sim=1. if key==source_key else (SequenceMatcher(None,key,source_key,autojunk=False).ratio() if same else 0.)
    if len(key)<22 or sim<.97:continue
    why='insufficient_source_material'
    hashes=s['material_sample_hashes'];hits=sum(h in material_samples(t['materials'][n]) for h in hashes)
    if len(hashes)<24 or hits<max(24,int(len(hashes)*(.65 if same else .9))):continue
    why='source_answer_incomplete_or_wrong_limit'
    if not m.limits_ok(q,r['question']) or not m.source_usable(q,r['answer']):continue
    rank.append((sim,hits,same,r))
   if not rank:reasons[why]+=1;continue
   rank.sort(key=lambda x:(x[0],x[1],x[2],min(x[3]['answer_characters'],1500)),reverse=True)
   sim,hits,same,r=rank[0];s=r['source'];answer=main_answer(r['answer'])
   a={'number':n,'answer':answer,'kind':'owned_reference','source_repository':SOURCE_REPO,
      'source_revision':SOURCE_REV,'source_path':s['path'],'source_title':s['title'],
      'source_file_sha256':s['sha256'],'source_blob':s['blob'],'source_question':r['question'],
      'source_answer_sha256':r['answer_sha256'],'answer_sha256':g.digest(answer),'answer_length':len(answer),
      'source_part':r['_part'],'source_row':r['_row'],'target_question_sha256':g.digest(q),
      'stem_similarity':sim,'matching_material_samples':hits,'material_samples_total':len(s['material_sample_hashes']),
      'cross_province':not same,'alternative_versions':len(rank),'was_missing':is_missing(t['answers'].get(n,'')),
      'source_url':'https://github.com/'+SOURCE_REPO+'/blob/'+SOURCE_REV+'/'+quote(s['path'],safe='/')}
   chosen.setdefault(t['path'],(t,[]))[1].append(a);proposals+=1
 return list(chosen.values()),{'parts_read':parts,'source_candidates':len(rows),'matched_answers':proposals,'remaining_diagnosis':reasons}
def main():
 papers,bad=m.read_all();internal,_,_=m.find_internal(papers);plans,stats=match(papers,internal)
 print('R7_SOURCE_CHECK',json.dumps(stats,ensure_ascii=False),flush=True)
 print('R7_ALL_CANDIDATES',json.dumps({'papers':len(plans),'answer_positions':sum(len(a) for _,a in plans),'new_positions':sum(a['was_missing'] for _,aa in plans for a in aa),'rows':[{'path':t['path'],'n':[a['number'] for a in aa]} for t,aa in plans]},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
