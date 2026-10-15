"""Archive proven mixed/repeated fragments, keeping every source byte recoverable."""
import argparse,hashlib,json,os,re,uuid
from difflib import SequenceMatcher
from pathlib import Path
import round5_bulk as parser
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def atomic(p,text):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.fragment-'+uuid.uuid4().hex+'.tmp')
    try:tmp.write_bytes(text.encode());os.replace(tmp,p)
    finally:
        if tmp.exists():tmp.unlink()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--include-shanghai-prior',action='store_true');ap.add_argument('--include-fujian-duplicates',action='store_true');ap.add_argument('--include-jiangzhe-buckets',action='store_true');args=ap.parse_args()
    proof=ROOT/'reports/FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json';global_data=json.loads(proof.read_text(encoding='utf-8'))
    specs=[('天津',2022,'申论-区级卷.md','天津2022申论-原区级卷两题重复片段.md'),('天津',2022,'申论-市级卷.md','天津2022申论-原市级卷两题重复片段.md')]
    for year in ([2016,2017,2018,2019,2020,2021,2022,2023] if args.include_shanghai_prior else [2022,2023]):specs.append(('上海',year,'申论-统考.md',f'上海{year}申论-原统考混合或重复来源.md'))
    if args.include_fujian_duplicates:
        specs.extend([('福建',2021,'申论-县级卷.md','福建2021申论-原县级卷重复片段.md'),('福建',2021,'申论-乡镇卷.md','福建2021申论-原乡镇卷重复片段.md'),('福建',2022,'申论-县乡卷.md','福建2022申论-原县乡卷重复片段.md')])
    if args.include_jiangzhe_buckets:
        for area in ('江苏','浙江'):
            for p in (ROOT/'省考'/area).glob('*/申论-统考.md'):
                specs.append((area,int(p.parent.name),p.name,f'{area}{p.parent.name}申论-原统考混合或重复来源.md'))
    plans=[]
    for area,year,name,destname in specs:
        rel=f'省考/{area}/{year}/{name}';dest='docs/来源校勘/'+destname
        if rel in global_data['relocations']:continue
        p=(ROOT/rel).resolve();q=(ROOT/dest).resolve()
        if not p.is_relative_to(ROOT/'省考'/area/str(year)) or not q.is_relative_to(ROOT/'docs/来源校勘'):raise ValueError('Archive boundary violation')
        if not p.exists() or q.exists():raise ValueError('Missing source or occupied archive: '+rel)
        old=p.read_text(encoding='utf-8');fragment=parser.parse(old,rel);candidates=[]
        for canonical in p.parent.glob('申论*.md'):
            if canonical==p or canonical.name.startswith('申论-统考'):continue
            # Tianjin 2022's other partial source is not a canonical paper.
            if area=='天津' and canonical.name in ('申论-区级卷.md','申论-市级卷.md'):continue
            target=parser.parse(canonical.read_text(encoding='utf-8'),canonical.relative_to(ROOT).as_posix())
            candidates.extend((canonical.relative_to(ROOT).as_posix(),n,parser.qkey(question)) for n,question in target['questions'].items())
        mapping=[]
        for n,question in fragment['questions'].items():
            key=parser.qkey(question);scores=sorted((SequenceMatcher(None,key,k,autojunk=False).ratio(),path,number) for path,number,k in candidates)
            if not scores or scores[-1][0]<.90:raise ValueError('Fragment not yet matched to complete paper: '+rel+'#'+str(n))
            score,path,number=scores[-1];mapping.append({'source_number':n,'canonical_path':path,'canonical_number':number,'question_similarity':score})
        new=set_fields(old,{'收录状态':'历史混合或重复片段来源留存，不计独立真题分卷','身份校核凭据':'reports/FULL-REPAIR-FRAGMENT-ARCHIVE-20261015.jsonl'},'2026-10-15按全部题目与完整分卷逐题对应归档；原文、来源与旧答案完整保留。')
        title=re.search(r'(?m)^# [^\n]+\n',new)
        links='；'.join('['+Path(v).stem+'](../../'+v+')' for v in sorted({m['canonical_path'] for m in mapping}))
        notice='\n> **来源校勘留存稿。** 本文件题目已逐题对应完整分卷，旧内部桶不作为另一套独立原卷。正式练习入口：'+links+'。此处保留全部旧来源材料和作答，映射见身份校核凭据。\n'
        new=new[:title.end()]+notice+new[title.end():]
        plans.append({'path':rel,'destination':dest,'before_sha256':sha(old),'after_sha256':sha(new.rstrip()+'\n'),'mapping':mapping,'old':old,'new':new.rstrip()+'\n'})
    # Validate all plans before any archive/move.
    records=[]
    for item in plans:
        p=ROOT/item['path'];q=ROOT/item['destination']
        if p.read_text(encoding='utf-8')!=item['old']:raise ValueError('Concurrent source edit')
        atomic(q,item['new'])
        if sha(q.read_text(encoding='utf-8'))!=item['after_sha256']:raise ValueError('Archive bytes mismatch')
        # Exact resolved source/destination boundaries were verified above.
        p.unlink();global_data['relocations'][item['path']]=item['destination']
        records.append({k:v for k,v in item.items() if k not in ('old','new')})
    if records:
        receipt=ROOT/'reports/FULL-REPAIR-FRAGMENT-ARCHIVE-20261015.jsonl';previous=receipt.read_text(encoding='utf-8') if receipt.exists() else ''
        atomic(receipt,previous+''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
        atomic(proof,json.dumps(global_data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'archived_fragments':len(records),'paths':[r['path'] for r in records]},ensure_ascii=False))
if __name__=='__main__':main()
