"""Refresh only this agent's reports against frozen priority MDs."""
import sys,subprocess,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[2];py=sys.executable
scripts=['priority_essay_inventory_six_regions_20261015.py','priority_essay_fingerprints_20261015.py','priority_essay_question_map_20261015.py','build_priority_six_regions_audit_20261015.py','audit_priority_question_counts_20261015.py','audit_national_jiangzhe_counts_20261015.py']
logs=[]
for s in scripts:
 result=subprocess.run([py,str(R/'tools/data'/s)],cwd=R,capture_output=True,encoding='utf-8',errors='replace')
 logs.append({'command':[py,'tools/data/'+s],'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
 if result.returncode:raise RuntimeError((s,result.stdout,result.stderr))
 print('REFRESH_OK',s,flush=True)
stock=json.loads((R/'reports/PRIORITY-ESSAY-SIX-REGIONS-STOCK-20261015.json').read_text(encoding='utf-8'));audit=json.loads((R/'reports/PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.json').read_text(encoding='utf-8'));count=json.loads((R/'reports/PRIORITY-ESSAY-QUESTION-COUNT-AUDIT-20261015.json').read_text(encoding='utf-8'));nj=json.loads((R/'reports/NATIONAL-JIANGZHE-TASK-COUNT-AUDIT-20261015.json').read_text(encoding='utf-8'))
files=['PRIORITY-ESSAY-SIX-REGIONS-STOCK-20261015.json','PRIORITY-ESSAY-SIX-REGIONS-FINGERPRINTS-20261015.json','PRIORITY-ESSAY-SIX-REGIONS-QUESTION-MAPS-20261015.json','PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.json','PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.md','PRIORITY-ESSAY-QUESTION-COUNT-AUDIT-20261015.json','NATIONAL-JIANGZHE-TASK-COUNT-AUDIT-20261015.json','NATIONAL-JIANGZHE-TASK-COUNT-AUDIT-20261015.md']
for name in files:
 path=R/'reports'/name;data=path.read_bytes();path.write_bytes(data.replace(b'\r\n',b'\n'))
summary={'status':'passed','six_region_stock_files':len(stock),'six_region_missing_real_types':audit['confirmed_missing_count'],'six_region_year_area_rows':audit['area_year_rows'],'six_region_task_count_discrepancies':len(count['confirmed_count_discrepancies']),'national_jiangzhe_files':nj['files_scanned'],'national_jiangzhe_named':nj['named_papers'],'national_files':nj['national_files'],'national_jiangzhe_task_count_discrepancies':len(nj['unresolved_count_discrepancies']),'national_jiangzhe_catalog_missing':[x['path'] for x in nj['same_year_catalog_unavailable']],'only_identity_pending':[(x['area'],x['year'],x['identity_pending']) for x in audit['rows'] if x['identity_pending'] and x['status']!='separate_exam_unconfirmed']}
report={'summary':summary,'commands':logs,'report_sha256':{f:hashlib.sha256((R/'reports'/f).read_bytes()).hexdigest() for f in files},'frozen_md_sha256':{x['path']:hashlib.sha256((R/x['path']).read_bytes()).hexdigest() for x in stock},'boundary':'Priority MDs frozen by root before refresh. Counts prove only actual task-container/catalog consistency, not full official source authenticity; missing whole papers remain missing.'}
(R/'reports/PRIORITY-ESSAY-FINAL-REFRESH-20261015.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8'));print(json.dumps(summary,ensure_ascii=False,indent=2))
