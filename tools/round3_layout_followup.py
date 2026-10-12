#!/usr/bin/env python3
"""One explicitly scoped, reversible layout correction after round3 delivery."""
from pathlib import Path
import hashlib,json,re
from paper_integrity_repair import split_paper

REL='省考/浙江/2016/申论-A类.md'
RECEIPT='reports/ROUND3-LAYOUT-FOLLOWUP-20261012.jsonl'
PATTERN=re.compile(r'(<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>)(.*?)(</details>)',re.S)

def sha(text):return hashlib.sha256(text.encode()).hexdigest()

def restore_receipted_version(root,rel,current):
    """Validate current follow-up and reconstruct the immutable R3 version.
    The R3 validator can therefore continue checking its original hashes.
    """
    path=Path(root)/RECEIPT
    if not path.exists():return current
    records=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if len(records)!=1 or records[0]['path']!=REL:raise ValueError('Unexpected layout follow-up scope')
    r=records[0]
    if rel!=REL:return current
    if sha(current)!=r['after_sha256']:raise ValueError('Layout follow-up current hash mismatch')
    before=r['before_block'];after=r['after_block']
    if current.count(after)!=1:raise ValueError('Follow-up is not uniquely reversible')
    original=current.replace(after,before,1)
    if sha(original)!=r['before_sha256']:raise ValueError('Layout follow-up inverse hash mismatch')
    od=split_paper(original);nd=split_paper(current)
    if original.split('## 答案与解析')[0]!=current.split('## 答案与解析')[0]:raise ValueError('Layout change touched material/question body')
    if set(od['answers'])!={1,2,3} or set(nd['answers'])!={1,2,3}:raise ValueError('Wrong answer IDs')
    if [int(m[2]) for m in PATTERN.finditer(current)]!=[1,2,3]:raise ValueError('Wrong rendered answer order')
    for n in [1,3]:
        if od['answers'][n]!=nd['answers'][n]:raise ValueError('Unrelated answer changed')
    removed=r['relocated_question_text']
    if od['answers'][2].count(removed)!=1 or od['answers'][2].replace(removed,'',1)!=nd['answers'][2]:raise ValueError('Actual answer wording was changed')
    if sha(removed)!=r['relocated_question_sha256']:raise ValueError('Lost relocated original text')
    if not all(w in removed for w in ['第一题','就业指导中心','讲话稿','500字']):raise ValueError('Removal is not the reviewed misplaced question')
    if not all(w in nd['qs'][2]['text'] for w in ['就业指导中心','讲话稿','500字']):raise ValueError('Question not preserved in its proper question section')
    return original

def main():
    root=Path(__file__).resolve().parents[1];rp=root/RECEIPT
    if rp.exists():raise ValueError('Already applied; never overwrite a receipt')
    p=root/REL;old=p.read_text(encoding='utf-8');matches=list(PATTERN.finditer(old));d=split_paper(old)
    if [int(m[2]) for m in matches]!=[2,1,3]:raise ValueError('Unexpected source block order')
    answer=d['answers'][2]
    m=re.search(r'(整体上条理较)(\s+第一题\s+假如你是[\s\S]*?)(为清晰。)',answer)
    if not m:raise ValueError('Reviewed insertion boundaries missing')
    removed=m[2]
    if not all(w in removed for w in ['就业指导中心','讲话稿','500字']):raise ValueError('Unexpected insertion')
    clean=answer.replace(removed,'',1)
    blocks={int(m[2]):m[0] for m in matches}
    if blocks[2].count(answer)!=1:raise ValueError('Nonunique old answer')
    blocks[2]=blocks[2].replace(answer,clean,1)
    before=old[matches[0].start():matches[-1].end()]
    after='\n\n'.join(blocks[n] for n in [1,2,3])
    if old.count(before)!=1:raise ValueError('Nonunique affected region')
    new=old.replace(before,after,1)
    record={'path':REL,'before_sha256':sha(old),'after_sha256':sha(new),'kind':'reversible_answer_layout_only','before_block':before,'after_block':after,'relocated_question_text':removed,'relocated_question_sha256':sha(removed),'old_answer2_sha256':sha(answer),'new_answer2_sha256':sha(clean),'reason':'旧答案解析被一整段题干打断；只移出错嵌题干，接回“整体上条理较为清晰”，全部旧混排原文保留在本凭据；答案块按1/2/3显示'}
    rp.write_text(json.dumps(record,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
    p.write_text(new,encoding='utf-8',newline='\n')
    assert restore_receipted_version(root,REL,p.read_text())==old
    print(json.dumps({'path':REL,'status':'passed','body_unchanged':True,'answers_order':[1,2,3],'relocated_chars':len(removed),'old_mixed_block_preserved_in_receipt':True},ensure_ascii=False))
if __name__=='__main__':main()
