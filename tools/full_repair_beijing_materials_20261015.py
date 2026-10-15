"""Recover absent shared passages from the user's same-question course manuscripts."""
import hashlib,json,re,unicodedata
from pathlib import Path
from urllib.parse import quote
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
OWNER_ROOT=Path('D:/projects/gwy-material-ops')
COURSE=OWNER_ROOT/'knowledge/gwy/000【上岸独家】花生十三/【003】【套题班-国考二期】2026年花生十三飞扬行测申论套题二期⭐/题本'
TARGET='省考/北京/2025/行测-统考.md'
def sha(t):return hashlib.sha256(t.encode('utf-8')).hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKC',t) if c.isalnum())
def clean(t):
    t=re.sub(r'<!--\s*page:.*?-->','',t,flags=re.S)
    t=re.sub(r'第\s*\d+\s*页\s*共\s*\d+\s*页','',t)
    return re.sub(r'\n\s*\n\s*\n+','\n\n',t).strip()

def main():
    p=ROOT/TARGET;old=p.read_text(encoding='utf-8')
    if '北京同题共用材料补录凭据:' in old:raise ValueError('Already applied')
    specs=[
      ('行测-副省级/副省（10）【四海】25下半年2期套题班《行测》.pdf.md','材料一长城是中华民族','请回答56～60 题',22,26,1),
      ('行测-地市级和行政执法/地市（5）【四海】25下半年2期套题班《行测》.pdf.md','2023 年8 月，中国科学院科研团队','请回答1～5 题',27,31,2),
    ]
    additions=[];rows=[]
    for relative,start,end,first,last,group in specs:
        source=COURSE/relative;raw=source.read_text(encoding='utf-8');a=raw.index(start);b=raw.index(end,a)
        passage=clean(raw[a:b])
        source_questions=raw[b:]
        qregion=old[old.index('## 第 '+str(first)+' 题'):old.index('## 第 '+str(last+1)+' 题')]
        # Require the complete current option texts to occur in the same source block.
        options=re.findall(r'(?m)^- \*\*[A-D]\*\*\.\s*(.+)',qregion)
        if len(options)!=20:raise ValueError('Expected 20 explicit options for shared passage')
        missing=[o for o in options if norm(o) not in norm(source_questions)]
        if missing:raise ValueError('Source question/option mismatch: '+str(missing))
        passage=re.sub(r'材料([一二三])(?=[^\s\n：:])',r'### 材料\1\n\n',passage)
        if group==2:
            example='该系统能带来近六千吨的碳减排，相当于近6000辆普通的燃油车不眠不休从北京穿越3700 千米的路程到达乌兰巴托。'
            if example not in passage:raise ValueError('Unique underlined example missing')
            passage=passage.replace(example,'<u>'+example+'</u>',1)
        relsource=source.relative_to(OWNER_ROOT).as_posix()
        url='https://github.com/ProfessorZhi/gwy-material-ops/blob/main/'+quote(relsource,safe='/')
        note='> 同题材料来源：'+source.name+'；四海课程题本，原稿未单列材料整理作者。已逐项核对本组5道题的20个选项。保留原稿标号与填空；页眉、页码不作为正文。'
        if group==1:note+=' 原稿的Ⅰ—Ⅳ标号用于辨识题目所指各句。'
        section='## 材料 '+str(group)+'（第'+str(first)+'—'+str(last)+'题共用）\n\n'+passage+'\n\n'+note+'\n\n[固定原稿文件位置]('+url+')\n\n'
        additions.append((old.index('## 第 '+str(first)+' 题'),section))
        rows.append({'path':TARGET,'question_numbers':list(range(first,last+1)),'source_path':relsource,'source_url':url,'source_sha256':sha(raw),'passage_sha256':sha(clean(raw[a:b])),'source_passage':clean(raw[a:b]),'matched_option_count':len(options),'transform':'Remove page artifacts; add material headings and locate the unique example sentence; preserve source passage text.'})
    new=old
    for at,section in sorted(additions,reverse=True):new=new[:at]+section+new[at:]
    new=set_fields(new,{'北京同题共用材料补录凭据':'reports/FULL-REPAIR-BEIJING-MATERIALS-20261015.json','现仍缺失共用材料题号':[79,80]},'2026-10-15按用户保存的同题课程原稿恢复第22—31题两组共用阅读材料，20项选择文本逐一核对。')
    p.write_text(new,encoding='utf-8',newline='\n')
    (ROOT/'reports/FULL-REPAIR-BEIJING-MATERIALS-20261015.json').write_text(json.dumps({'path':TARGET,'before_sha256':sha(old),'after_sha256':sha(new),'groups':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'shared_material_groups_restored':len(rows),'questions_covered':10,'still_unverified_material_questions':[79,80]},ensure_ascii=False))
if __name__=='__main__':main()
