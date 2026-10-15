"""Audit current task bodies separately from immutable historical receipts."""
import argparse,collections,json,re
from pathlib import Path
import r7_reference_audit as r7
import round5_bulk as parser
import full_repair_precise_answer_audit_20261015 as precise
from full_repair_answers_20261015 import validate_answer
ROOT=Path(__file__).resolve().parents[1]
MARKER=re.compile(r'<!-- full-repair-answer-20261015 -->\s*(.*?)\s*<!-- /full-repair-answer-20261015 -->',re.S)

def audit():
    rows,bad,requests,counts=r7.audit();errors=[];originals=[];authorship=collections.Counter()
    for row in rows:
        p=ROOT/row['path'];text=p.read_text(encoding='utf-8');paper=parser.parse(text,row['path'])
        # An excerpt explicitly asking for an essay remains an essay even when
        # the source lost its word-limit tail. Historical r7 remains untouched.
        for task in row['tasks']:
            q=paper['questions'][task['number']]
            if task['kind']=='小题参考作答' and re.search(r'写一篇(?:议论性文章|议论文|文章)|写一篇.{0,6}文章',q):
                counts[task['kind']+'/'+task['status']]-=1
                counts['作文范文/'+task['status']]+=1
        for n,q in paper['questions'].items():
            answer=paper['answers'].get(n,'');match=MARKER.search(answer)
            if not match:continue
            try:
                count=validate_answer(q,{'answer':match[1],'attribution_kind':'ai_original','author':'AI辅助原创'})
                if '不是官方答案' not in answer or '来源说明' not in answer:raise ValueError('Missing authorship notice')
                if re.search(r'此处(?:可以写|填写|补充)|具体表述缺失',match[1]):raise ValueError('Unresolved drafting placeholder')
                prefix=answer[:match.start()]
                kind='AI辅助修订' if 'AI辅助修订示范' in prefix else 'AI辅助原创' if 'AI辅助原创示范' in prefix else '同题来源参考'
                authorship[kind]+=1
                originals.append({'path':row['path'],'number':n,'characters':count,'authorship_kind':kind})
            except Exception as exc:errors.append({'path':row['path'],'number':n,'error':str(exc)})
    missing=[{'path':row['path'],'tasks':[t for t in row['tasks'] if t['status']!='已收录']} for row in rows if row['status']!='已收录']
    unresolved=[]
    for p in [*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]:
        t=p.read_text(encoding='utf-8')
        notes=re.findall(r'> 原参考正文[^\n]+',t)
        if notes:unresolved.append({'path':p.relative_to(ROOT).as_posix(),'source_length_notes':notes})
    body_review=precise.audit()
    enforced={'explicit_minimum_not_met','explicit_maximum_exceeded','per_item_maximum_exceeded','outline_or_placeholder','no_main_body','approximate_target_short','approximate_target_long'}
    body_errors=[r for r in body_review['candidates'] if not r['another_version_without_findings'] and any(i['rule'] in enforced for i in r['issues'])]
    return {'status':'passed' if not bad and not missing and not errors and not unresolved and not body_errors and not body_review['parse_errors'] else 'failed','essay_papers':len(rows)+len(bad),'parsed_papers':len(rows),'classifications':dict(counts),'unparsed':bad,'incomplete_recognized_tasks':missing,'new_or_revised_answer_bodies_checked':len(originals),'checked_body_authorship':dict(authorship),'answer_body_errors':errors,'legacy_source_length_notes':unresolved,'precise_body_counts':body_review['counts'],'precise_body_candidate_tasks':body_review['candidate_tasks'],'precise_body_errors':body_errors,'precise_body_review_candidates':body_review['candidates'],'boundary':'Actual body lengths exclude source URLs, authorship labels and teacher commentary. A compliant alternative body can satisfy the task while historical versions remain reviewable. Ambiguous original word limits remain explicit review candidates. Missing entire papers, source factual truth, actual exam scores, and unavailable original conditions are separate inventory findings.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);args=ap.parse_args();result=audit()
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('legacy_source_length_notes','precise_body_review_candidates')},ensure_ascii=False,indent=2))
    raise SystemExit(result['status']!='passed')
if __name__=='__main__':main()
