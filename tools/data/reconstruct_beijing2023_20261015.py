import json,re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import beijing_shenlun_inventory_20261015 as b
import round5_bulk as parser
from difflib import SequenceMatcher
from urllib.parse import quote
p=b.R/'省考/北京/2023/申论-统考.md';old=p.read_text(encoding='utf-8');d=parser.parse(old,str(p));s=next(b.SOURCE_BASE.glob('*2023*'));raw=s.read_text(encoding='utf-8')
# Page numbers attached to first line are removed only when identical to page marker.
t=re.sub(r'<!-- page: (\d+) -->\s*\n\s*\1\s*', '\n\n',raw)
t=b.clean_source(t);m=t[t.index('### 材料1'):t.index('## 三、作答要求')].strip()
q=t[t.index('## 三、作答要求'):t.index('2023 年北京市公考《申论》题（解析）')];ms=list(re.finditer(r'(?m)^## ([一二三四])、[ \t]*$',q));assert len(ms)==4
qs={n+1:re.sub(r'\*\*','',q[z.end():ms[n+1].start() if n+1<4 else len(q)]).strip() for n,z in enumerate(ms)}
mapping=[]
for n,donor in enumerate([3,2,1,4],1):
 sim=SequenceMatcher(None,parser.qkey(qs[n]),parser.qkey(d['questions'][donor]),autojunk=False).ratio();assert sim==1,(n,sim)
 mapping.append({'number':n,'old_number':donor,'old_question':d['questions'][donor],'new_question':qs[n],'qkey_similarity':sim,'old_answer':d['answers'][donor]})
url='https://github.com/ProfessorZhi/gwy-material-ops/blob/'+b.REVISION+'/'+quote(s.relative_to(b.M).as_posix(),safe='/')
header=old[:old.index('\n---',4)+4];header=re.sub(r'题号口径:[^\n]+','题号口径: "按完整同年题本顺序1–4；原3/2/1/4依次映射"',header)
out=[header,'# 2023年北京市公务员考试申论（统一试卷）','',f'> 依照[用户完整同卷题本]({url})恢复统一的六段材料编号、原卷题序及材料引用；旧文件将材料局部分段重编号，现统一回原卷“材料4–6”“材料6”。原参考作答逐题原文保留；完整旧文件及映射见 `reports/FULL-REPAIR-BEIJING-2023-20261015.json`。题本编制机构／作者未明确，非官方发布认证。','','## 给定材料','',b.readable(m),'','## 作答要求','']
for n in range(1,5):out += [f'## 第 {n} 题','',b.readable(qs[n]),'']
out += ['## 答案与解析','']
for n,e in enumerate(mapping,1):out += [f'<a id="r7-reference-{n}"></a>','<details>',f'<summary>第 {n} 题</summary>','',e['old_answer'].strip(),'','</details>','']
new='\n'.join(out);newd=parser.parse(new,str(p));assert len(newd['questions'])==len(newd['answers'])==4
p.write_text(new,encoding='utf-8')
(b.R/'reports/FULL-REPAIR-BEIJING-2023-20261015.json').write_text(json.dumps({'status':'passed','path':p.relative_to(b.R).as_posix(),'source':url,'source_sha256':b.sha(raw),'before_sha256':b.sha(old),'before_text':old,'after_sha256':b.sha(new),'mapping':mapping,'materials_source':m,'materials_source_numbers':[1,2,3,4,5,6]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('2023 normalized to original 4 task order and 6-material numbers; 4 answers unchanged.')
