"""Build the current inventory and an honest scoped repair report."""
import argparse,collections,json,shutil
from pathlib import Path
import cloud_quality as cq
from full_repair_current_audit_20261015 import audit
ROOT=Path(__file__).resolve().parents[1]
def load(name):return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8'))
def save(name,data):(ROOT/'reports'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',action='store_true');args=ap.parse_args()
    current=audit()
    if current['status']!='passed':raise ValueError('Current answer audit failed: '+json.dumps(current,ensure_ascii=False))
    six=load('PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.json')
    jz=load('FULL-REPAIR-JIANGZHE-VARIANT-INVENTORY-A-20261015.json')
    beijing=load('FULL-REPAIR-BEIJING-ESSAY-INVENTORY-20261015.json')
    gaps=[{'area':r['area'],'year':r['year'],'variant':r['type'],'source_urls':r.get('source_urls',[])} for r in six['confirmed_missing']]
    for row in jz['rows']:
        gaps.extend({'area':row['region'],'year':row['year'],'variant':v,'evidence_report':'FULL-REPAIR-JIANGZHE-VARIANT-INVENTORY-A-20261015.json'} for v in row['missing_named_variants'])
    if beijing['missing_full_papers']!=1:raise ValueError('Reconcile changed Beijing inventory before release')
    gaps.append({'area':'北京','year':2026,'variant':'统一卷','evidence_report':'FULL-REPAIR-BEIJING-ESSAY-INVENTORY-20261015.json'})
    if len(gaps)!=six['confirmed_missing_count']+jz['missing_real_variants']+beijing['missing_full_papers']:raise ValueError('Variant inventory counter mismatch')
    rows,stats=cq.scan(ROOT,False)
    if stats['hard_integrity_errors'] or stats['forbidden_tracked_files']:raise ValueError('Native integrity errors: '+str(stats['hard_integrity_errors']))
    totals=collections.Counter(r['area'] for r in gaps)
    snapshot={'date':'2026-10-15','scope_complete':False,'scope':'2016–2026国考及浙江江苏上海北京天津广东福建，含广州深圳；其他省份仅维护已有质量','current_essay_markdown_files':current['essay_papers'],'readable_answer_positions':sum(current['classifications'].values()),'current_answer_audit':current,'native_summary':stats,'confirmed_missing_real_papers':len(gaps),'missing_real_papers_by_area':dict(sorted(totals.items())),'missing_real_papers':gaps,'confirmed_missing_original_aptitude_questions':stats['confirmed_missing_original_questions'],'missing_aptitude_shared_condition_questions':stats['confirmed_missing_shared_condition_questions'],'missing_option_questions':stats['confirmed_missing_option_questions'],'missing_material_segments':stats['confirmed_material_gap_segments'],'boundary':'Current Markdown/answer positions are not unique real exams or verified exam scores. Confirmed missing real papers and unavailable original source text remain unresolved; machine pass does not mean zero content defects.'}
    save('FULL-REPAIR-CURRENT-ANSWERS-20261015.json',current)
    save('FULL-REPAIR-20261015.json',snapshot)
    lines=['# 2026-10-15 题库修复与真实缺口验收','',
           '**目标尚未全部达成。** 现存可识别申论作答位置已有完整主作答，重点范围仍有 '+str(len(gaps))+' 份已确认真实漏卷未取得完整题面；原始要求与来源残缺单列，不能用答案收录率替代原卷完整率。','',
           '验收范围：2016—2026国考，浙江、江苏、上海、北京、天津、广东、福建，含广州、深圳市考；其他省份维护已有内容质量。','',
           '| 当前项目 | 结果 |','|---|---:|',
           f"| 当前申论 MD 文件 | {current['essay_papers']} |",
           f"| 可读参考作答位置 | {sum(current['classifications'].values())} |",
           f"| 未解析申论 / 已识别作答空位 | {len(current['unparsed'])} / {len(current['incomplete_recognized_tasks'])} |",
           f"| 新增或修订正文逐题检查 | {current['new_or_revised_answer_bodies_checked']} |",
           f"| 实际主文篇幅／占位强制检查错误 | {len(current['precise_body_errors'])} |",
           f"| 含旧版本或原题限制待复核的位置 | {current['precise_body_candidate_tasks']} |",
           f"| 已确认仍漏真实申论整卷 | {len(gaps)} |",
           f"| 已确认仍缺行测原题 | {stats['confirmed_missing_original_questions']} |",
           f"| 行测共用条件未恢复 / 选项不全 | {stats['confirmed_missing_shared_condition_questions']} / {stats['confirmed_missing_option_questions']} |",
           f"| 行测题干主图 / 关键条件未恢复 | {stats['confirmed_missing_stem_figure_questions']} / {stats['confirmed_missing_stem_condition_questions']}（可为同一道题） |",
           f"| 黑龙江2016申论来源材料仍缺段 | {stats['confirmed_material_gap_segments']} |",'',
           f"明确登记的来源解析争议：{stats['declared_source_analysis_disagreement_questions']}题，见原卷正文；不因补全公式就将原题条件歧义算作解决。",'',
           '文件数和作答位置包含历史来源桶及跨省同题，不能当独立真卷去重数。正文可读、字数合规与实际阅卷得分分别看待。','',
           '## 已完成的内容修复','',
           '- 现有申论补齐参考作答，作文给出完整正文；机构／用户原稿、AI辅助原创和AI辅助修订分别署明性质，不承诺未经核实的实考高分。',
           '- 北京2020—2021恢复四套完整分卷，北京2022纠正统一卷与重复排序，北京2023恢复材料编号及真实题序。',
           '- 上海按同题完整来源恢复2016—2023可得分卷的材料、题序、缺题与要求，确认2018执法为三题；旧混卷逐题归位后完整归档。',
           '- 天津、广东、福建多份早期三题片段按原稿补回实际漏题、作文、完整材料和字数要求；不同年执法卷不套统一题量。',
           '- 深圳恢复2016两卷15则材料编号、跨页尾文和准确引用，纠正2018、2019、2022、2023一卷错用另一卷要求；天津2022厘清真实类名与重复片段，2017滨海专项核实独立招考身份。',
           '- 修订真实正文超字、篇幅不足、断尾和草稿占位，分离署名、链接与教师点评；修复推广广告、标题粘连和段落断行，原参考全文留在凭据或校勘档案。',
           '- 73份原以行内中文号排列的申论补齐292个Markdown题目标题，题干、要求、材料与答案保留，便于逐题定位。',
           '- 江浙16个混合桶及福建3个重复片段逐题对应完整卷后归档；文件数减少源于清理重复入口，全部旧材料和答案仍保留。',
           '- 行测四卷补入141处参考作答，北京2025片段补入88处作答；修复已核实的选项问题及数学解析。来源解析统一注明非官方性质。','',
           '- 西藏2016按125题来源整理版补回5题、4组共用资料和原图表，20题解析补回完整公式或独立重算；与另一120题公开整理版的题序及收录差异保留说明，不冒称官方原件认证。',
           '- 修复13处判断题空数组占位和20处图推错分类；全库扫描区分独立共用材料、公式图与真正主图缺失。','',
           '新增／修订正文性质：'+ '；'.join(k+' '+str(v)+'份' for k,v in current['checked_body_authorship'].items())+'。原有未改正文另按逐卷台账收录。','',
           '## 尚未取得的真实整卷','',
           '| 地区 | 年份 | 卷型 |','|---|---|---|']
    lines.extend('| '+r['area']+' | '+str(r['year'])+' | '+r['variant']+' |' for r in sorted(gaps,key=lambda r:(r['area'],r['year'],r['variant'])))
    lines+=['','公告、目录和领取广告不当作试卷正文；未取得原题的项目继续列缺，不用相邻卷或自编题替代。未证实独立开考的广州／深圳年份另外标待核，不按日历强凑缺卷。','',
            '## 原题和版本问题','',
            '- 行测原题仍缺25道：广东2020县级69—75；江苏2024A的76、96、110、111；江苏2025C的27、29、35、36、37、42、75、77、78、80、81、85；浙江2020A的49、50。',
            '- 北京2025回忆版仅收93题，仍缺其他原卷内容；56—58缺操作定义，79—80缺日程条件。第51题的8次构造推翻来源10次结论，但未证明全局最优下界。',
            '- 黑龙江2024行测96题D项在三个同题源均残缺；江西2019法检41题计算5400元与原四选项不匹配。其他机构分歧及山东补充版选项边界仍随题保留。',
            '- 新疆2024兵团行测54题虽有四张选项公式图，但题干主图及A点关键条件仍缺；上游亦残缺，未以原参考C反推图形。该项与25道整题缺失、黑龙江D选项缺失分别计，不重命名为已补齐。',
            '- 黑龙江2016县乡原材料有两处来源缺段；已有答案不代表题面完整。','',
            '- 上海2017行测22题补回公式或修正解析；第53题数列可拟合两套规则，第71题“前三天”与来源计算使用的“第三天”冲突，保留歧义和适用假设，不冒称唯一标准解。','',
            '精确正文复核将旧范文的其他版本、原题字数缺失等继续列候选；有另一份合规完整主作答时，不把旧稿超限误算成整题缺答案。新疆2021下半年当前仍是单篇作文来源摘录，原始字数要求未核实，不作完整原卷认证。','',
            '## 可复核入口','',
            '- [本轮机器数据](FULL-REPAIR-20261015.json)；[当前答案逐题检查](FULL-REPAIR-CURRENT-ANSWERS-20261015.json)。',
            '- [剥离链接与解析后的正文终态复核](FULL-REPAIR-PRECISE-ANSWER-FINAL-20261015.json)；[Git暂存原图逐帧验收](FULL-REPAIR-INDEX-IMAGE-PIXELS-20261015.json)。',
            '- [江浙逐年真实分卷](FULL-REPAIR-JIANGZHE-VARIANT-INVENTORY-A-20261015.json)；[北京逐年分卷](FULL-REPAIR-BEIJING-ESSAY-INVENTORY-20261015.md)；[六地区逐年审计](PRIORITY-ESSAY-SIX-REGIONS-AUDIT-20261015.md)。',
            '- [25道原题固定源证据](FULL-REPAIR-APTITUDE-25-MISSING-SOURCE-PACK-20261015.json)；[行测来源分歧](FULL-REPAIR-APTITUDE-SOURCE-DISAGREEMENTS-20261015.json)。',
            '- [已证实的归档映射](FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json)；[原固定Git基线及可逆凭据索引](FULL-REPAIR-BASELINE-20261015.json)。',
            '- 验证命令和终态结果见 [最终验证记录](FULL-REPAIR-VALIDATION-20261015.json)。历史466项在逐字节恢复的固定Git原树运行，新正文和像素另验；缺卷／缺原始条件不因测试通过变成已补。','']
    (ROOT/'reports/FULL-REPAIR-20261015.md').write_text('\n'.join(lines),encoding='utf-8')
    if args.build:cq.build(ROOT,rows,stats)
    print(json.dumps({'essay_files':current['essay_papers'],'readable_answer_positions':sum(current['classifications'].values()),'confirmed_missing_real_papers':len(gaps),'native_flags':stats['files_with_machine_flags'],'build':args.build},ensure_ascii=False))
if __name__=='__main__':main()
