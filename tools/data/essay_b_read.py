import html,re,sys,unicodedata
from pathlib import Path
R=Path(__file__).resolve().parents[2]
short=sys.argv[1];a=short.split('/');p=R/'省考'/a[0]/a[1]/('申论-'+a[2]+'.md')
t=unicodedata.normalize('NFKC',html.unescape(p.read_text(encoding='utf-8')))
markers=list(re.finditer(r'(?:^|\n)\s*(?:材料|资料)\s*([一二三四五六七八九十\d]+)\s*[:：、]?\s*\n',t))
nums=sys.argv[2:]
if not markers:print(t)
for i,m in enumerate(markers):
 n=m[1];digit=str('一二三四五六七八九十'.index(n)+1) if n in '一二三四五六七八九十' else n
 if not nums or digit in nums:
  end=markers[i+1].start() if i+1<len(markers) else (t.find('作答要求',m.end()) if t.find('作答要求',m.end())>0 else len(t))
  print(t[m.start():end])
