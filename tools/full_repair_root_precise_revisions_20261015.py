"""Apply individually reviewed body revisions with durable full preimages."""
import argparse,hashlib,json,os,re,uuid
from pathlib import Path
import round5_bulk as parser
import full_repair_answers_20261015 as applier
from full_repair_layout_20261015 import format_essay
ROOT=Path(__file__).resolve().parents[1]
def sha(t):return hashlib.sha256(t.encode()).hexdigest()
def atomic(p,t):
    tmp=p.with_name(p.name+'.root-review-'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('wb') as f:f.write(t.encode());f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if tmp.exists():tmp.unlink()
def run(data,batch):
    rows=json.loads(Path(data).read_text(encoding='utf-8'));rows=rows.get('answers',[]) if isinstance(rows,dict) else rows
    receipt=ROOT/f'reports/FULL-REPAIR-ROOT-PRECISE-{batch}-20261015.json'
    if receipt.exists():raise ValueError('Batch already prepared; inspect receipt before replay')
    before={r['path']:(ROOT/r['path']).read_text(encoding='utf-8') for r in rows}
    old_answers={p:parser.parse(t,p)['answers'] for p,t in before.items()}
    check,_=applier.apply_entries(ROOT,rows,False)
    if check['status']!='passed':raise ValueError(check)
    proof={'status':'prepared','data':Path(data).as_posix(),'entries':rows,'papers':[{'path':p,'before_text':t,'before_sha256':sha(t)} for p,t in before.items()]}
    atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    result,steps=applier.apply_entries(ROOT,rows,True)
    if result['status']!='passed':raise ValueError(result)
    for p,old in before.items():
        text=(ROOT/p).read_text(encoding='utf-8')
        for row in [r for r in rows if r['path']==p]:
            n=row['number'];previous=old_answers[p][n]
            # The heading deliberately cannot masquerade as another current task.
            text+='\n\n### 正文复核留存：原参考作答 '+str(n)+'（'+batch+'）\n\n<details>\n<summary>修订前来源参考稿（仅供校勘，不作当前规范作答）</summary>\n\n'+previous+'\n\n</details>\n'
        text,layout=format_essay(text,p)
        current=parser.parse(text,p)
        for row in [r for r in rows if r['path']==p]:
            if row['answer'].strip() not in current['answers'][row['number']]:raise ValueError('New body lost')
        atomic(ROOT/p,text)
        entry=next(x for x in proof['papers'] if x['path']==p);entry.update(after_sha256=sha(text),layout=layout)
    proof.update(status='applied',summary=result,application_steps=steps)
    atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('data',type=Path);args.add_argument('--batch',required=True);ns=args.parse_args();run(ns.data,ns.batch)
