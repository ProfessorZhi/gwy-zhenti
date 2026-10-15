"""Specific, falsifiable source audit for five missing Jiangsu/Zhejiang variants."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
def src(url,title,result,kind='checked_page'):
 return dict(url=url,title=title,result=result,kind=kind)
zj=[
 src('https://static.32xueyuan.com/zq//u/cms/zj/202411/07163021u9x9.pdf','展鸿教育2021～2024浙江申论考情分析','TinyFish读取PDF全文：表中2022 A/B/C直接标“民生建议（缺）”，未给题目、分值或题本；2021与2023/24均有具体题型。这是机构公开整理尚缺2022的实质证据，不推论真题不存在。','institution_pdf_missing_entry'),
 src('https://gx.huatu.com/2021/1101/1772759.html','2022年浙江省各级机关单位考试录用公务员公共科目考试大纲','全文确认申论A综合、B基层、C执法；D为综合应用能力。同年大纲依据，不含真题。','institution_reprint_of_exam_authority'),
 src('https://www.aipta.com/zt/sk/zj/sl/','爱真题浙江申论历年目录','读取完整目录：2021后直接2023；2022-11-04是2020/2021等旧卷上传日期，没有2022ABC题本。'),
 src('https://www.132gongkao.com/','132公考浙江/2022筛选','TinyFish运行12d5593a-ec65-4fa3-8b19-9000173117fe终态未取得浙江2022真实省考题本。仅证明该次可见目录无全文，不推断全网不存在。','live_browser_search'),
 src('http://www.houzhiwang.com/html/202012/74196.html','厚职2022浙江申论真题标题','页面发表于2020-12-20，正文写尚未考试/尚未发布，旧年下载营销入口不是2022真题。','excluded_placeholder'),
 src('http://www.zggwy.org/zjgwy/448052.html','浙江省考申论考情分析（2022-11-18）','历史考情明确2022AB考民生、C考数字赋能，能交叉核主题与卷型，没有给定材料/完整题干。','historical_exam_analysis'),
]
js=[
 src('https://www.suzhou.gov.cn/szsrmzf/gwyjsydwklxx/202510/5db8eab43b324856be70dc743b7fa4c6.shtml','江苏省2026年度公共科目笔试考试大纲','政府站全文确认A/B/C各有申论；乡镇选调同A。仅用于分卷存在和科目身份，不含真题。','official_syllabus'),
 src('https://www.aipta.com/zt/sk/js/sl/','爱真题江苏申论历年目录','读取目录最新2025ABC，未列2026；不能拿2025冒充2026。'),
 src('https://www.fenbi.com/fpr/doc-user-v2/dir/23059','粉笔江苏历年考卷合集','TinyFish运行cf3431e4-9ff4-4c3c-92d0-d848f73eb76a完成：14个可见文件均2022/2023，没有2026。fetch空内容后已真实浏览核实。','live_browser_directory'),
 src('http://www.js.xinhuanet.com/20251208/1ecfd2b4afbd4daa8d84ea62c20d662e/c.html','43.8万人赶考2026年度江苏省公考公共科目笔试','考后报道确认2025-12-07考试和ABC；A卷涉及品牌/标准与中国式现代化/高质量发展。不含整套材料。','post_exam_news'),
 src('https://www.huatu.com/jsgwy/shiti/xl/','华图江苏申论真题目录','“2026”栏目标题没有返回目标A/C完整题本；不将宣传标题计收录。','catalogue_not_fullpaper'),
]
rows=[]
for v in 'ABC':
 s=list(zj)
 if v=='A':
  s += [src('https://www.eoffcn.com/kszx/detail/1029502.html','中公2022浙江综合类申论试题解读','真实考后解读确认三题：充电桩问题建议、小微企业帮扶经验发言提纲、为民生办实事文章。无全部材料和逐题字数，不构造残缺真卷。','institution_same_exam_analysis'),src('https://static.32xueyuan.com/zq/u/cms/zj/202212/07183022bn59.pdf','展鸿标2022浙江A PDF','C代理核文认定实际2021科技创新材料错标2022，排除；不得导入作2022A。','excluded_misdated_paper')]
 rows.append(dict(region='浙江',year=2022,variant=v,status='real_variant_confirmed_fullpaper_not_obtained',checks=s,remaining='需同年同卷完整给定材料、原题与作答要求；主题片段不足导入。'))
for v in 'AC':
 s=list(js)
 if v=='A':s += [src('https://www.bilibili.com/video/BV1ffMk63E19/','三好申面：2026年江苏省考申论A卷第二题','公开页面确认同题讲解存在；正文仅标题/作者与相关推荐，没有可转录的给定材料或完整题干。','teacher_video_partial'),src('https://yyxz.cust.edu.cn/xzlljs/zl/3196847faa534b808d895dfbb280189e.htm','史为恒：申论命题的现代视野（应用写作杂志）','作者单位江苏师大文学院；文章明确引述2026A第四题品牌/标准写作任务及资料8，可核题目身份，但没有完整材料/字数要求/前三题。','signed_academic_analysis')]
 else:s += [src('https://www.bilibili.com/video/BV1FfMk6GEcj/','三好申面公开视频相关推荐','可见关联视频“2026年江苏省考申论C卷第四题：领导讲啥我干啥，小小山村赚到麻”，仅题名与05:40时长，没有C卷全文。','teacher_video_lead_only')]
 rows.append(dict(region='江苏',year=2026,variant=v,status='real_variant_confirmed_fullpaper_not_obtained',checks=s,remaining='需同年同卷完整给定材料、原题与作答要求；不能以B卷或模考代替。'))
out=dict(date='2026-10-15',browser='TinyFish only; no OpenCLI',scope='用户确认的重点省份中，浙江2022ABC和江苏2026AC五张真实分卷',result='5张分卷身份明确，尚未取得可完整导入题面；没有生成真题',papers=rows,excluded_wrong_year_official_urls=[{'url':'http://gwy.zjks.gov.cn/zjgwy/website/queryDetail.htm?mkxh=2&tzid=7523','actual':'2023大纲；不能用于2022身份'},{'url':'http://gwy.zjks.gov.cn/zjgwy/website/queryDetail.htm?mkxh=2&tzid=7502','actual':'2023宁波公告；2022年发布不等于2022考试'}],owned_local_search='MOPS2000-2025省考PDF浙江文件夹、教师packet及上游gongkao-tiku年度JSON未检出目标2022浙江真实全卷；2026江苏不能从旧年合集冒充。',public_share_lead={'url':'https://docs.feishu.cn/article/wiki/A7dZw3JfhihQIikUUF4c62Hnned','title':'国省市考（2026）','finding':'公开页有分省目录标题但无具体目标文件；指向夸克分享正在只读核验','run_id':'1e8270dc-a563-421c-bb47-a829721bdaaf'})
out['public_share_lead'].update(status='completed_directory_only_no_target_file_verified',finding='TinyFish真实浏览到【02】省考真题/1.公务员省考真题及答案到26/，可见江苏到26和浙江到26各3项；未进入省子目录，未核到任何目标具体文件。出现扫码/手机验证码登录弹窗和步骤预算限制。目录到26不能证明内含2022浙江或2026江苏缺卷；不记为找到题本。',share_url='https://pan.quark.cn/s/6b05756a32a0',run_duration_seconds=197,visible_share_file_count=26452)
(ROOT/'reports/FULL-REPAIR-FOCUS-5-PAPERS-A-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Wrote 5 individually auditable rows, each with >=2 concrete source checks.')
