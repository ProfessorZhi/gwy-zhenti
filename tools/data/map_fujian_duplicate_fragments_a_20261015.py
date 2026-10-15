import sys,json,hashlib,re,uuid,os
from pathlib import Path
from difflib import SequenceMatcher
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
from paper_integrity_repair import set_fields
pairs=[('省考/福建/2021/申论-县级卷.md','省考/福建/2021/申论-县级.md',3,'https://www.aipta.com/article/1291.html'),('省考/福建/2021/申论-乡镇卷.md','省考/福建/2021/申论-乡镇.md',4,'https://www.aipta.com/article/1292.html'),('省考/福建/2022/申论-县乡卷.md','省考/福建/2022/申论-县乡.md',4,'https://www.aipta.com/article/5385.html')]
sha=lambda t:hashlib.sha256(t.encode()).hexdigest();rows=[];receipts=[]
for frag,canonical,expected,url in pairs:
 fp=R/frag
 if not fp.exists():
  # Root may already have archived a fully established fragment; never recreate it.
  rows.append(dict(fragment=frag,canonical=canonical,status='already_archived_by_root'));continue
 ftext=fp.read_text(encoding='utf8');ctext=(R/canonical).read_text(encoding='utf8');fd=b.parse(ftext,frag);cd=b.parse(ctext,canonical);assert len(cd['questions'])==expected
 tasks=[]
 for n,q in fd['questions'].items():
  nn,sim=max(((nn,SequenceMatcher(None,b.qkey(q),b.qkey(qq),autojunk=False).ratio()) for nn,qq in cd['questions'].items()),key=lambda x:x[1]);assert sim>.98,(frag,n,sim)
  grams=b.shingles(fd['materials'][n]);dest=b.norm(cd['materials'][nn]);coverage=sum(x in dest for x in grams)/max(1,len(grams))
  tasks.append(dict(source_number=n,canonical_number=nn,question_similarity=sim,source_material_12gram_coverage=coverage))
 meta={'实有题数':expected,'对照题本题量':expected,'缺失原题号':[],'题量校核来源':url,'题量校核凭据':'reports/FULL-REPAIR-FUJIAN-DUPLICATE-MAP-A-20261015.json'}
 new=set_fields(ctext,meta,'2026-10-15以同年同卷真实目录及完整父卷全部任务核对题量；保留较好现有题面和作答，不以OCR残段覆盖。')
 if new!=ctext:
  cp=R/canonical;before=ctext;tmp=cp.with_name(cp.name+'.expected-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(new.encode());assert sha(cp.read_text(encoding='utf8'))==sha(before);os.replace(tmp,cp)
  receipts.append(dict(path=canonical,before_sha256=sha(before),before_text=before,after_sha256=sha(new),change='Only confirmed expected count/provenance metadata; all existing materials, tasks and answers preserved'))
 rows.append(dict(fragment=frag,canonical=canonical,fragment_sha256=sha(ftext),canonical_sha256=sha(new),canonical_expected=expected,source_count_url=url,tasks=tasks,unmapped=[],archive_action='root_only; fragment unchanged'))
out=dict(date='2026-10-15',rows=rows,canonical_metadata_updates=receipts,note='完整父卷已有全部原题和答案；片段逐题映射供根统一归档，不重复新造全卷。2021县级MOPS作文OCR较差，未用于覆盖父卷清晰题面。')
(R/'reports/FULL-REPAIR-FUJIAN-DUPLICATE-MAP-A-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps([{k:v for k,v in x.items() if k!='tasks'}|{'tasks':x.get('tasks')} for x in rows],ensure_ascii=False))
# Correct the diagnostic to compare against all pre-existing task-material scopes.
rp=R/'reports/FULL-REPAIR-FUJIAN-FULL-SOURCE-A-20261015.jsonl';records=[]
packets={x['target_path']:x for x in json.loads((R/'tools/data/fujian-full-restore-packets-a-20261015.json').read_text(encoding='utf8'))}
for line in rp.read_text(encoding='utf8').splitlines():
 rec=json.loads(line);before=b.parse(rec['before_text'],rec['path']);pool=''.join(b.norm(x) for x in before['materials'].values());comparison=[]
 for m in packets[rec['path']]['materials']:
  grams=b.shingles(m['text']);comparison.append(dict(number=m.get('number',m['source_label']),source_material_12gram_in_all_existing_task_scopes=sum(x in pool for x in grams)/max(1,len(grams))))
 rec['source_material_comparison_scope']='all before-image task-material scopes; 0 may identify material genuinely absent with the omitted task, not a mismatch judgment';rec['source_material_comparison']=comparison;records.append(rec)
rp.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in records),encoding='utf8')
