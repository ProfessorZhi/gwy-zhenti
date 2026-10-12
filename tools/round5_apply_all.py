#!/usr/bin/env python3
"""Apply all verified R5 candidates atomically per paper and preserve source history."""
import argparse,json
import round5_bulk as b
import round5_owned as owned
from round5_delivery import render
import round4_gap_repair as g

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 papers,bad,plans,left,diag=b.scan();plans,left,external=owned.extend(papers,plans,left)
 ready=[];errors=[]
 for t,a in plans:
  try:new,r=render(t,a);ready.append((t,new,r))
  except Exception as e:errors.append({'path':t['path'],'error':str(e)})
 count=sum(len(r['added_answers']) for _,_,r in ready);before=sum(len(t['missing']) for t in papers)
 summary={'baseline':b.BASE,'parsed_essays':len(papers),'unparsed_essays':len(bad),'recognized_missing_slots_before':before,'modified_papers':len(ready),'answers_added':count,'remaining_recognized_slots':before-count,'filled_fraction':round(count/before,6),'user_sources':external,'rejected':errors,'apply':args.apply,'known_xingce_questions_fixed':0,'known_xingce_questions_still_missing':25,'priority_year_subject_blanks_remaining':10,'boundary':'Document answer positions include overlapping historic records; no full-corpus authenticity certification.'}
 print('R5_DELIVERY',json.dumps(summary,ensure_ascii=False),flush=True)
 print('R5_CHANGED',[{'path':r['path'],'answers':[a['number'] for a in r['added_answers']]} for _,_,r in ready],flush=True)
 if not args.apply:return
 rp=b.ROOT/'reports'/b.RECEIPT
 if rp.exists() or errors or not ready:raise ValueError('Refuse repeated or failed delivery')
 for t,new,r in ready:
  p=b.ROOT/t['path']
  if g.digest(p.read_bytes())!=r['before_sha256']:raise ValueError('Concurrent source change')
 for t,new,r in ready:
  p=b.ROOT/t['path'];p.write_text(new,encoding='utf-8',newline='\n')
  if g.digest(p.read_bytes())!=r['after_sha256']:raise ValueError('Write readback mismatch')
 rp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in ready),encoding='utf-8')
 (b.ROOT/'reports/REPAIR-SUMMARY-20261012-R5.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (b.ROOT/'reports/ROUND5-UNRESOLVED-20261012.json').write_text(json.dumps({'parsed_missing':left,'unparsed':bad},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
