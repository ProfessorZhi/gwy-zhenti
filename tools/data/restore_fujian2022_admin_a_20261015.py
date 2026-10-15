import json,re,sys,hashlib,uuid,os
from pathlib import Path
from urllib.parse import quote
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tools'))
import round5_bulk as b
from full_repair_answers_20261015 import validate_answer,render_answer
from full_repair_layout_20261015 import format_essay
sha=lambda t:hashlib.sha256(t.encode()).hexdigest();src=json.loads((R/'tools/data/fujian2022-admin-public-source-a-20261015.json').read_text(encoding='utf8'));raw=src['text'];at=raw.rfind('三、作答要求');assert at>1000;pre=raw[:at];qreg=raw[at:];ms=list(re.finditer(r'(?m)^材料([1-4])\s*$',pre));assert len(ms)==4
mats=[pre[m.end():ms[i+1].start() if i+1<len(ms) else None].strip().removesuffix('三、').strip() for i,m in enumerate(ms)];hs=list(re.finditer(r'(?m)^([1-4])\.',qreg));assert len(hs)==4
qs={i+1:qreg[m.start():hs[i+1].start() if i+1<4 else None].split('注：篇幅有限')[0].strip() for i,m in enumerate(hs)}
rel='省考/福建/2022/申论-行政执法.md';p=R/rel;old=p.read_text(encoding='utf8');d=b.parse(old,rel)
def main(a):return re.split(r'文章分析|参考答案说明|\n\s*>\s*(?:出处|来源说明)|\n\s*\[本题(?:既有)?来源记录\]',a,1)[0].strip()
answers={1:main(d['answers'][2]),2:main(d['answers'][1]),3:'''这句话强调，法官应以人民需求为导向，既公正裁判，又兼顾多方利益、延伸审判职能，不能就案论案。

一、答好判断题，依法查明事实、分清是非。庭前研究卷宗和法律问题，庭中充分听取诉辩，庭后规范说理论证；必要时现场勘验，确保裁判质量和司法公信。

二、答好多选题，兼顾合法权益与纠纷实质化解。鸭毛纠纷中，明确处理义务，说明鉴定成本，开展耐心调解，综合考虑经济负担、邻里关系和法律效果，避免机械办案。

三、答好论述题，将个案审理延伸为制度完善和源头治理。针对跨域取证难建立协同机制，提高审理效率；梳理事故多发路段并提出治理建议，推动隐患预防。

答好每一道题，就是以专业严谨的作风和为民初心守护公平正义，让群众获得实实在在的司法服务。''',4:'''以标准化、数字化、协同化提升市域综治效能

各位领导、各位同仁：

D市坚持强平台、强队伍、强协商，推动市域社会综合治理现代化，主要做法如下：

一、建设实战化综治中心。推进各级中心标准化建设、实体化运行，专职政法委员入驻办公，公安、司法、民政等责任单位远程或派员入驻，依托视联网提供专家远程指导，增强协同处置能力。

二、以数据贯通提升治理能力。开发四级贯通的综治“9+X”系统，融合网格化管理、物联网，建设一体化管控平台；整合50余家部门数据，打造云数据中心。建立基础信息库，实现业务下派、督办、通报、考核闭环，强化动态感知、预警预防和科学决策。

三、推动政法力量下沉。建立机关党员干部下沉一线长效机制，组织法官、检察官、警官等担任兼职网格员，明确十大职责，设置工作纪实、建议和考核模块，推动责任落地。

四、强化网格人才培养。依托政法学院建立网格学院，吸纳专家、实务人才及一线网格员任教，开设三类课程，建设现场教学基地，形成培训、科研、咨询体系。

五、完善多元协商共治。实现“一组一会”全覆盖，吸纳党员、居民、网格员参与，将议事落实为现场解决；推行党组织领导下居委会、业委会、物业公司“四位一体”模式，动员成员参与巡防，化解基层矛盾。

下一步，我们将继续夯实基层基础，让数据赋能、干部下沉与群众参与形成合力。

谢谢大家！'''}
# The existing references are retained in full in the before-image; only reviewed
# compression is used if their newly restored real task limit requires it.
answers[1]=answers[1].replace('共同研究论证','共同论证').replace('相关情况分别上报本市主管部门','分别上报主管部门').replace('未来更加紧密','更加紧密')
metrics=[];rendered={}
for n,q in qs.items():
 e=dict(answer=answers[n],attribution_kind='ai_original' if n>=3 else 'ai_revision' if n==1 else 'owned_source',author='AI辅助原创示范；依据本卷材料独立编写' if n>=3 else 'AI辅助修订示范；所据原稿见旧版凭据' if n==1 else '库内既有同题参考版本；个人作者未署名',sources=[dict(title='同年同卷完整题面及给定资料',url=src['url'])])
 if n<3:e['sources'].append(dict(title='库内原有参考版本（固定基线）',url='https://github.com/ProfessorZhi/gwy-zhenti/blob/f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab/'+quote(rel,safe='/')))
 if n==1:e['replace_reason']='恢复实际300字要求后精简重复措辞，保留跨区域合作三方面措施。'
 nc=validate_answer(q,e);metrics.append(dict(number=n,characters=nc,kind=e['attribution_kind'],answer_sha256=sha(answers[n])));rendered[n]=render_answer(e)
text='---\n'+''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in {'考试':'省考','地区':'福建','年份':'2022','科目':'申论','卷型':'行政执法','真题性质':'机构整理/考生回忆真题，非官方原件','命题形式':'多省联考','来源':['同年机构完整题面','库内已有同题参考稿'],'来源整卷':src['url'],'来源整卷SHA256':sha(raw),'实有题数':4,'对照题本题量':4,'题目分值':[20,20,25,35],'缺失原题号':[],'给定材料段数':4,'已收录参考答案题号':[1,2,3,4],'缺参考答案题号':[],'题号口径':'同年完整执法卷4题原序；旧源序两题校准为原第1/2题','校验状态':'2026-10-15按同年完整卷恢复4材料和4题100分，补两份明确署名的AI原创示范，非官方逐字认证','恢复凭据':'reports/FULL-REPAIR-FUJIAN-2022ADMIN-A-20261015.json'}.items())+'---\n# 2022年福建省公务员考试申论（行政执法）\n\n[同年完整题面来源]('+src['url']+')\n\n'
text+='## 考试注意事项\n\n'+pre[:ms[0].start()].replace('二、给定材料','').strip()+'\n\n'
for i,m in enumerate(mats,1):text+='## 给定资料 '+str(i)+'\n\n'+m+'\n\n'
text+='## 作答要求\n\n'
for n,q in qs.items():text+='## 第 '+str(n)+' 题\n\n'+q+'\n\n'
text+='## 答案与解析\n\n'
for n in qs:text+='<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+rendered[n]+'\n\n</details>\n\n'
text=text.replace('不代表官方答案或真实实考高分卷','不是官方答案，也不代表真实实考高分卷');text,layout=format_essay(text,rel);nd=b.parse(text,rel);assert len(nd['questions'])==4 and len(nd['answers'])==4
rp=R/'reports/FULL-REPAIR-FUJIAN-2022ADMIN-A-20261015.json';assert not rp.exists();record=dict(path=rel,before_sha256=sha(old),before_text=old,after_sha256=sha(text),source_url=src['url'],source_title=src['title'],source_sha256=sha(raw),questions=4,materials=4,points=[20,20,25,35],answers=metrics,old_to_real=[dict(old_number=1,new_number=2),dict(old_number=2,new_number=1)],layout=layout)
rp.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp=p.with_name(p.name+'.fjadmin-'+uuid.uuid4().hex+'.tmp');tmp.write_bytes(text.encode());assert sha(p.read_text(encoding='utf8'))==sha(old);os.replace(tmp,p);assert sha(p.read_text(encoding='utf8'))==sha(text);print(json.dumps({k:v for k,v in record.items() if k!='before_text'},ensure_ascii=False))
