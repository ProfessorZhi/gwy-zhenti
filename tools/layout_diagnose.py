# -*- coding: utf-8 -*-
"""全库只读排版诊断（第三轮）。

只读：不写入任何试卷文件，只输出 JSON 与计数。
检出项是当前规则能看到的，不是全库缺陷全集；未检出不等于不存在。
用法：python tools/layout_diagnose.py <repo_root> [out.json]
"""
import os,re,sys,json,unicodedata,hashlib,collections
from pathlib import Path
ROOT=sys.argv[1] if len(sys.argv)>1 else "."
def norm(s):
    s=unicodedata.normalize('NFKC',s); return re.sub(r'\s+','',s)
ART=("图片/","reports/","catalog/","tools/","docs/")
md=[]
for dp,dn,fn in os.walk(ROOT):
    if '/.git' in dp or '/.github' in dp: continue
    for f in fn:
        if f.endswith('.md'): md.append(os.path.join(dp,f))
md.sort()
ISS=collections.defaultdict(list)
Q_RE=re.compile(r'^#{2,4} 第 (\d+) 题',re.M)
A_RE=re.compile(r'<summary>第 (\d+) 题</summary>')
for p in md:
    rel=os.path.relpath(p,ROOT)
    top=rel.split('/')[0]
    t=open(p,encoding='utf-8').read()
    qn=[int(m.group(1)) for m in Q_RE.finditer(t)]
    an=[int(m.group(1)) for m in A_RE.finditer(t)]
    if not qn and not an: continue
    paper = top in ("国考","省考","资料缺失")

    # A. 题干题号必须严格递增且从1开始；允许已知缺号但必须是"声明过的"
    if qn!=sorted(qn) or (qn and qn[0]!=1):
        ISS['question_order_broken'].append((rel,qn[:12]))
    gap=[n for n in range(1,max(qn)+1) if n not in qn] if qn else []
    if gap: ISS['question_number_gap'].append((rel,gap))

    # B. 答案块与题干块的对应
    if an:
        orphan=[n for n in an if n not in qn]
        if orphan: ISS['answer_without_question'].append((rel,orphan))
        if an!=sorted(an): ISS['answer_order_broken'].append((rel,an[:12]))

    # C. 材料锚点
    for pat,tag in ((r'^## 给定资料 (\d+)\s*$','资料'),(r'^## 给定材料 (\d+)\s*$','材料')):
        nums=[int(m.group(1)) for m in re.finditer(pat,t,re.M)]
        if nums:
            g=[n for n in range(1,max(nums)+1) if n not in nums]
            if g: ISS['material_anchor_gap'].append((rel,tag,g))
    # 行测共享材料声明 vs 实际子题
    for m in re.finditer(r'^## 材料 (\d+)（第(\d+)—(\d+)题共用）',t,re.M):
        lo,hi=int(m.group(2)),int(m.group(3))
        body=t[m.end():]
        nxt=re.search(r'^## ',body,re.M)
        seg=body[:nxt.start()] if nxt else body
        sub=[int(x.group(1)) for x in Q_RE.finditer(seg)]
        exp=list(range(lo,hi+1))
        if sub!=exp:
            ISS['shared_material_span_mismatch'].append((rel,int(m.group(1)),f"声明{lo}-{hi}",f"实际{sub}"))

    # D. 文件内重复材料（申论长材料）
    blk=re.split(r'^## 给定资料 \d+\s*$',t,flags=re.M)
    if len(blk)>2:
        seen={}
        for b in blk[1:]:
            n=norm(b)
            if len(n)>120:
                k=hashlib.sha256(n.encode()).hexdigest()[:16]; seen[k]=seen.get(k,0)+1
        d=sum(1 for v in seen.values() if v>1)
        if d: ISS['dup_material_in_file'].append((rel,d))

    # E. 残留模块拼接：同一文件出现多个"答案与解析"块 / 过期计数摘要
    if t.count('## 答案与解析')>1: ISS['multiple_answer_sections'].append((rel,t.count('## 答案与解析')))
    for i,l in enumerate(t.split('\n')):
        if re.search(r'(当前题数|当前数量|本卷共收录|共收录\s*\d+\s*题|现有\s*\d+\s*题|本次共(收录|计|有))',l):
            pat=re.search(r'(当前题数|当前数量|本卷共收录|共收录\s*\d+\s*题|现有\s*\d+\s*题|本次共)',l)
            ISS['stale_count_line'].append((rel,i+1,pat.group(0),l.strip()[:70]))

    # F. 字数/分值要求分离：只看 ### 作答要求 子块本身，不看整题块
    if paper and re.search(r'申论',rel):
        for m in re.finditer(r'^#{2,4} 第 (\d+) 题[^\n]*$(.*?)(?=^#{2,4} 第 \d+ 题|^## 答案与解析|\Z)',t,re.M|re.S):
            body=m.group(2); n=int(m.group(1))
            if norm(body)=='' : continue
            rq=re.search(r'^#{3,4} 作答要求\s*$(.*?)(?=^#{2,4} |\Z)',body,re.M|re.S)
            if not rq:
                ISS['shenlun_no_requirement_heading'].append((rel,n)); continue
            req=rq.group(1)
            if not re.search(r'字(数)?|篇幅',req): ISS['shenlun_requirement_no_wordcount'].append((rel,n))
            if not re.search(r'\d+\s*分',req):      ISS['shenlun_requirement_no_score'].append((rel,n))
            tail=norm(req)[-6:]
            if tail.endswith('要求：') or tail.endswith('要求:'):
                ISS['shenlun_requirement_truncated'].append((rel,n,req.strip()[-40:].replace(chr(10),' ')))
            elif re.search(r'(不超过|不少于|不多于|\d+\s*[—-]\s*\d+\s*字)',norm(req)) and not re.search(r'字',norm(req)):
                ISS['shenlun_requirement_truncated'].append((rel,n,req.strip()[-40:].replace(chr(10),' ')))
    # G. markdown 可读性（仅试卷）
    if paper:
        for m in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)',t):
            tgt=m.group(1).strip().split()[0].strip('<>')
            if tgt.startswith('http'): continue
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p),tgt))):
                ISS['image_missing'].append((rel,tgt))
        if t.count('```')%2: ISS['code_fence_unbalanced'].append((rel,t.count('```')))

print(f"扫描 MD = {len(md)}")
for k in sorted(ISS):
    print(f"  {k:40s} {len(ISS[k])}")
    if k in ("answer_without_question","multiple_answer_sections","question_number_gap","question_order_broken","stale_count_line","material_anchor_gap","shared_material_span_mismatch","dup_material_in_file","image_missing","code_fence_unbalanced","answer_order_broken","shenlun_question_no_requirement","shenlun_requirement_no_wordcount","shenlun_no_requirement_heading","shenlun_requirement_no_score","shenlun_requirement_truncated"):
        for it in ISS[k][:12]: print("      -",it)
out=sys.argv[2] if len(sys.argv)>2 else str(Path(ROOT)/'reports/LAYOUT-DIAGNOSIS-20261012-R3.json')
Path(out).write_text(json.dumps({'scanned_md':len(md),'findings':{k:v for k,v in ISS.items()},
  'boundary':'只读诊断；检出项由当前规则定义，未检出不代表不存在；不覆盖题干、材料、答案或历史凭据。'},
  ensure_ascii=False,indent=1),encoding='utf-8')
print("written:",out)
