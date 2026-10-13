"""Conservative removal of teacher PDF layout and point annotations, never answer generation."""
import re
from source_supplement_20261013 import cleaned
def teacher_cleaned(text):
 text=cleaned(text)
 text=re.sub(r"(?m)^\s*\d{1,3}\s*$","",text)
 text=re.sub(r"天晓(?:2025\s*)?\s*申论批改班第\s*\d+\s*期\s*\d{0,2}","",text)
 text=re.sub(r"《申论解题思维趣学营》\s*\d{1,2}","",text)
 text=re.sub(r"\d?认准批改班唯一更新微信号：[\s\S]*?其余都是骗子！！！","",text)
 text=re.sub(r"题目讲练","",text)
 text=re.sub(r"历年真题组卷\s*[（(][一二三四五六七八九十]+[）)]","",text)
 text=re.sub(r"[（(][^()（）]{0,180}\d+\s*分[^()（）]{0,180}[）)]","",text)
 text=re.sub(r"【\d+\s*分[^】]*】","",text)
 return text
