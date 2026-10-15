"""Restore explicit Shenzhen variant boundaries from existing combined transcripts."""
import json,re
from pathlib import Path
import round5_bulk as parser
import round4_gap_repair as g
from round4_delivery import operations
from r7_delivery import strip_guide
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
SPECS=[
 ('省考/深圳/2018/申论-A类.md','Ａ卷作答要求','B卷作答要求',r'第[一二三]题[：:]'),
 ('省考/深圳/2019/申论-一卷.md','一卷问题及作答要求','二卷问题及作答要求',r'[123]、'),
 ('省考/深圳/2022/申论-一卷.md','（一）卷作答要求','（二）卷作答要求',r'问题[一二三][：:]'),
 ('省考/深圳/2023/申论-一卷.md','一卷作答要求','二卷作答要求',r'问题[一二三][：:]'),
]
def main():
    receipts=[]
    for rel,startmark,endmark,pattern in SPECS:
        p=ROOT/rel;old=p.read_text(encoding='utf-8')
        if '分卷纠正凭据:' in old:continue
        parsed=parser.parse(old,rel);clean=strip_guide(old)
        start=clean.index(startmark);end=clean.index(endmark,start)
        selected=clean[start+len(startmark):end].strip()
        selected=re.sub(r'<!--.*?-->','',selected,flags=re.S).strip()
        found=list(re.finditer(pattern,selected))
        if len(found)!=3:raise ValueError('Expected three explicit variant tasks: '+rel)
        questions=[selected[m.start():found[j+1].start() if j+1<len(found) else len(selected)].strip() for j,m in enumerate(found)]
        if any('要求' not in q or not re.search(r'\d+\s*字',q) for q in questions):raise ValueError('Incomplete variant task requirements')
        prefix=clean[:start].rstrip()
        # Preserve existing correct answers only when their question text still aligns.
        keep={}
        for n,a in parsed['answers'].items():
            if not __import__('full_repair_answers_20261015').pending(a):
                if parser.qkey(parsed['questions'][n])!=parser.qkey(questions[n-1]):
                    if rel=='省考/深圳/2023/申论-一卷.md' and n in (1,2):continue
                    raise ValueError('Existing answer requires manual remap: '+rel+'#'+str(n))
                keep[n]=a
        source='https://github.com/ProfessorZhi/gwy-zhenti/blob/f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab/'+__import__('urllib.parse',fromlist=['quote']).quote(rel,safe='/')
        prefix=set_fields(prefix,{'题目结构':'合卷资料保留；按源文显式本卷标签拆分作答要求','分卷纠正凭据':'reports/FULL-REPAIR-SHENZHEN-VARIANTS-20261015.jsonl','实有题数':3,'对照题本题量':3,'缺失原题号':[],'题目分值':[20,30,50],'已收录参考答案题号':sorted(keep),'缺参考答案题号':sorted({1,2,3}-set(keep))},'2026-10-15按合卷原文的显式卷别恢复本卷题目；不再把末尾另一卷题目错当本卷。')
        year=rel.split('/')[2]
        prefix=re.sub(r'(?m)^# .*$',lambda m:'# '+year+'年深圳市公务员考试《申论》试题（'+('A卷' if year=='2018' else '一卷')+'）',prefix,count=1)
        new=prefix+'\n\n> 分卷校核：共享给定材料保留，本卷题目按原合卷页面中的“'+startmark+'”区段恢复；另一卷作答要求在对应分卷阅读。[固定版本原记录]('+source+')。\n\n'
        new+='\n\n'.join('## 第 '+str(n)+' 题\n\n'+q for n,q in enumerate(questions,1))+'\n'
        if keep:new+='\n## 答案与解析\n\n'+'\n\n'.join('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+keep.get(n,'本题尚未收录可核对的完整参考作答。')+'\n\n</details>' for n in (1,2,3))+'\n'
        check=parser.parse(new,rel)
        if len(check['questions'])!=3:raise ValueError('Rebuilt variant unparseable')
        for n,a in keep.items():
            if check['answers'][n]!=a:raise ValueError('Existing correct reference altered')
        r={'path':rel,'before_sha256':g.digest(old),'after_sha256':g.digest(new),'source':source,'evidence':startmark+'至'+endmark,'preserved_existing_answers':sorted(keep),'operations':operations(old,new)}
        p.write_text(new,encoding='utf-8',newline='\n');receipts.append(r)
    if receipts:
        receipt=ROOT/'reports/FULL-REPAIR-SHENZHEN-VARIANTS-20261015.jsonl'
        previous=receipt.read_text(encoding='utf-8') if receipt.exists() else ''
        receipt.write_text(previous+''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in receipts),encoding='utf-8')
    print(json.dumps({'variant_papers_corrected':len(receipts),'paths':[r['path'] for r in receipts]},ensure_ascii=False))
if __name__=='__main__':main()
