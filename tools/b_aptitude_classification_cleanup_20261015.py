"""Repair reviewed display-only type tags and judgment empty-array envelopes."""
from pathlib import Path
import collections,hashlib,json,os,re,uuid
import cloud_quality as c
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b if isinstance(b,bytes) else b.encode()).hexdigest()
def main():
 scan=json.loads((ROOT/'reports/FULL-REPAIR-B-APTITUDE-CONTENT-SECOND-20261015.json').read_text(encoding='utf8'));plans=collections.defaultdict(list)
 for x in scan['candidates']:
  if x['rule']=='graph_type_no_local_image':plans[x['path']].append({'number':x['number'],'kind':'incorrect_graph_type'})
 for year,nums in [(2024,[1,2,6,7,8]),(2025,[1,2,3,4]),(2026,[1,2,3,4])]:
  for n in nums:plans[f'省考/广东/{year}/行测-统考.md'].append({'number':n,'kind':'judgment_empty_array'})
 assert sum(x['kind']=='incorrect_graph_type' for xs in plans.values() for x in xs)==20
 rp=ROOT/'reports/FULL-REPAIR-B-APTITUDE-DISPLAY-TYPES-20261015.jsonl';summary=[]
 for rel,changes in plans.items():
  file=ROOT/rel;before=file.read_bytes();old=before.decode('utf8');new=old;oldanswers=c.DETAIL.findall(old);evidence=[];allowed=[]
  for x in changes:
   n=x['number'];block=next(b for b in c.QBLOCK.finditer(old) if int(b[1])==n);answer=next(body for k,body in oldanswers if int(k)==n);heading=block[0].split('\n',1)[0]
   if x['kind']=='incorrect_graph_type':
    assert not c.image_refs(block[2]);assert '图形推理' in heading
    if '判断题干词语间逻辑关系' in answer or '正方形：立方体' in block[2]:
     target='类比推理';basis='词项对应关系/种属或交叉关系，参考解析逐项比较词项逻辑关系'
    else:
     target='逻辑判断';basis='题干给出论证/假言陈述并要求支持、削弱、必要前提或推出结论；解析明确论点论据或命题翻译'
     assert re.search(r'论点|翻译题干|肯前|推出|削弱|加强',answer),(rel,n)
    replacement=heading.replace('图形推理',target);assert new.count(heading)==1;new=new.replace(heading,replacement,1);allowed.append((heading,replacement))
    evidence.append({**x,'old_type':'图形推理','new_type':target,'basis':basis,'question_excerpt':block[2][:650],'reference_excerpt':answer[:650]})
   else:
    assert '- （选项）[]' in block[2];assert re.search(r'故(?:表述|题干|该|说法)?(?:正确|错误)|本题为判断|判断题',answer),(rel,n)
    assert not re.search(r'(?m)^- \*\*[ABCD]\*\*',block[2]),(rel,n)
    cleaned=block[2].replace('- （选项）[]','> 题型说明：本题为判断题，请判断上述表述是否正确。',1)
    assert new.count(block[2])==1;new=new.replace(block[2],cleaned,1);allowed.append((block[2],cleaned))
    newhead=heading.replace('</sub>',' · 判断题</sub>');assert new.count(heading)==1;new=new.replace(heading,newhead,1);allowed.append((heading,newhead))
    evidence.append({**x,'basis':'陈述式判断题，无真实选择项；参考解析明确表述正误；不创造ABCD、不改来源答案代码','question_excerpt':block[2][:450],'reference_excerpt':answer[:450]})
  assert c.DETAIL.findall(new)==oldanswers,('Answer altered',rel)
  check=old
  for a,b in allowed:assert check.count(a)==1;check=check.replace(a,b,1)
  assert check==new,('Unexpected textual difference',rel)
  assert c.HEAD_Q.findall(new)==c.HEAD_Q.findall(old)
  row={'path':rel,'status':'prepared','before_text':old,'before_sha256':sha(before),'after_text':new,'after_sha256':sha(new),'changes':evidence,'answers_unchanged':True,'only_reviewed_type_labels_and_empty_array_envelopes_changed':True}
  with rp.open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  assert file.read_bytes()==before,('Concurrent edit',rel)
  temp=file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(new.encode());os.replace(temp,file)
  with rp.open('a',encoding='utf8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':sha(file.read_bytes())},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  summary.extend({'path':rel,**x} for x in evidence);print(rel,[(x['number'],x.get('new_type',x['kind'])) for x in evidence],flush=True)
 out={'status':'passed','files':len(plans),'incorrect_graph_type_fixed':20,'judgment_empty_array_removed':13,'new_questions_or_options_or_answer_keys':0,'details':summary,'boundary':'Read actual stems and source explanations to classify. Text/real options/answers kept byte-for-byte except the specifically identified empty-array display envelope; no figure invented and no unknown sequence certified.'}
 (ROOT/'reports/FULL-REPAIR-B-APTITUDE-DISPLAY-TYPES-SUMMARY-20261015.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode())
if __name__=='__main__':main()
