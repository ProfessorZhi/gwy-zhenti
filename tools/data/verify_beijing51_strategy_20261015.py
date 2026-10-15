"""Verify an at-most-eight-query counterexample to the source's ten-query key.

Only the query functions see the performance ordering. The strategy itself uses
machine identities, recorded group membership, and prior query outcomes.
This establishes an upper bound, not an exhaustive global lower-bound proof.
"""
import collections,json,random
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def solve(performance):
 calls=[]
 def top(xs,k):
  assert len(xs)==(8 if k==2 else 6) and len(set(xs))==len(xs)
  result=sorted(xs,key=lambda x:performance[x])[:k]
  calls.append((len(xs),k))
  return result
 groups=[list(range(i*8,(i+1)*8)) for i in range(4)]
 tops=[top(g,2) for g in groups];heads=sum(tops,[])
 pq=top(heads,2);rest=[x for x in heads if x not in pq]
 gi=lambda x:x//8
 if gi(pq[0])==gi(pq[1]):
  g=gi(pq[0]);losers=[x for x in groups[g] if x not in tops[g]]
  uv=top(losers+rest[:2],2)
  # Outside g every initial non-winner has at least four proven superiors:
  # p,q plus its own two group winners, hence cannot belong to global top four.
  padding=[x for j in range(4) if j!=g for x in groups[j] if x not in tops[j]][:2]
  rs=top(uv+rest[2:]+padding,2)
  answer=set(pq+rs);branch='same_group'
 else:
  rr=top(rest,1)[0];remaining=[x for x in rest if x!=rr]
  if gi(rr) in {gi(x) for x in pq}:
   g=gi(rr);losers=[x for x in groups[g] if x not in tops[g]]
   candidate=top(losers,1)[0]
   ss=top([candidate]+remaining,1)[0];branch='different_groups_partner_third'
  else:
   # A group-loser below rr's other original winner cannot be fourth.
   pad=next(x for x in groups[gi(rr)] if x not in tops[gi(rr)])
   ss=top(remaining+[pad],1)[0];branch='different_groups_other_third'
  answer=set(pq+[rr,ss])
 assert answer==set(sorted(range(32),key=lambda x:performance[x])[:4])
 return len(calls),branch

if __name__=='__main__':
 rng=random.Random(20261015);counts=collections.Counter();branches=collections.Counter();p=list(range(32))
 for _ in range(200000):
  rng.shuffle(p);n,b=solve(p);counts[n]+=1;branches[b]+=1
 for p in [list(range(32)),list(reversed(range(32)))]:solve(p)
 row={'status':'passed','random_cases':200000,'seed':20261015,'query_counts':dict(counts),'branches':dict(branches),'upper_bound':8,'source_key_claim':10,'conclusion':'A source claim that at least ten queries are necessary is disproved. This script does not prove no strategy using seven queries exists.'}
 (R/'reports/FULL-REPAIR-BEIJING-Q51-COUNTEREXAMPLE-20261015.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(row,ensure_ascii=False))
