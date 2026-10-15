import sys,re
from pathlib import Path
root=Path(__file__).resolve().parents[2]
for arg in sys.argv[1:]:
 p=root/arg;t=p.read_text(encoding='utf8');t=re.sub(r'<!--[\s\S]*?-->','',t)
 t=t.split('---',2)[-1];t=re.sub(r'## 参考作答与范文导读[\s\S]*?(?=> 申论)','',t)
 if '\n## 答案与解析' in t:t=t.split('\n## 答案与解析')[0]
 print('\nPATH',arg);print(t)
