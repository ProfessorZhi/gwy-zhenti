#!/usr/bin/env python3
import json,re
from pathlib import Path
from verify_round3_repairs import verify
ROOT=Path(__file__).resolve().parents[1]

def main():
    summary=verify(ROOT)
    receipts=[json.loads(x) for x in (ROOT/'reports/ROUND3-ESSAY-20261012.jsonl').read_text().splitlines() if x]
    summary.update({'baseline':'74cd629e6318af0a30c77c0a3f0c8b0befaf4d22','known_xingce_questions_fixed':0,'jiangsu_zhejiang_missing_xingce_questions':18,'official_original_certification':False})
    (ROOT/'reports/REPAIR-SUMMARY-20261012-R3.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 第三轮：国考早年申论、江苏答案与浙江2016残卷修复','',
        '执行基线：`74cd629e`。题源读取、处理、验证与提交均在GitHub托管运行器完成，不使用东京设备。','',
        f"实际修改 {summary['papers']} 份既有申论文档；新增 {summary['new_major_questions']} 道大题，补入 {summary['added_reference_answers']} 份来源参考答案；没有新建重复试卷。",
        f"已校验 {summary['checked_material_blocks']} 个完整材料块和 {summary['checked_full_question_blocks']} 个完整作答块，逐块保留 {summary['preserved_answers']} 份历史答案。",'',
        '## 实际修改的正文','', '| 文档 | 本轮结果 | 仍需注意 |','|---|---|---|']
    for r in receipts:
        text=(ROOT/r['path']).read_text();m=re.search(r'^缺参考答案题号: (.+)$',text,re.M);missing=m[1] if m else '见正文'
        result=f"补参考答案 {r['added_answers']}，题面和既有答案未改" if r['kind']=='answer_only' else f"{r['materials_after']}则材料、{r['questions_after']}道题；题序、分值和全部字数要求归位"
        risk='来源公开转录，不是官方原件逐字认证；未收录答案 '+missing
        if r.get('common_question_material_evidence'):risk='第1题来源页标A类；按相同题干、8则材料逐段比对用于B类，明确标注同题来源，不冒充B类独立答案'
        lines.append(f"| [{r['path']}](../{r['path']}) | {result} | {risk} |")
    lines += ['', '## 本轮解决的具体结构问题','',
        '国考2016地市级是4道大题，其中一题包含两个小问，不增造第5道题。其他国考卷按同题题干和完整源的作答段落顺序核对；旧稿末尾只剩“要求：”等缺失项按来源恢复。',
        '来源中HTML列表隐含的题号与“材料5(341891)”等题库ID标记分别处理；材料ID不是新的材料，也不能吞掉材料5。每道题引用的全局材料编号必须实际存在。',
        '浙江2016 A/B分开恢复7材料编排；A卷众筹概括、创业讲话稿，与B卷创业建议、众筹展板不得互换。旧稿已有材料保留非空白字符；登山段明显乱码仅按另一来源的同段材料修正，不采用该网页错配的作答题。',
        '浙江A旧答案末尾夹入的题干从答案区移出，完整异文原文与哈希留在凭据，不静默丢弃。', '',
        '## 未冒填的18道行测题','',
        '| 试卷 | 仍缺原题号 |','|---|---|',
        '| 浙江2020行测A | 49、50 |',
        '| 江苏2024行测A | 76、96、110、111 |',
        '| 江苏2025行测C | 27、29、35、36、37、42、75、77、78、80、81、85 |','',
        '本轮已查的公开候选仍含“暂缺/征集中”或默认答案占位，没有取得可以安全补入上述18题的完整同卷原文，因此正文缺号和台账维持不变。这不表示全网不存在。广东另7题与10个重点年度科目空白未在本轮消除。','',
        '## 可复核证据','',
        '`ROUND3-ESSAY-20261012.jsonl`：来源URL及原始文件SHA、题干映射、材料/问题/答案哈希、旧答案保持和逐处校订依据。',
        '`ROUND3-SOURCE-EXCEPTIONS-20261012.json`：未通过本轮自动导入条件的对象；有异常不按成功处理。',
        '`REPAIR-SUMMARY-20261012-R3.json`：从实际正文与凭据校验生成的数量。',
        '验收包括既有回归、新增16项结构保护测试、当前清单、修复凭据链和全库图片实际像素解码；成功与否以本分支最终GitHub Actions记录为准。结构验收不替代官方原件逐字核验。','']
    (ROOT/'reports/QUALITY-REPAIR-20261012-R3.md').write_text('\n'.join(lines),encoding='utf-8')
    progress=ROOT/'PROGRESS.md';t=progress.read_text();marker='## 第三轮：当前申论补全与剩余（2026-10-12）'
    t=t.split(marker)[0].rstrip()+f"\n\n{marker}\n\n本轮实际修改{summary['papers']}份既有申论，新增{summary['new_major_questions']}道作答题、{summary['added_reference_answers']}份来源参考答案。早期章节中的缺答案/残卷表述是历史状态，当前以第三轮报告和逐卷正文为准。\n\n[第三轮实际修复与边界](reports/QUALITY-REPAIR-20261012-R3.md)。18道江苏/浙江行测缺题未获得可靠原文，仍保留；不把机器检查通过说成缺题已经补齐。\n"
    progress.write_text(t,encoding='utf-8')
    ledger=ROOT/'reports/PRIORITY-QUALITY-20261012.md';text=ledger.read_text();updated=[]
    for line in text.splitlines():
        matched=next((r for r in receipts if '['+r['path']+']' in line),None)
        if matched:
            r=matched;cells=line.split('|');body=(ROOT/r['path']).read_text();m=re.search(r'^缺参考答案题号: (.+)$',body,re.M)
            cells[-4]=f" {r['questions_after']} / {r['questions_after']} ";cells[-3]=' 第三轮：完整来源作答结构与同题匹配；答案旧文保持 ' if r['kind']!='answer_only' else ' 第三轮：补缺参考答案；题面与已有答案保持 '
            cells[-2]=' 未收录参考答案 '+(m[1] if m else '见正文')+'；非官方逐字认证 '
            if r.get('common_question_material_evidence'):cells[-2]=' 第1题为A/B共用题参考来源，非B类独立发布；来源卷型已明确标注 '
            line='|'.join(cells)
        updated.append(line)
    updated.insert(2,'> 当前已接续第三轮实际结果；仅下表标注“第三轮”的行属于本轮范围。详见 [第三轮报告](QUALITY-REPAIR-20261012-R3.md)。')
    ledger.write_text('\n'.join(updated)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
