"""Pin only independently proved complete task sets, never infer from parser count."""
import hashlib,json,os,uuid
from pathlib import Path
import round5_bulk as parser
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
SPECS=[*( (f'省考/北京/{y}/申论-{v}.md',4,'reports/FULL-REPAIR-BEIJING-ESSAY-RECONSTRUCTION-20261015.json') for y in [2020,2021] for v in ['区级','乡镇卷']),('省考/北京/2023/申论-统考.md',4,'reports/FULL-REPAIR-BEIJING-2023-20261015.json'),*( (f'省考/上海/2016/申论-{v}类.md',4,'reports/FULL-REPAIR-SHANGHAI-2016-RESTORATION-20261015.jsonl') for v in ['A','B']),('省考/天津/2017/申论-统考__t443.md',4,'reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json'),*( (f'省考/天津/2022/申论-{v}.md',3,'reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json') for v in ['市级','县级'])]
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def main():
 rp=ROOT/'reports/FULL-REPAIR-B-CERTIFIED-COUNTS-20261015.jsonl';count=0
 for rel,n,proof in SPECS:
  p=ROOT/rel;old=p.read_text(encoding='utf-8');d=parser.parse(old,rel);assert set(d['questions'])==set(range(1,n+1));assert (ROOT/proof).is_file()
  fields={'对照题本题量':n,'实有题数':n,'缺失原题号':[],'原题完整性核实凭据':proof};fields={k:v for k,v in fields.items() if (k+':') not in old.split('---',2)[1]}
  if not fields:continue
  new=set_fields(old,fields,'2026-10-15仅对已有完整同卷题本与逐题对应证明的卷固定应有题数，防止缺题时自报已满。');row={'path':rel,'proof':proof,'before_sha256':sha(old),'before_text':old,'after_sha256':sha(new),'after_text':new,'fields_added':fields,'status':'prepared'}
  with rp.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  t=p.with_name(p.name+'.count-'+uuid.uuid4().hex+'.tmp');t.write_bytes(new.encode());os.replace(t,p)
  with rp.open('a',encoding='utf-8') as f:f.write(json.dumps({'path':rel,'status':'applied','after_sha256':row['after_sha256']},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  count+=1
 print('Certified expected task counts set on',count,'source-proved papers.')
if __name__=='__main__':main()
