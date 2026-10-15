import sys,re,json,os,subprocess,hashlib
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import full_repair_answers_20261015 as a
MOPS=ROOT.parent/'gwy-material-ops';REV='95676de3a494730fdcacd43416fd51d6bed48ab6'
base=MOPS/'knowledge/gwy/001【公务员国省考】/资料包/【000】历年国省考真题/【国考】2000-2025真题pdf/2000-2025国考申论PDF'
out=[]
for name,rel,kind in [('2020年国家公务员考试《申论》真题及答案（省级）.pdf.md','国考/2020/申论-副省级.md','ai_revision'),('2020年国家公务员考试《申论》真题及答案（地市级）.pdf.md','国考/2020/申论-地市级.md','owned_source')]:
    p=base/name;source_rel=p.relative_to(MOPS).as_posix();env=dict(os.environ,GIT_CONFIG_GLOBAL='NUL',GIT_CONFIG_NOSYSTEM='1')
    raw=subprocess.check_output(['git','-c','core.fsmonitor=false','show',REV+':'+source_rel],cwd=MOPS,env=env,timeout=90)
    assert raw.decode().replace('\r\n','\n')==p.read_text(encoding='utf8')
    body=p.read_text(encoding='utf8').split('### 5、参考答案：')[-1];body=re.sub(r'<!--.*?-->','',body,flags=re.S).strip()
    if kind=='ai_revision':
        body=body.replace('海纳百川聚四方之才尊敬的各位来宾：大家好！','海纳百川 聚四方之才\n\n尊敬的各位来宾：\n\n大家好！',1).replace('负责人XXX','负责人').replace('很荣幸能在此高端人才会上和大家交流','很荣幸在此与大家交流').replace('给与资源倾斜','给予资源倾斜')
    else:body=body.replace('莱康村参选乡村治理先进典型的推荐材料莱康村','莱康村参选乡村治理先进典型的推荐材料\n\n莱康村',1)
    out.append({'path':rel,'number':5,'answer':body,'attribution_kind':kind,'author':'AI辅助校订；依据同题未署名来源完整正文' if kind=='ai_revision' else '同题来源参考；原稿未署答文作者','sources':[{'title':name+'（固定已核Git版本）','url':'https://github.com/ProfessorZhi/gwy-material-ops/blob/'+REV+'/'+quote(source_rel,safe='/')}],'source_blob_sha256':hashlib.sha256(raw).hexdigest(),'replace_reason':'旧库只收录部分段落；依同题完整原稿补回政策与项目、结语，并校订称谓及少量措辞' if kind=='ai_revision' else '旧库断于“最美家”，现依据同题完整来源恢复德治、集体活动、经济发展及结语，正文与原稿一致'})
body='''致社会各界朋友的公开信

社会各界朋友们：

近日，我局就某中学食堂蔬菜过度挑选问题发出《责令改正通知书》，并约谈当事人，引发社会关注。大家既关心厉行节约，也担忧食品安全。我们理解家长的心情，感谢各界监督。反对食品浪费与保障食品安全，应当共同落实，决不能以节约之名降低任何人的食品安全标准。

节约粮食是全社会的责任。粮食供求存在矛盾，食物浪费又造成经济损失和环境负担。反食品浪费法已经实施，学校更应在勤俭节约方面发挥育人作用。我局开展监管，初衷是推动珍惜粮食、物尽其用。此次发出的是责令改正通知书，不能笼统等同于已经实施了罚款处罚；具体执法事实与适用依据，我们将认真复核并及时说明。

同时，我们正视大家提出的问题。菜叶有虫眼、颜色变化，不能仅凭外观就一概断定安全或不安全，更不能靠执法人员主观感觉认定浪费。学校对食材质量的顾虑应得到尊重。对于“员工内部消化”“定向捐赠”等建议，也必须以符合食品安全要求为前提，不能把风险转嫁给其他群体。执行标准不清、捐赠渠道不畅，是需要切实解决的问题。

下一步，我们将做好以下工作：

一、核实情况，依法规范处理。认真听取学校、家长和专业人员意见，结合食材实际状态、储存条件等调查取证，严格按照法定权限和程序办事。对处置中不准确、不恰当的做法及时纠正，对公众关注的问题及时回应，防止简单套用条文、机械搬用经验。

二、细化标准，提高执法水平。结合本地情况和实际需要，推动制定科学、具体、可操作的反食品浪费办法，充分征求社会意见。加强执法培训，统一判断尺度，坚持具体问题具体分析，既依法制止浪费，也守住食品安全底线，避免“一刀切”和形式主义。

三、完善服务，畅通合理利用渠道。会同有关方面探索规范的食品捐赠平台和制度，明确可捐条件、交接流程与责任，帮助食堂减少采购、储存、加工等环节的损耗。对不符合食品安全要求的食材，绝不能建议食用或捐赠。

四、共建共治，培育节约风尚。加强普法宣传，鼓励食堂科学备餐、适量供应，引导用餐者按需取餐，支持社会监督。我们将耐心倾听诉求、持续改进工作，让执法既有力度，也有温度。

厉行节约需要法治保障，也需要理解和参与。诚邀各界继续提出意见，与我们共同营造安全、节约、文明的用餐环境。

G市市场监管局
XXXX年XX月XX日'''
out.append({'path':'国考/2022/申论-行政执法.md','number':5,'answer':body,'attribution_kind':'ai_revision','author':'AI辅助修订，依本题材料5重写完整公开信','sources':[],'replace_reason':'旧稿仅483字、只列第一项改进措施，未达到800—1000字要求；补齐回应争议、标准细化、安全底线、捐赠机制与公众参与，并区分责令改正和罚款'})
(ROOT/'tools/data/root-national-missing-bodies-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for r in out:print(r['path'],a.answer_characters(r['answer']))
