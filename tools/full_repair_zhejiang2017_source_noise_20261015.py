"""Remove a proven web recommendation block outside the original materials."""
import json,re
from pathlib import Path
from full_repair_root_precise_revisions_20261015 import atomic,sha
ROOT=Path(__file__).resolve().parents[1]
def main():
    receipt=ROOT/'reports/FULL-REPAIR-ZHEJIANG2017-SOURCE-NOISE-20261015.json'
    if receipt.exists():raise ValueError('Already applied')
    plans=[]
    for v in ('A','B'):
        rel=f'省考/浙江/2017/申论-{v}类.md';p=ROOT/rel;old=p.read_text(encoding='utf8')
        start=old.index('环球网校友情提示：');end=old.index('## 作答要求',start)
        removed=old[start:end];assert '2018年国家公务员考试面试热点' in removed and '【摘要】历年试题' in removed
        new=old[:start]+old[end:]
        plans.append({'path':rel,'before_text':old,'before_sha256':sha(old),'after_sha256':sha(new),'removed_web_navigation':removed,'new_text':new})
    proof={'status':'prepared','papers':plans};atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    for row in plans:
        if (ROOT/row['path']).read_text(encoding='utf8')!=row['before_text']:raise ValueError('Concurrent source change')
        atomic(ROOT/row['path'],row.pop('new_text'))
    proof['status']='applied';atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print('Removed web navigation from two papers; full preimages retained.')
if __name__=='__main__':main()
