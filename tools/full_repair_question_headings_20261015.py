"""Expose the parser's explicit original question boundaries as Markdown headings."""
import json,re
from pathlib import Path
import round5_bulk as parser
from full_repair_root_precise_revisions_20261015 import atomic,sha
ROOT=Path(__file__).resolve().parents[1]
def main():
    receipt=ROOT/'reports/FULL-REPAIR-QUESTION-HEADINGS-20261015.json'
    if receipt.exists():raise ValueError('Already prepared')
    plans=[]
    for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
        rel=p.relative_to(ROOT).as_posix();old=p.read_text(encoding='utf8');d=parser.parse(old,rel)
        if re.search(r'(?m)^##\s+第\s*\d+\s*题',old) or d['mode']!='unstructured':continue
        new=old
        for n,at in sorted(d['question_spans'].items(),key=lambda x:x[1],reverse=True):new=new[:at]+'\n## 第 '+str(n)+' 题\n\n'+new[at:]
        final=parser.parse(new,rel)
        if {n:parser.qkey(q) for n,q in final['questions'].items()}!={n:parser.qkey(q) for n,q in d['questions'].items()}:raise ValueError('Question identity changed: '+rel)
        if final['answers']!=d['answers']:raise ValueError('Answer content changed: '+rel)
        if old[:min(d['question_spans'].values())]!=new[:min(d['question_spans'].values())]:raise ValueError('Material prefix changed')
        plans.append({'path':rel,'before_text':old,'before_sha256':sha(old),'after_sha256':sha(new),'explicit_question_numbers':sorted(d['questions']),'new_text':new})
    proof={'status':'prepared','method':'Only insert headings at the parser already identified explicit 问题一/二/... boundaries. Original question, requirement, material and answer characters are retained.','papers':plans}
    atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    for row in plans:
        p=ROOT/row['path']
        if p.read_text(encoding='utf8')!=row['before_text']:raise ValueError('Concurrent paper edit')
        atomic(p,row.pop('new_text'))
    proof['status']='applied';atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'papers':len(plans),'question_headings':sum(len(x['explicit_question_numbers']) for x in plans)},ensure_ascii=False))
if __name__=='__main__':main()
