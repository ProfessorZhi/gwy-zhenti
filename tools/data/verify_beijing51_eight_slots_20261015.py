"""Independent stronger construction using only eight-participant/top-two queries.

The actual question also permits six-participant/top-one queries, as used in
the main answer's valid construction. This additional check omits that allowed
operation and still achieves eight runs. A padding participant beating all six
local candidates is explicitly handled.
"""
import collections,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def solve(performance,rng):
    calls=[]
    def query(xs):
        assert len(xs)==8 and len(set(xs))==8
        result=sorted(xs,key=lambda x:performance[x])[:2]
        rng.shuffle(result);calls.append(list(xs));return result
    groups=[list(range(8*i,8*i+8)) for i in range(4)]
    winners=[query(xs) for xs in groups];heads=sum(winners,[])
    pq=query(heads);p,q=pq;rest=[x for x in heads if x not in pq]
    group=lambda x:x//8
    safe=[x for j,xs in enumerate(groups) if j not in {group(p),group(q)} for x in xs if x not in winners[j]]
    assert len(safe)>=12
    def other(result):
        assert p in result
        return next(x for x in result if x!=p)
    padding_wins=False
    if group(p)==group(q):
        losers=[x for x in groups[group(p)] if x not in pq]
        uv=query(losers+rest[:2])
        rs=query(uv+rest[2:]+safe[:2]);answer=set(pq+rs);branch='same_group'
    else:
        r=other(query([p]+rest+[safe[0]]));remaining=[x for x in rest if x!=r]
        if group(r) in {group(p),group(q)}:
            losers=[x for x in groups[group(r)] if x not in winners[group(r)]]
            candidate=other(query([p]+losers+[safe[0]]))
            padding_wins=candidate==safe[0]
            # If the padding wins, all six local losers are eliminated. The
            # eighth query still finds fourth in the other five group winners.
            if padding_wins:final=[p]+remaining+safe[:2]
            else:final=[p]+remaining+[candidate,safe[0]]
            s=other(query(final));branch='different_groups_partner_third'
        else:
            s=other(query([p]+remaining+safe[:2]));branch='different_groups_other_third'
        answer=set(pq+[r,s])
    assert answer==set(sorted(range(32),key=lambda x:performance[x])[:4])
    assert len(calls)<=8 and all(len(xs)==8 for xs in calls)
    return len(calls),branch,padding_wins
def main():
    rng=random.Random(20261015);oracle_rng=random.Random(520261015);permutation=list(range(32));counts=collections.Counter();branches=collections.Counter();pad=0
    for _ in range(200000):
        rng.shuffle(permutation);n,branch,won=solve(permutation,oracle_rng);counts[n]+=1;branches[branch]+=1;pad+=won
    for performance in [list(range(32)),list(reversed(range(32)))]:solve(performance,oracle_rng)
    assert pad>0
    result={'status':'passed','random_cases':200000,'all_queries_exactly_eight_participants':True,'each_query_returns_two_unordered_winners':True,'query_count_distribution':dict(counts),'branches':dict(branches),'padding_wins_cases_explicitly_handled':pad,'upper_bound':8,'global_lower_bound_proved':False,'boundary':'A constructive at-most-eight bound only; no claim that every seven-query strategy is impossible.'}
    (ROOT/'reports/FULL-REPAIR-BEIJING-Q51-EIGHT-SLOTS-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
