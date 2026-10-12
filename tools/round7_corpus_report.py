#!/usr/bin/env python3
"""Report genuine reference-answer coverage across all 738 essay Markdown files."""
from __future__ import annotations
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import is_missing
from round7_reference_delivery import ROOT
from verify_round7_reference import verify as verify_r7,records as r7_records

def all_papers():
    return sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')])

def assess():
    rows=[];failures=[];missing=0
    regional=collections.defaultdict(collections.Counter)
    for p in all_papers():
        path=p.relative_to(ROOT).as_posix()
        area='国考' if path.startswith('国考/') else path.split('/')[1]
        stat=regional[area];stat['files']+=1
        data=p.read_text(encoding='utf-8')
        try:
            paper=b.parse(data,path)
            if paper is None:raise ValueError('Not a supported essay file')
        except Exception as exc:
            failures.append({'path':path,'reason':str(exc)})
            rows.append({'path':path,'region':area,'status':'unparsed','reason':str(exc)})
            stat['unparsed']+=1
            continue
        questions=[];unfilled=[]
        for number,stem in sorted(paper['questions'].items()):
            ans=paper['answers'].get(number,'')
            is_blank=is_missing(ans)
            is_essay=bool(re.search(r'议论性文章|议论文|写一篇文章|撰写一篇文章|对策性文章|作文',stem))
            if is_blank:
                missing+=1;stat['missing']+=1;unfilled.append(number)
            else:stat['filled']+=1
            stat['recognized_questions']+=1
            if is_essay:stat['essay_candidate']+=1
            questions.append({
                'number':number,'reference_answer_present':not is_blank,
                'answer_characters':len(re.sub(r'\s','',ans)) if not is_blank else 0,
                'is_long_essay_candidate':is_essay,
                'ai_original_explicitly_labeled':('AI辅助编写' in ans and '未经实考评分' in ans),
                'source_authenticity_not_independently_certified':True
            })
        rows.append({'path':path,'region':area,'year':paper['identity'][1],
            'variant':paper['variant'],'status':'parsed','questions':questions,
            'missing_answer_ids':unfilled})
    if len(rows)!=738 or len(failures)!=9:
        raise ValueError('Unexpected corpus size or unparsed essay file count')
    return rows,regional,failures,missing

def main():
    result=verify_r7(ROOT)
    records=r7_records(ROOT)
    rows,regions,failures,missing=assess()
    if result['answers_added']!=7 or missing!=602:
        raise ValueError('Unexpected missing-answer slot count: '+str(missing))
    stats=json.loads((ROOT/'reports/QUALITY-SUMMARY.json').read_text(encoding='utf-8'))
    output=ROOT/'reports/SHENLUN-COVERAGE-ALL-738-20261013.jsonl'
    output.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    summary={'status':'verified','essay_papers':738,'parsed':729,'unparsed':len(failures),
             'missing_answer_slots_before':609,'missing_answer_slots_after':missing,
             'completed_original_examples_added':7,'updated_exam_papers':len(records),
             'machine_flagged_files':stats['files_with_machine_flags'],
             'reference_kind':'Independent AI-assisted example, not institutional transcript or graded exam answer',
             'verification':result}
    (ROOT/'reports/REPAIR-SUMMARY-20261013-R7.json').write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[
        '# 738份申论逐卷参考答案与范文覆盖台账','',
        '更新：2026-10-13。此表统计文档中的参考答案位置，不等于去重后的独立真题。',
        '原有答案是否正确、材料是否逐字真实、机构是否有转载授权，仍需单独核对。','',
        '## 实际覆盖','',
        '| 指标 | 数量 |','|---|---:|',
        '| 申论Markdown | 738 |','| 可识别题目与答案结构 | 729 |',
        '| 结构仍需人工核对 | 9 |',
        '| 新增完整原创示范作答位置 | 7 |',
        '| 完整参考答案空位 | 609 → '+str(missing)+' |',
        '| 全库质量机器告警 | '+str(stats['files_with_machine_flags'])+' |',
        '',
        '## 逐地区覆盖','',
        '| 地区 | 申论文档 | 已识别题目位置 | 现有参考答案位置 | 缺参考答案位置 | 未识别文档 |',
        '|---|---:|---:|---:|---:|---:|'
    ]
    for area,c in sorted(regions.items(),key=lambda x:(-x[1]['missing'],x[0])):
        lines.append('| '+area+' | '+str(c['files'])+' | '+str(c['recognized_questions'])+
            ' | '+str(c['filled'])+' | '+str(c['missing'])+' | '+str(c['unparsed'])+' |')
    lines.extend(['','## 本轮真正补回的答案','',
        '| 试卷 | 已补原题号 | 答案性质 |','|---|---|---|'])
    for rec in records:
        path=rec['path'];nums=[str(a['number']) for a in rec['added_answers']]
        lines.append('| ['+path+'](../'+quote(path,safe='/')+') | '+','.join(nums)+
            ' | 根据本卷材料独立写作的示范稿；不是网上机构原文或经实考评分的高分卷 |')
    lines+=['','## 尚未完成题目解析的9份申论','']
    for rec in failures:lines.append('- '+rec['path']+'：'+rec['reason'])
    lines+=['','## 每道题的补全准则','',
      '每道小题需有完整、切题、符合文种与字数限制的参考作答；每道作文题应有围绕同题材料的完整范文。',
      '引用机构范文时，区分可转载全文的许可和只能引用链接或短摘录的情况。',
      '只有带具体考生分数核实依据的才宣称实考高分卷；公开机构范文按“机构范文”标注；AI辅助独立写作须说明未获实考评分。',
      '机器标签仅是下一轮逐题人工核对的入口，不意味着全部738份已通过质量认证。',
      '',
      '完整逐文件机器清单：reports/SHENLUN-COVERAGE-ALL-738-20261013.jsonl。','']
    (ROOT/'reports/SHENLUN-QUALITY-COVERAGE-20261013.md').write_text('\n'.join(lines),encoding='utf-8')
    progress=ROOT/'PROGRESS.md';orig=subprocess.check_output(['git','show','HEAD:PROGRESS.md'],text=True)
    existing=progress.read_text(encoding='utf-8')
    old_section=re.search(r'(?m)^## 第三轮：',orig)
    existing=re.sub(r'\n## 第三轮:[\s\S]*\Z','',existing).rstrip()+'\n'
    if old_section:existing+='\n'+orig[old_section.start():].rstrip()+'\n'
    existing+=('\n## 第七轮：全库申论答案覆盖（2026-10-13）\n\n'
      '已建立全部738份申论的逐卷答案台账，729份题目/答案可识别、9份待复核。'
      '本轮对江苏2026B、浙江2025A及浙江2026A/C四卷新增7个明确标注AI辅助原创的完整示范作答，'
      '保留机构同题对照入口，不将原创稿冒充已获实考分数的高分答卷。'
      '识别出的缺完整参考答案位置609→602；这不是独立真题数量。\n\n'
      '[全库逐卷统计](reports/SHENLUN-QUALITY-COVERAGE-20261013.md) · '
      '[完整逐题JSONL](reports/SHENLUN-COVERAGE-ALL-738-20261013.jsonl) · '
      '[可逆验收记录](reports/REPAIR-SUMMARY-20261013-R7.json)\n')
    progress.write_text(existing,encoding='utf-8')
    print('ROUND7_ALL_738',json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
