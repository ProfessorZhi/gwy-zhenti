"""State the actual single-task excerpt boundary without inventing requirements."""
import json,re
from pathlib import Path
from paper_integrity_repair import set_fields
from full_repair_layout_20261015 import format_essay
from full_repair_root_precise_revisions_20261015 import atomic,sha
ROOT=Path(__file__).resolve().parents[1]
def main():
    receipt=ROOT/'reports/FULL-REPAIR-XINJIANG2021-EXCERPT-BOUNDARY-20261015.json'
    if receipt.exists():raise ValueError('Already applied')
    rel='省考/新疆/2021/申论-下半年.md';p=ROOT/rel;old=p.read_text(encoding='utf8')
    new=set_fields(old,{'真题性质':'来源标注为真题；完整原卷和原始作答要求未独立核实','收录状态':'单篇作文及所附材料摘录，不计完整原卷认证','原始作答要求完整性':'原上游题干止于“要求：”，字数及其他要求未取得','原卷完整性':'仅有1道作文；其他题目及整卷题量未取得','完整性校核凭据':receipt.relative_to(ROOT).as_posix()},'2026-10-15明确作文摘录与原题要求缺失，不以可读范文冒充完整原卷。')
    new=re.sub(r'(?m)^# [^\n]+', '# 2021年新疆申论作文题摘录（上游标注下半年，原始要求待核）',new,count=1)
    title=re.search(r'(?m)^# [^\n]+\n',new)
    notice='\n> **收录边界：** 本页仅有一道作文及所附材料，上游题干在“要求：”后缺失内容。原始字数、其他作答要求及整卷题量尚未取得，不能把本页当作完整原卷。现有范文供比较立意、结构和论证，不以自行建议的篇幅冒充原题限制。\n'
    new=new[:title.end()]+notice+new[title.end():]
    new,layout=format_essay(new,rel)
    proof={'status':'prepared','path':rel,'before_text':old,'before_sha256':sha(old),'after_sha256':sha(new),'upstream_matching_sources':['linfukai186-gongkao-tiku/data/shengkao-shenlun/y2021.json : 2021·新疆下半年公考','gongkao-tiku/data/shenlun-shengkao.json : 2021·新疆下半年公考'],'same_source_limitation':'Both sources have exactly one task, and both question fields end at 要求：. They do not independently establish the missing original requirements.','layout':layout}
    atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    if p.read_text(encoding='utf8')!=old:raise ValueError('Concurrent source change')
    atomic(p,new);proof['status']='applied';atomic(receipt,json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print('One excerpt boundary stated; no original requirement invented.')
if __name__=='__main__':main()
