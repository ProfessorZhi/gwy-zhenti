"""Record the accepted scope and explicit residual source boundaries."""
import hashlib,json,os,re,uuid
from pathlib import Path
import round5_bulk as parser
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def write(p,text):
    temp=p.with_name(p.name+'.scope-'+uuid.uuid4().hex+'.tmp')
    try:temp.write_bytes(text.encode());os.replace(temp,p)
    finally:
        if temp.exists():temp.unlink()
def main():
    national=[]
    for year in range(2016,2027):
        expected=['副省级','地市级']+(['行政执法'] if year>=2022 else [])
        for variant in expected:
            rel=f'国考/{year}/申论-{variant}.md';p=ROOT/rel
            if p.exists():
                text=p.read_text(encoding='utf-8');d=parser.parse(text,rel)
                national.append({'year':year,'variant':variant,'path':rel,'state':'collected','sha256':sha(text),'tasks':len(d['questions']),'question_keys':{str(n):parser.qkey(q) for n,q in d['questions'].items()}})
            else:national.append({'year':year,'variant':variant,'path':rel,'state':'missing'})
    result={'scope_confirmed':'用户2026-10-15确认：2016至2026国考及浙江、江苏、上海、北京、天津、广东、福建，含广州深圳市考；其他省份维护已有内容质量。','national_expected_variants':27,'national_collected':sum(r['state']=='collected' for r in national),'national':national,'classification_evidence':[{'url':'http://hangzhou.offcn.com/html/2021/10/74352.html','supports':'2022起新增行政执法类，三类公共科目试卷'},{'url':'https://www.ncss.cn/ncss/zt/2026gk.shtml','supports':'2026三类职位分类测查'}],'boundary':'File and task inventory, not official-original authentication. Duplicate provincial buckets and yearly no-exam cases are adjudicated separately.'}
    write(ROOT/'reports/FULL-REPAIR-SCOPE-NATIONAL-20261015.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    changes=[]
    specs=[('省考/北京/2025/行测-统考.md',{'当前收录边界':'93道公开回忆题片段；未取得完整原卷及资料分析部分','已收录参考答案题号':[n for n in range(1,94) if n not in (56,57,58,79,80)],'现仍缺失共用条件题号':[56,57,58,79,80]},'> **当前收录边界：** 本页为93道公开回忆题片段，尚缺原卷其他部分。88题已有参考作答；第56—58题缺操作符定义，第79—80题缺共用日程条件，继续待补，不以偏移答案键猜填。'),('省考/黑龙江/2016/申论-C卷：县乡.md',{'原材料完整性':'尚有两处来源缺段；已有答案不代表题面齐全','原材料缺段说明':['材料二“加盖厂房”前缺失段首','材料三“无讼、以和为贵”传统文化处原源标部分资料暂缺']},'> **材料校勘边界：** 已补回可核对的9处材料内容与编号，但材料二“加盖厂房”前及材料三“无讼、以和为贵”处仍有原来源缺段。现有参考作答依据可读材料编写，不能据此宣称题面完整。')]
    specs.append(('省考/黑龙江/2024/行测-统考.md',{'缺失选项题号':[96],'选项缺失校核凭据':'reports/FULL-REPAIR-APTITUDE-BLACK2024-96-20261015.json'},'> **题面校勘边界：** 第96题D项在现存题本、解析和公开同题源中均不完整。保留C作为原回忆版本参考，D项恢复前不作完整单选题认证。'))
    for rel,fields,notice in specs:
        p=ROOT/rel;old=p.read_text(encoding='utf-8')
        if notice in old:continue
        new=set_fields(old,fields,'2026-10-15明确当前收录内容及仍缺原始条件；历史来源状态仅作修复前记录。')
        title=re.search(r'(?m)^# [^\n]+\n',new);new=new[:title.end()]+'\n'+notice+'\n'+new[title.end():]
        if p.read_text(encoding='utf-8')!=old:raise ValueError('Concurrent edit')
        write(p,new.rstrip()+'\n');changes.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new.rstrip()+'\n')})
    if changes:write(ROOT/'reports/FULL-REPAIR-RESIDUAL-NOTICES-20261015.json',json.dumps(changes,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'national_variants':len(national),'collected':result['national_collected'],'residual_notices':len(changes)}))
if __name__=='__main__':main()
