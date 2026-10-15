"""Repair 2023 first-paper answers after restoring the actual first-paper tasks."""
import json
from pathlib import Path
from full_repair_answers_20261015 import apply_entries
ROOT=Path(__file__).resolve().parents[1]
REL='省考/深圳/2023/申论-一卷.md'
ANSWERS=[
    (1,'一、压实责任，健全机制，投入资金，聚焦群众急难愁盼。二、教育帮扶，企校双师定向培养技能人才，结对支教、培训师资。三、消费帮扶，政府引导、市场主导、社会参与，采购产品、发消费券，建特色基地、育品牌、推认证，搭建电商平台。四、旅游帮扶，挖掘红色和生态资源，创新产业模式。'),
    (2,'致全球投资者的一封信\n\n尊敬的全球投资者：\n\n鹏城向世界发出诚挚邀约！深圳新一届全球招商大会即将举行，我们诚邀各位相聚深圳，共话合作、共谋发展。\n\n深圳是创新创业的热土，也是携手成长的沃土。这里市场活跃、产业基础扎实，优良的营商环境为各类经营主体发展壮大提供有力支撑。2022年全球招商大会引进315个重大项目、签约8790亿元，既是全球投资者投下的信任票，也是我们深化合作的新起点。\n\n面向未来，深圳前瞻布局战略性新兴产业和未来产业，持续汇聚创新资源，拓展产业协作空间。我们将拿出宝贵资源支持优质企业和项目落地，做好用地等要素保障，提供便捷高效的服务，让企业安心投资、专心经营、舒心发展。\n\n无论您来自哪里，都欢迎带着项目、技术与创意走进深圳。期待与您现场交流投资需求，寻找合作伙伴，把发展机遇转化为合作成果，在开放共赢中共享中国式现代化的新机遇。\n\n相约鹏城，携手向未来！期待您的到来。\n\n深圳全球招商大会组委会\nXXXX年XX月XX日')]
def main():
    entries=[{'path':REL,'number':n,'answer':answer,'attribution_kind':'ai_original','author':'AI辅助原创整理','replace_reason':'原合卷文件曾误取二卷题目；按一卷显式作答要求恢复后补写同题作答','sources':[{'title':'修复前固定合卷题面','url':'https://github.com/ProfessorZhi/gwy-zhenti/blob/f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab/'+__import__('urllib.parse',fromlist=['quote']).quote(REL,safe='/')}]} for n,answer in ANSWERS]
    result,receipts=apply_entries(ROOT,entries)
    if result['status']!='passed':raise ValueError(result)
    (ROOT/'tools/data/full-repair-shenzhen-2023-20261015.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'reports/FULL-REPAIR-SHENZHEN-2023-20261015.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in receipts),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
