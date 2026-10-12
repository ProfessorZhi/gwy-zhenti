#!/usr/bin/env python3
"""Report actual R8 originals separately from internet institutional answers and score claims."""
from __future__ import annotations
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
import round4_gap_repair as g
import r7_delivery as r7
from r7_reference_audit import assess
from verify_round8_repairs import verify,records
ROOT=g.ROOT

def main():
 stats=verify(ROOT);rr=records(ROOT)
 summary_path=ROOT/'reports/REPAIR-SUMMARY-20261013-R8.json'
 summary=json.loads(summary_path.read_text(encoding='utf-8'))
 if stats['new_original_versions']!=summary['authored_answer_versions']:raise ValueError('Summary mismatch')
 state=collections.Counter();rows=[];bad=[];paths=sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')])
 for p in paths:
  rel=p.relative_to(ROOT).as_posix()
  try:d=r7.parse(p.read_text(encoding='utf-8'),rel)
  except Exception as e:bad.append({'path':rel,'reason':str(e)});continue
  for n,q in d['questions'].items():
   a=assess(q,d['answers'].get(n,''));state[a['kind']+'/'+a['status']]+=1
   rows.append({'path':rel,'number':n,'type':a['kind'],'status':a['status']})
 if len(paths)!=738 or len(bad)!=9:raise ValueError('Entire essay scope is no longer 738/9')
 missing=sum(v for k,v in state.items() if k.endswith('/待补'))
 warnings=sum(v for k,v in state.items() if k.endswith('/正文偏短待复核') or k.endswith('/正文或图像待复核'))
 available=sum(v for k,v in state.items() if k.endswith('/已收录'))
 if missing+warnings+available!=len(rows):raise ValueError('Task count changed')
 earlier=json.loads((ROOT/'reports/REPAIR-SUMMARY-20261013-R7.json').read_text(encoding='utf-8'))['actual_coverage']
 if missing!=earlier['missing_reference_answer_positions']-stats['newly_filled_positions']:
  raise ValueError('The exact number of filled blanks is inconsistent')
 quality=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
 counts={'status':'verified','corpus_essay_documents':len(paths),'parsed':len(paths)-len(bad),'unparsed':len(bad),
  'known_answer_positions':len(rows),'available_reference_positions':available,
  'missing_reference_positions':missing,'needs_text_layout_review':warnings,
  'missing_example_essays':state['作文范文/待补'],
  'new_original_reference_versions':stats['new_original_versions'],
  'original_newly_filled_positions':stats['newly_filled_positions'],
  'original_full_essay_versions':stats['new_full_essay_versions'],
  'full_corpus_machine_flags':quality['files_with_machine_flags'],
  'boundary':'AI-authored educational examples; these are not independently scored high-mark essays.'}
 (ROOT/'reports/REPAIR-SUMMARY-20261013-R8.json').write_text(
   json.dumps({**summary,'status':'verified','verification':stats,'actual_coverage':counts},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 paper_rows=[]
 for r in rr:
  rel=r['path'];paper_rows.append({'path':rel,'new':[(a['number'],a['mode'],a['type']) for a in r['added_answers']]})
 lines=['# 第八轮：按给定材料原创的参考作答与作文范文','',
  '> 文中新增9个参考版本是基于本库题干和材料撰写的AI原创学习示范；不冒充其他机构原文，也不宣称真实考场得分。网络链接仅用于同题对照阅读。','',
  '| 指标 | 已验证内容 |','|---|---:|',
  '| 本轮新增参考版本 | '+str(stats['new_original_versions'])+' |',
  '| 真正补齐既有空位 | '+str(stats['newly_filled_positions'])+' |',
  '| 完整作文示范范文 | '+str(stats['new_full_essay_versions'])+' |',
  '| 实际修改既有试卷MD | '+str(len(rr))+' |',
  '| 最新缺完整参考作答 | '+str(missing)+' |',
  '| 其中缺作文范文 | '+str(state['作文范文/待补'])+' |',
  '| 既有答案篇幅/正文待复核 | '+str(warnings)+' |',
  '| 可靠解析申论 | '+str(len(paths)-len(bad))+' / '+str(len(paths))+' |','',
  '## 具体写回题号','',
  '| 试卷 | 写回情况 |','|---|---|']
 for r in rr:
  p=r['path'];parts=[]
  for a in r['added_answers']:
   title='作文示范范文' if a['type']=='作文范文' else '小题参考作答'
   parts.append(f"第{a['number']}题{'填空' if a['mode']=='fill' else '新增第二版本'}（{title}）")
  lines.append('| ['+p+'](../'+quote(p,safe='/')+') | '+'；'.join(parts)+' |')
 lines+=['','## 质量边界与作答标准','',
  '对于小题，重点核对指向材料、要点覆盖、分析逻辑、文种和字数；对于作文，重点评估中心论点、材料衔接、论证层次、实际政策可行性和完整结尾。',
  '此次稿件全部明示AI原创示范，原有机构范文和参考作答仍完整保留，不替换更早的版本。每一处修改有文档前后SHA-256、可逆差异、题干锚点和原有答案保护记录。',
  '高分范文可以作为学习目标，但未经评分证据不得冒称真实得分；对于新示范稿，建议读者独立批改、与机构同题版本对照。',
  '',
  '历史资料缺卷、行测缺题和申论未解析事项不因本批作文/答案增加而自动消失。',
  '',
  '[最新申论覆盖统计](REPAIR-SUMMARY-20261013-R8.json) · [逐文件可逆凭据](ROUND8-AUTHORED-20261013.jsonl) · [上轮全库逐题清单](ROUND7-COVERAGE-20261013.json)']
 (ROOT/'reports/QUALITY-REPAIR-20261013-R8.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 p=ROOT/'PROGRESS.md';cur=p.read_text(encoding='utf-8');base=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True,encoding='utf-8')
 m=re.search(r'(?m)^## 第三轮：',base)
 if m:cur=re.sub(r'\n## 第三轮：[\s\S]*\Z','',cur).rstrip()+'\n\n'+base[m.start():].rstrip()+'\n'
 cur+='\n## 第八轮：缺项原创建模与作文对照（2026-10-13）\n\n'
 cur+='基于本库同题给定材料原创9个学习参考版本，7处为原缺答案，3篇为完整作文范文。所有新增均声明为AI原创示范、无真实评分认证，原机构答案保留。\n\n'
 cur+='最新已识别申论缺答案位置'+str(missing)+'处、缺作文范文'+str(state['作文范文/待补'])+'处，另外'+str(warnings)+'处正文/篇幅需复核，9份结构未解析。\n\n'
 cur+='[第八轮完整逐题变更](reports/QUALITY-REPAIR-20261013-R8.md) · [最新机器验收数字](reports/REPAIR-SUMMARY-20261013-R8.json)\n'
 p.write_text(cur,encoding='utf-8')
 print('R8_ACTUAL_COVERAGE',json.dumps(counts,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
