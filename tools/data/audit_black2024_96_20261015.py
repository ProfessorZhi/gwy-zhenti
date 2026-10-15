"""Record a newly discovered source-truncated choice. Never invent its missing wording."""
from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[2]
p=R/'省考/黑龙江/2024/行测-统考.md';t=p.read_text(encoding='utf8')
m=re.search(r'(?m)^## 第 96 题.*?(?=^## 第 97 题)',t,re.S)
base=Path('D:/projects/gwy-material-ops/knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【省考】2000-2025真题pdf/【11】黑龙江公务员考试真题pdf版')
srcs=[]
for s in base.rglob('*2024*行测*.md'):
 st=s.read_text(encoding='utf8');start=st.find('中国式现代化的区域实践')
 if start>=0 or '选项不完整，内容待补充' in st:
  srcs.append({'path':str(s),'sha256':hashlib.sha256(st.encode()).hexdigest(),'finding':'题本D同为“中国式现代化区域······实现现代化”' if start>=0 else '解析也明确D选项不完整'})
out={'paper':p.relative_to(R).as_posix(),'question':96,'qid':11881048,'issue':'D选项原文截断；原参考解析也承认待补充','status':'unresolved_source_truncation','before_sha256':hashlib.sha256(t.encode()).hexdigest(),'after_sha256':hashlib.sha256(t.encode()).hexdigest(),'question_sha256':hashlib.sha256(m[0].encode()).hexdigest(),'current_D':'中国式现代化区域······实现现代化','retained_answer':'C（仅作原回忆版本参考，D未恢复前不能宣称完整单选题已认证）','private_sources':srcs,'public_sources':[{'url':'https://www.xingguanggongkao.com/Mobile/Ques/view/id/49282.html','title':'中国式现代化的区域实践遵循区域经济发展的一般规律','retrieved':'2026-10-15','finding':'星光公考2025-04-10同题，A/B/C与库一致，D明确“暂缺”；未取得完整D。'},{'url':'http://theory.people.com.cn/n1/2023/1003/c40531-40088948.html','title':'中国式现代化区域实践的三重逻辑','retrieved':'2026-10-15','evidence_level':'search_excerpt_only','finding':'命题素材写“生命力”；回忆题干写“生产力”。素材不是原试卷，不能擅改回忆题干；改回可能影响B/C排他性。'}],'action':'保留原题、原选项及来源参考解析；只补可审计缺项记录，不编造原题D，不以删除待核文字压低告警。'}
(R/'reports/FULL-REPAIR-APTITUDE-BLACK2024-96-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'status':out['status'],'private_sources':len(srcs)},ensure_ascii=False))
