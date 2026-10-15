"""Record examined source leads without converting summaries into fictitious papers."""
import sys,json,csv,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_repair_essay_a_20261015 import ROOT
base=json.loads((ROOT/'reports/FULL-REPAIR-MISSING-PAPERS-20261015.json').read_text(encoding='utf8'))
lead={
'云南':['https://www.huatu.com/yngwy/shiti/xl/','http://www.yngwy.org/category/67.html','https://www.132gk.com/web/exercise/shenlun/exam'],
'内蒙古':['https://www.huatu.com/nmgwy/shiti/xl/','https://www.aipta.com/zt/sk/nm/sl/','https://www.eoffcn.com/kszx/detail/1619190.html'],
'北京':['https://www.huatu.com/bjgwy/shiti/xl/','https://www.aipta.com/zt/sk/bj/sl/','https://rsj.beijing.gov.cn/bm/ztzl/gwy/'],
'吉林':['https://www.aipta.com/zt/sk/jl/sl/','https://jl.huatu.com/gwy/shiti/slzt/','http://www.jlgwyks.cn/'],
'宁夏':['https://www.aipta.com/zt/sk/nx/sl/','https://www.huatu.com/nxgwy/shiti/xl/'],
'山东':['https://www.aipta.com/article/1444.html','https://www.163.com/dy/article/KG9R4DQG05459BTA.html'],
'广西':['https://gx.huatu.com/guojia/ziliao/sl/','https://www.bohuigk.com/news/19/'],
'新疆':['http://www.xjgwyw.org/category/67.html','https://www.aipta.com/zt/sk/xj/','https://rst.xinjiang.gov.cn/xjrst/c112678/zfxxgk_gknrz.shtml'],
'河北':['https://www.aipta.com/zt/sk/hb/sl/','https://www.huatu.com/hegwy/shiti/xl/'],
'海南':['https://hi.huatu.com/gwy/','https://www.rsks.cn/ziliao/shenlun/'],
'深圳':['https://www.eoffcn.com/kszx/detail/1208330.html','https://hrss.sz.gov.cn/szksy/ztzl/gwyks/'],
'湖北':['https://www.gemu.cn/hbgwy/skkm/','https://ah.huatu.com/zt/hbgwy/ksgg/'],
'甘肃':['https://www.aipta.com/zt/sk/gs/sl/','http://www.gsgwy.org/category/67.html','http://gs.huatu.com/gwy/shiti/slzt/'],
'陕西':['https://www.aipta.com/zt/sk/sa/sl/','http://www.shanxigwy.org/category/67.html'],
'青海':['https://www.aipta.com/zt/sk/qh/sl/','https://m.kaosheng.com/down/show.php?itemid=4411','http://qhpta.org.cn/ncms/gwyks.shtml'],
'黑龙江':['https://www.huatu.com/hljgwy/shiti/xl/','http://www.hljgwy.org/category/67.html'],
'浙江':['https://www.eoffcn.com/kszx/detail/1029502.html','https://www.132gk.com/web/exercise/shenlun/exam'],
}
records=[]
for x in base:
 if x['subject']!='申论':continue
 r={k:x[k] for k in ('area','year','subject','registered_path')};r.update({'state':'未取得可核验的完整原卷，未生成真题','source_leads':lead.get(x['area'],[]),'existing_exam_evidence':x.get('evidence_url',''),'existing_evidence_note':x.get('note',''),'new_paper_added':False})
 r['source_boundary']='搜索命中不等于题面；营销目录、教材、模拟卷、国考卷、节选与题型解读均不冒充该省年完整真题。'
 if x['year']=='2026' and x['area'] in ('云南','内蒙古','北京'):r['finding']='华图标题为2026，但正文是旧栏目/推广入口，没有可提取当年完整题面。'
 if x['area']=='浙江':r['finding']='中公同年解读证实综合类主题及三题类型，但缺全部材料、精确题干与字数；132动态按年/地区均无该卷可见。排除把2021科技创新改年的展鸿PDF。'
 if x['area']=='深圳':r['finding']='招录年度口径需复核：中公历史表2020后为2022（公告发布于2021）；2026搜索命中广东省考及2025深圳专项，未取得独立深圳该年原卷。未据此断言未开考。'
 if x['area']=='西藏':r['finding']='沿用C代理核验的开考证据，开考不等于取得原卷；无完整题面不能构造试卷。'
 records.append(r)
payload={'date':'2026-10-15','scope':'原57格中35个申论省年格','cells_checked':len(records),'complete_new_papers_admitted':0,'method':'TinyFish search/fetch_content, two bounded read-only browser runs on 132, existing GitHub source snapshots and owned materials filenames','browser_runs':[{'run_id':'7f999c86-6485-4706-9a81-045cf50bf623','target':'2026云南申论','result':'当前132可见库中无此卷；不推导考试未举行'},{'run_id':'12d5593a-ec65-4fa3-8b19-9000173117fe','target':'2022浙江各类申论','result':'按年份与地区筛选无可提取原卷'}],'owned_files_check':'用户省考PDF资料包中浙江2022、吉林2024/2025、内蒙2025只见行测文件，无对应申论；教师source-index未找到这些年省完整专卷。','records':records}
(ROOT/'reports/FULL-REPAIR-ESSAY-MISSING-SOURCE-A-20261015.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
out=io.StringIO();w=csv.DictWriter(out,fieldnames=['area','year','subject','state','finding','source_leads']);w.writeheader()
for r in records:w.writerow({k:('; '.join(r[k]) if isinstance(r.get(k),list) else r.get(k,'')) for k in w.fieldnames})
(ROOT/'reports/FULL-REPAIR-ESSAY-MISSING-SOURCE-A-20261015.csv').write_text(out.getvalue(),encoding='utf8')
print(json.dumps({k:v for k,v in payload.items() if k not in ('records',)},ensure_ascii=False,indent=2))
