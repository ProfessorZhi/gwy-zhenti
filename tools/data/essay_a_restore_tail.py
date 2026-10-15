import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_essay_a_20261015 import ROOT
rel='省考/广西/2025/申论-B类.md';p=ROOT/rel;old=p.read_text(encoding='utf8')
if '（4）字数800-1000字' not in old:
 new=old.rstrip()+'\n\n　　（3）思路清晰，语言流畅；\n\n　　（4）字数800-1000字。\n\n> 题面补全记录（2026-10-15）：原收录在第4题要求第2项后截断；经[同题公开题面](https://gwy.gkzhenti.cn/paper/1748833072513)与[爱真题同题页](https://www.aipta.com/article/10188.html)交叉核对，补回第3、4项要求。公开页面属回忆整理版本。\n'
 rec={'path':rel,'before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(new.encode()).hexdigest(),'old_tail':old[-800:],'added_requirements':['（3）思路清晰，语言流畅；','（4）字数800-1000字。'],'sources':['https://gwy.gkzhenti.cn/paper/1748833072513','https://www.aipta.com/article/10188.html']}
 (ROOT/'reports/FULL-REPAIR-ESSAY-A-TOPIC-RESTORE-20261015.json').write_text(json.dumps([rec],ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 p.write_text(new,encoding='utf8',newline='\n')
 print('RESTORED',rel)
