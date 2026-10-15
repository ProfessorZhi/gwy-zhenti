import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import round5_bulk as p,full_repair_precise_answer_audit_20261015 as audit
rows=[]
for rel,n in [('省考/浙江/2023/申论-A类.md',3),('省考/深圳/2024/申论-二卷.md',3),('省考/黑龙江/2023/申论-行政执法卷.md',4)]:
 d=p.parse((ROOT/rel).read_text(encoding='utf8'),rel);old=d['answers'][n];body=audit.extract_versions(old)[0]['body']
 if '/浙江/' in rel:
  anchor='人生有千百次选择'
  assert anchor in body
  body=body.replace(anchor,'保障合理报酬、打通成长通道，才能让基层岗位既有价值感，也有可持续的吸引力。\n\n'+anchor,1)
  why='剥除署名后原作文997字略低于1000字下限；补足基层就业保障与价值实现的联系，保留全文论证'
 elif '/深圳/' in rel:
  body=body.replace('之路事非经过','之路\n\n事非经过',1)
  assert '增强操作全系统技术能力' in body
  body=body.replace('增强操作全系统技术能力','增强关键核心技术攻关能力',1)
  anchor='一年之计在于春，乘势而上正当时，迎着春光奔跑'
  assert anchor in body
  paragraph='把信心转化为底气，还要形成改革落实的闭环。营商环境的改善，不能只看出台了多少政策，更应看企业办事是否便捷、合法权益能否得到有效保护；民生服务的进步，也应由群众的实际体验来检验。坚持听取企业和居民意见，对改革中的堵点及时协调、对实施效果持续评估，才能让创新举措从纸面走进生活，让每一次具体进步累积成稳定的发展预期。\n\n'
  body=body.replace(anchor,paragraph+anchor,1)
  why='原文1012字未充分接近1200字目标；补入与法治化营商环境、民生改革对应的落实论证，分开粘连标题并校正“操作全系统”明显错词'
 else:
  a='以往，个体工商户需按期到服务大厅办理营业执照的年检业务，错过年检，则会影响正常经营。'
  assert a in body
  body=body.replace(a,'以往，企业办理生鲜乳收购、种畜禽生产经营等许可延续，需要自行准备材料、到部门申请；疏忽了有效期限，还可能影响正常经营。',1)
  why='原参考例子将材料中的经营许可证续办误写成营业执照年检，现据本卷资料4校正对象，避免张冠李戴'
 urls=re.findall(r'\[([^\]]+)\]\((https://[^)]+)\)',old)
 rows.append({'path':rel,'number':n,'answer':body,'attribution_kind':'ai_revision','author':'AI辅助修订；逐题对照材料与篇幅要求','sources':[{'title':a,'url':u} for a,u in urls[:2]],'replace_reason':why})
(ROOT/'tools/data/root-final-bodies-20261015.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for row in rows:print(row['path'],audit.char_count(row['answer']))
