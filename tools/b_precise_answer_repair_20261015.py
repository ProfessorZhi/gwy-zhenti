"""Apply reviewed scoped B repairs with immediate, reversible full-file receipts."""
import collections,hashlib,json,os,re,uuid
from pathlib import Path
import round5_bulk as parser
from full_repair_answers_20261015 import render_answer,validate_answer
ROOT=Path(__file__).resolve().parents[1]
def sha(t):return hashlib.sha256(t if isinstance(t,bytes) else t.encode()).hexdigest()
def main():
 pre=json.loads((ROOT/'reports/FULL-REPAIR-B-PRECISE-PREIMAGES-20261015.json').read_text(encoding='utf-8'));files={r['path']:r for r in pre['files']};entries=json.loads((ROOT/'tools/data/b-precise-repair-answers-20261015.json').read_text(encoding='utf-8'));groups=collections.defaultdict(lambda:collections.defaultdict(list))
 for e in entries:groups[e['path']][e['number']].append(e)
 rp=ROOT/'reports/FULL-REPAIR-B-PRECISE-ANSWERS-20261015.jsonl';summary=[]
 for rel,tasks in groups.items():
  p=ROOT/rel;before=p.read_text(encoding='utf-8');old=files[rel];assert sha(before)==old['before_sha256'],('Concurrent edit',rel);d=parser.parse(before,rel);new=before;metrics=[]
  for n,versions in sorted(tasks.items()):
   whole=d['answers'][n];links=[]
   for label,url in re.findall(r'\[([^\]]+)\]\((https://[^)]+)\)',whole):
    if not any(r['url']==url for r in links):links.append({'title':'修订所据原参考／旧来源记录','url':url})
   parts=[]
   for j,e in enumerate(versions):
    assert parser.qkey(d['questions'][n])==parser.qkey(e['question']);count=validate_answer(d['questions'][n],e)
    if e['attribution_kind']=='ai_revision':
     item={**e,'sources':links[:3]};text=render_answer(item)+'\n\n> 旧稿留存：完整原答文、来源署名及附解析保存在 `reports/FULL-REPAIR-B-PRECISE-ANSWERS-20261015.jsonl`，修订稿不归署原作者。'
    else:
     title=('**参考文章'+('一二三四'[j])+'**\n\n') if len(versions)>1 else ''
     text=title+'**同题来源参考作答（主文整理）**\n\n<!-- full-repair-answer-20261015 -->\n'+e['answer']+'\n<!-- /full-repair-answer-20261015 -->\n\n> 来源说明：原库已有同题完整参考正文，原答文署名以旧来源为准；本次剥离误混的题干、范文点评、封装，并整理断行字形。不是官方答案，未经实考评分。全部旧稿及来源原文留存恢复凭据。'
     if links:text+='\n\n'+'\n\n'.join('['+r['title']+']('+r['url']+')' for r in links[:3])
    parts.append(text);metrics.append({'number':n,'version':j+1,'characters':count,'kind':e['attribution_kind'],'reason':e['reason'],'new_body_sha256':sha(e['answer'])})
   replacement='\n\n'+'\n\n'.join(parts)+'\n\n';pat=re.compile(r'(<summary>第\s*'+str(n)+r'\s*题</summary>)(.*?)(</details>)',re.S);m=pat.search(new);assert m,('Missing answer detail',rel,n);new=new[:m.start(2)]+replacement+new[m.end(2):]
  nd=parser.parse(new,rel);assert nd['questions']==d['questions'],('Question changed',rel)
  for n,a in d['answers'].items():
   if n not in tasks:assert nd['answers'][n]==a,('Unrelated reference changed',rel,n)
  row={'path':rel,'status':'prepared','before_sha256':sha(before),'before_text':before,'after_sha256':sha(new),'after_text':new,'question_sha256':{str(n):sha(q) for n,q in d['questions'].items()},'old_references':{str(n):d['answers'][n] for n in tasks},'new_references':metrics,'materials_untouched':True}
  with rp.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  temp=p.with_name(p.name+'.precise-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(new.encode());os.replace(temp,p);assert sha(p.read_bytes())==row['after_sha256']
  with rp.open('a',encoding='utf-8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':row['after_sha256']},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  summary.append({'path':rel,'tasks':sorted(tasks),'references':metrics});print(rel,sorted(tasks),flush=True)
 out={'status':'passed','files':len(summary),'answer_positions':sum(len(r['tasks']) for r in summary),'main_versions':len(entries),'ai_revised_versions':sum(e['attribution_kind']=='ai_revision' for e in entries),'source_body_cleanup_versions':sum(e['attribution_kind']=='owned_source' for e in entries),'details':summary,'manual_only_not_guessed':pre['manual_only'],'root_owned_exclusions':pre['root_owned_excluded']}
 (ROOT/'reports/FULL-REPAIR-B-PRECISE-ANSWERS-SUMMARY-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('Summary:',{k:v for k,v in out.items() if k not in ['details','manual_only_not_guessed','root_owned_exclusions']})
if __name__=='__main__':main()
