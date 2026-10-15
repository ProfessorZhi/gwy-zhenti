import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
base=Path(r'D:\projects\gwy-material-ops\knowledge\gwy\001【公务员国省考】\资料包\【000】历年国省考真题\【省考】2000-2025真题pdf\【26】天津公务员考试真题pdf版')
files=[]
for p in sorted(base.rglob('*2024*')):
 if p.is_file():files.append(dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
checks=[
dict(url='https://gs.huatu.com/2024/0122/1737098.html',kind='institution_reprint_of_same_year_syllabus',finding='华图2024-01-22解读明确市区、乡镇街道、行政执法申论分别命制；有同年卷型依据但不含考后真题。'),
dict(url='https://www.aipta.com/zt/sk/tj/sl/',kind='exam_catalogue',finding='2024仅市区卷article/9871，2023有乡镇/执法，2025有街镇，不能跨年替代。'),
dict(url='https://www.kkgwy.com/stk/tj/14940.html',kind='exam_catalogue',finding='已读整页汇总：2023乡镇/执法后为2024市区，未见2024街镇/执法全文。'),
dict(url='https://www.yfzxmn.com/examTab_get.action?so_Id=340&su_Id=5',kind='exam_catalogue_access_restricted',finding='可读列表2024仅市区，正文提示未在学校IP授权范围；没有尝试绕过。'),
dict(url='https://www.huatu.com/tjgwy/shiti/xl/',kind='year_label_without_exam_body',finding='页面标题虽2024，正文仅5条栏目记录/备考推荐，无两套目标题本。'),
dict(url='https://www.132gk.com/web/exercise/shenlun/exam',kind='completed_live_browser_search',run_id='f2afc56b-b374-4e90-b85a-efd1e0e608bf',duration_seconds=184,finding='2024+天津筛选无结果；可见2026天津执法不能用作2024。此结论仅限本次可见目录，非全网不存在。'),
dict(url='http://word.baidu.com/view/b14a36b37d21af45b307e87101f69e314332fab9.html',kind='unverified_document_candidate',finding='搜到2024天津执法标题，但TinyFish fetch empty_content，未取得材料和题目，未采纳。'),
]
rows=[dict(region='天津',year=2024,variant=v,status='missing_full_paper',identity='same_year_syllabus_confirms_distinct_category',checks=checks,reason='未取得可核对的全部给定材料及逐题要求，不能生成真题或将市区卷复制改名。') for v in ['街镇','行政执法']]
out=dict(date='2026-10-15',task='天津2024街镇及行政执法分卷查源',new_papers_created=0,rows=rows,local_2024_files=files,local_teacher_content_search='reports/FULL-REPAIR-TIANJIN2024-TEACHER-CONTENT-HITS-A-20261015.json；源包内2024天津仅市级完整题本，其他命中为2025材料提及天津2024活动，不是2024卷。',upstream_search='D:/projects/_gwy-upstream 和 _gwy-upstream-v2 文件名检索仅 SLB 天津2024市区卷；gongkao-tiku y2024.json递归卷名中没有天津。',boundary='题库缺项不能以地区合卷、旧年真卷、国考天津考区、模考或生成材料清零。')
(ROOT/'reports/FULL-REPAIR-TIANJIN2024-MISSING-VARIANTS-A-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'new_papers_created':0,'missing_variants':['街镇','行政执法'],'source_checks_per_variant':len(checks),'local_2024_files':len(files)},ensure_ascii=False))
