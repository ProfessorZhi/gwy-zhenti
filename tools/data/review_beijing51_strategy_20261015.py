"""Independent upper-bound check with unordered top-two machine outputs."""
import builtins,collections,hashlib,importlib.util,json,random
from pathlib import Path
R=Path(__file__).resolve().parents[2]
source=R/'tools/data/verify_beijing51_strategy_20261015.py'
spec=importlib.util.spec_from_file_location('beijing51_strategy',source)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
rng=random.Random(20261015051)
flips=0
def unordered_sorted(xs,*args,**kwargs):
 global flips
 vals=builtins.sorted(xs,*args,**kwargs)
 if len(vals)==8 and rng.getrandbits(1):
  vals[0],vals[1]=vals[1],vals[0];flips+=1
 return vals
mod.sorted=unordered_sorted
counts=collections.Counter();branches=collections.Counter();p=list(range(32))
for _ in range(50000):
 rng.shuffle(p);n,b=mod.solve(p);counts[n]+=1;branches[b]+=1
for p in [list(range(32)),list(reversed(range(32)))]:mod.solve(p)
row={
 'source':'tools/data/verify_beijing51_strategy_20261015.py',
 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'random_cases':50000,'seed':20261015051,'top_two_order':'Every 8-to-2 output pair independently reversed with probability 1/2; strategy cannot rely on hidden within-pair rankings.',
 'pair_order_flips':flips,'query_counts':dict(counts),'branches':dict(branches),'status':'passed',
 'proven_upper_bound':8,
 'lower_bound_status':'No global lower bound excluding all seven-query strategies has been established. The eight-query constructive strategy refutes a minimum-ten claim but alone does not prove eight is optimal.',
 'prefix_specific_lower_bound':'In the stated four-groups-of-eight prefix, after p/q arise from different groups and third winner r is p/q partner, the fourth-best remains possible among six previously unselected devices in r group and five other heads. One last query can contain at most eight distinct devices, so that fixed prefix needs two additional queries. This is not a bound for every possible global strategy.'
}
(R/'reports/BEIJING51-INDEPENDENT-REVIEW-20261015.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(row,ensure_ascii=False))
