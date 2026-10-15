from pathlib import Path
import re,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sha=lambda t:hashlib.sha256(t.encode('utf8')).hexdigest()
records=[]
def write(rel,fn,why,sources):
 p=ROOT/rel;old=p.read_text(encoding='utf8');new=fn(old);assert new!=old
 records.append(dict(path=rel,before_sha256=sha(old),after_sha256=sha(new),reason=why,sources=sources));p.write_text(new,encoding='utf8',newline='\n')
def guo(t):
 front,ans=t.split('## 答案与解析',1)
 qpat=r'(^## 第 12 题[^\n]*\n)(.*?)(?=^## )'
 m=re.search(qpat,front,re.S|re.M);body=m[2]
 assert '- **B**. 预备役人员从事个体经营，可以按照国家有关规定享受出资优惠政策' in body
 assert '- **C**. 缺失' in body
 body=body.replace('享受出资优惠政策','享受融资优惠政策').replace('- **C**. 缺失','- **C**. 预备役人员退出预备役的，其预备役军衔予以收回')
 body+='> 2026-10-15校对：依据展鸿同卷题本补回C项，并纠正B项“出资”为“融资”；答案随题面版本联动纠正为C。\n\n'
 front=front[:m.start()]+m[1]+body+front[m.end():]
 pat=r'(<details>\s*<summary>第 12 题</summary>)(.*?)(</details>)';m=re.search(pat,ans,re.S)
 body='''\n\n**答案**：C

**原创校核解析（AI辅助整理，非官方标准答案）**

本题要求选出错误表述。A项符合《预备役人员法》第四十三条；B项的“融资优惠”符合第四十六条；D项的两类预备役军官划分符合第十三条。第十五条规定，退出预备役后原军衔予以保留并加注退役性质，因此C项“予以收回”与规定相反，应选C。

**校对来源**：[展鸿2024国考副省级题本](https://static.32xueyuan.com/zq/u/cms/www/202410/09100412q9dd.pdf)，第12题；[《人民日报》刊载的《预备役人员法》](https://paper.people.com.cn/rmrb/images/2023-02/17/10/rmrb2023021710.pdf)，第十三、十五、四十三、四十六条。来源答案与法规校核一致。原库B项误转为“出资”、C项缺失，原答案B依据错误题面形成，本次联动替换。

'''
 ans=ans[:m.start()]+m[1]+body+m[3]+ans[m.end():]
 return front+'## 答案与解析'+ans
write('国考/2024/行测-副省级.md',guo,'补C项、纠B项转录、按法规与完整题本重核答案C',['https://static.32xueyuan.com/zq/u/cms/www/202410/09100412q9dd.pdf','https://paper.people.com.cn/rmrb/images/2023-02/17/10/rmrb2023021710.pdf'])
def west(t):
 front,ans=t.split('## 答案与解析',1);pat=r'(^## 第 96 题[^\n]*\n)(.*?)(?=^## )';m=re.search(pat,front,re.S|re.M)
 body=m[2];body,n=re.subn(r'(?m)^- \*\*A\*\*\.\s*$','- **A**. 酒精在体内的代谢产物乙醛可以稳定地附着在DNA分子上，导致癌变或者突变',body,count=1);assert n==1
 body+='> 选项A据[星光公考同题](https://www.xingguanggongkao.com/pc/wb/quesView/id/10637.html)补录（2026-10-15）；与本卷已有A项解析的代谢产物致癌机制吻合。\n\n'
 return front[:m.start()]+m[1]+body+front[m.end():]+'## 答案与解析'+ans
write('省考/西藏/2016/行测-统考.md',west,'补回第96题空白A选项，原答案A及解析无需改动',['https://www.xingguanggongkao.com/pc/wb/quesView/id/10637.html'])
def js(t):
 pat=r'(<details>\s*<summary>第 110 题</summary>)(.*?)(</details>)';m=re.search(pat,t,re.S);assert '暂以B项代替' in m[2]
 body='''\n\n**答案状态**：尚无可核验答案。

**版本纠错**：旧源明确写“题目缺失，正在征集，暂以B项代替”，B只是来源占位默认值。本题四个选项仍缺，不能据默认字母判分，现撤销错误的答案B。已找到公考通与星光公考同题卷入口，但尚未取到可核对的四幅选项图，仍需补齐原图后独立判断。

**对照来源**：[公考通2024江苏C卷](https://www.chinagwy.org/files/20241206160947_16977.pdf)，第110题。不同题库版本题号可能不同，应按“驳岸”完整题干匹配，不只按数字套答案。

'''
 return t[:m.start()]+m[1]+body+m[3]+t[m.end():]
write('省考/江苏/2024/行测-C类.md',js,'撤销缺失选项题的来源默认答案B，保留真实待补状态',['https://www.chinagwy.org/files/20241206160947_16977.pdf'])
Path(ROOT/'reports/FULL-REPAIR-APTITUDE-OPTIONS-20261015.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
labels=[]
for area in ['国考','省考']:
 for p in (ROOT/area).rglob('行测*.md'):
  old=p.read_text(encoding='utf8');new=old.replace('**官方解析**','**来源参考解析（非官方标准答案）**')
  if new==old:continue
  labels.append(dict(path=p.relative_to(ROOT).as_posix(),before_sha256=sha(old),after_sha256=sha(new),replacements=old.count('**官方解析**')));p.write_text(new,encoding='utf8',newline='\n')
(ROOT/'reports/FULL-REPAIR-APTITUDE-LABELS-20261015.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'content_repairs':len(records),'label_files':len(labels),'labels':sum(x['replacements'] for x in labels)},ensure_ascii=False))
