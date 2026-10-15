"""Author-reviewed B-region answer packets and reversible question-layout repairs."""
import hashlib,html,json,re,sys,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'tools/data/full-repair-essay-b-20261015.json'
GAPS=Path('D:/artifacts/essay_b_gaps.json')

def sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def repair_layout():
    receipts=[]
    rel='省考/陕西/2024/申论-B类.md';p=ROOT/rel;old=p.read_text(encoding='utf-8');new=old
    new=re.sub(r'(问题[一二三四]：[^\n]+\n\n)([ \u3000]*（1）)',r'\1　　要求：\n\2',new)
    if new!=old:
        receipts.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'operations':[{'old':old,'new':new}],'reason':'前四题已有完整作答限制但缺要求标签；只补结构标记，不改原题文字。'})
        p.write_text(new,encoding='utf-8',newline='\n')
    rel='省考/黑龙江/2017/申论-统考.md';p=ROOT/rel;old=p.read_text(encoding='utf-8');new=old
    if '作答要求一、根据给定材料2' in new:
        new=new.replace('作答要求一、根据给定材料2','\n\n## 作答要求\n\n## 第 1 题\n\n一、根据给定材料2',1)
        for n,cn in [(2,'二'),(3,'三'),(4,'四')]:
            needle={'二':'二、根据给定资料3-4','三':'三、假如你是某市文明办','四':'四、就个体而言'}[cn]
            new=new.replace(needle,f'\n\n## 第 {n} 题\n\n'+needle,1)
        receipts.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'operations':[{'old':old,'new':new}],'reason':'原题四道题及要求挤在材料6末段，按环球网校和51上岸同材料题面交叉核对后恢复题目标题和段落；未补造题干。','sources':['https://www.hqwx.com/gjgwy-kaoshi/news/15011469571765.html','https://www.51shangan.top/index.php?a=index&aid=453&c=View&m=home']})
        p.write_text(new,encoding='utf-8',newline='\n')
    if receipts:(ROOT/'reports/FULL-REPAIR-ESSAY-B-LAYOUT-20261015.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in receipts),encoding='utf-8')
    print('layout repairs',len(receipts))

def put(short,n,answer,sources=None,bounds=None,kind='ai_original',author='Codex（AI辅助原创示范）'):
    rel='省考/'+short.rsplit('/',1)[0]+'/申论-'+short.rsplit('/',1)[1]+'.md'
    rows=json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else []
    import round5_bulk as parser
    paper=parser.parse((ROOT/rel).read_text(encoding='utf-8'),rel)
    row={'path':rel,'number':n,'question':paper['questions'][n],'answer':answer.strip(),'attribution_kind':kind,'author':author,'sources':sources or []}
    if bounds:row['target_word_range']=bounds
    if any((r['path'],r['number'])==(rel,n) for r in rows):raise ValueError('duplicate '+short+':'+str(n))
    rows.append(row);DATA.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(short,n,len(re.sub(r'\s','',answer)))

if __name__=='__main__':repair_layout()
