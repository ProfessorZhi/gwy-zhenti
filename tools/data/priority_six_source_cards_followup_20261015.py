"""Append compact, directly relevant verified evidence cards; no full page republication."""
from pathlib import Path
import json,hashlib
P=Path(__file__).with_name('priority-six-regions-source-evidence-20261015.json')
d=json.loads(P.read_text(encoding='utf8'))
new=[
 {'url':'http://www.tjgwyw.org/2018/1220/24369.html','title':'2017滨海新区等单位专项申论网络整理题本','retrieved':'2026-10-15','status':'verified_by_peer_report','evidence_excerpt':'六段材料6367规范字与完整原卷逐字一致，四题及要求分值对应；PDF去页眉页码后亦一致。','interpretation':'__t443是真实独立2017-12-23专项卷，身份待核解除，不作为普通4月卷补充。','peer_evidence':'reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json'},
 {'url':'https://www.eol.cn/gongwuyuan/difang/skzx/201711/t20171127_1569596.shtml','title':'2017年滨海新区等单位招考公务员考试大纲','retrieved':'2026-10-15','status':'verified_by_peer_report','evidence_excerpt':'中国教育在线2017-11-27转载天津市人社局专项大纲：申论150分钟100分。','interpretation':'同年独立专项证据，区别于普通4月联考。','peer_evidence':'reports/FULL-REPAIR-TIANJIN-2017-BINHAI-IDENTITY-20261015.json'},
 {'url':'http://www.tjgwyw.org/2022/0224/38404.html','title':'2022天津公务员公共科目考试大纲解读','retrieved':'2026-10-15','status':'verified_by_peer_report','evidence_excerpt':'当年分综合管理市级、综合管理区级以下、行政执法三类。','interpretation':'两完整三题卷与两倒序片段逐题材料核清后，实际只覆盖前两类；行政执法真实另缺。','peer_evidence':'reports/FULL-REPAIR-TIANJIN-2022-IDENTITY-20261015.json'},
 {'url':'https://www.eoffcn.com/kszx/detail/1229673.html','title':'2021—2023上海公务员考试申论考情简析','retrieved':'2026-10-15','status':'fetched','evidence_excerpt':'2022｜A类｜政府与市场关系；B类｜一体化高质量发展。2023｜A类｜基层治理；B类｜建设科创中心。','interpretation':'当年AB各独立主题。上海2023统考唯一作文为基层治理，即A题，不能用来覆盖科创中心B卷。'},
 {'url':'https://www.huatu.com/2024/1107/2787521.html','title':'2025天津市公务员考试公共科目考试大纲','retrieved':'2026-10-15','status':'fetched','evidence_excerpt':'市级和区级机关综合管理类职位;乡镇街道综合管理类职位;行政执法类职位的申论试题分别命制。','interpretation':'三类申论分别命题，市区/街镇8题并桶不等于包含执法卷。'},
 {'url':'https://i.offcn.com/c/1822756','title':'上海执法类公务员历年试题【无解析-限查看题型】','retrieved':'2026-10-15','status':'browser_verified_unavailable','evidence_excerpt':'课程已下架；公开页面未显示具体历年文档下载或预览。','interpretation':'TinyFish单站实测，不能将搜索缓存的2021/2024申论PDF条目计作已取得原文；未购买/登录。','browser_run_id':'52dbbce7-8d93-4c4b-b1c4-89629d61ea3e'},
 {'url':'https://www.bilibili.com/video/BV1fJP3eYE2x/','title':'（满分小题如何抄）2024深圳申论一真题讲解（第1题）','author':'申论小盐姐','published':'2025-02-25 12:53:26','retrieved':'2026-10-15','status':'browser_verified_video_unplayable','evidence_excerpt':'视频标题明确2024深圳申论一第1题，合集另列一二通用大作文；播放器未能加载。','interpretation':'元数据和公开目录能验证存在；视频PPT/字幕不可读取，未取得原题全文，不能移植Ⅱ类前两题充数。','browser_run_id':'a1f484ab-76be-43bf-825a-e570c9df1f32'},
]
urls={x['url'] for x in new};d=[x for x in d if x['url'] not in urls]+new
for x in d:
 x.pop('retained_evidence_sha256',None);x.pop('hash_scope',None)
 x['retained_evidence_sha256']=hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 x['hash_scope']='retained metadata/excerpt/catalog; not the full remote response'
P.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('cards',len(d),'bytes',P.stat().st_size)
