#!/usr/bin/env python3
"""Report actual R9 Markdown content, never count prepared packets as answers."""
from __future__ import annotations
import collections,json,re,subprocess
from pathlib import Path
from urllib.parse import quote
import r7_delivery as layout
from r7_reference_audit import assess
from r9_check_authored import ROOT,read_drafts
from verify_round9_authored import verify,records

def line_index():
    lines=['# 第九轮原材料精确阅读索引','','行号指对应临时packet文件的物理行；不是原卷题号。','',
        '| 原卷 | 文件和行范围 | 题号与任务原文 |','|---|---|---|']
    for file in sorted((ROOT/'reports/r9-context').glob('packet-*.md')):
        content=file.read_text(encoding='utf-8').splitlines()
        starts=[i for i,line in enumerate(content) if line.startswith('# 省考/') or line.startswith('# 国考/')]
        for pos,start in enumerate(starts):
            end=starts[pos+1] if pos+1<len(starts) else len(content)
            title=content[start][2:];parts=[]
            for i in range(start,end):
                if content[i].startswith('## R9-'):
                    taskline=next((line.strip() for line in content[i+1:end] if line.strip()),'')
                    parts.append(content[i][3:].replace('|','／')+'：'+taskline.replace('|','／'))
            lines.append('| '+title+' | '+file.name+':'+str(start+1)+'—'+str(end)+' | '+'；'.join(parts)+' |')
    (ROOT/'reports/r9-context/read-map.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    result=verify(ROOT);tasks,drafts,issues,bad=read_drafts();rows=[];counter=collections.Counter();unparsed=[]
    for p in sorted([*ROOT.glob('国考/*/申论*.md'),*ROOT.glob('省考/*/*/申论*.md')]):
        rel=p.relative_to(ROOT).as_posix()
        try:
            doc=layout.parse(p.read_text(encoding='utf-8'),rel)
            status=[]
            for n,q in doc['questions'].items():
                s=assess(q,doc['answers'].get(n,''));s['number']=n;status.append(s)
                counter[s['kind']+'/'+s['status']]+=1
            rows.append({'path':rel,'tasks':status})
        except Exception as e:unparsed.append({'path':rel,'error':str(e)})
    pending=sum(value for key,value in counter.items() if not key.endswith('/已收录'))
    if len(rows)+len(unparsed)!=738 or len(unparsed)!=9:raise ValueError('Unexpected corpus/parse count')
    if pending!=len(tasks)-len(drafts):raise ValueError('Actual current missing count does not match delivered answers')
    summary={'status':'verified','baseline':'8c23683610441d82836b907e20c586f2b4622646',
        'all_essay_files':738,'parsed_essay_files':len(rows),'unparsed_documents':unparsed,
        'actual_authored_answer_positions':len(drafts),'actual_edited_papers':result['modified_papers'],
        'remaining_incomplete_positions':pending,
        'remaining_blank_positions':sum(v for k,v in counter.items() if k.endswith('/待补')),
        'remaining_old_length_or_image_warnings':sum(v for k,v in counter.items() if not k.endswith(('/已收录','/待补'))),
        'authored_full_essays':sum(x['task']['kind']=='作文范文' for x in drafts.values()),
        'classification':dict(counter),'source_limitations':result['source_limitations'],
        'verification':result,'boundary':'Authored study references, not institution originals or scored answer sheets; unparsed/source-limited tasks remain explicitly qualified.'}
    (ROOT/'reports/REPAIR-SUMMARY-20261013-R9.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'reports/ROUND9-COVERAGE-20261013.json').write_text(json.dumps({'summary':summary,'papers':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    left=[t for key,t in tasks.items() if key not in drafts]
    (ROOT/'reports/ROUND9-REMAINING-20261013.json').write_text(json.dumps({'tasks':left,'unparsed':unparsed},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 第九轮：实际原创参考作答补录','','只统计已写入对应试卷答案区的完整正文；备料、查源、导航和草稿不单独计作完成。','',
        '| 指标 | 实际结果 |','|---|---:|',
        '| 申论文档 | 738 |','| 本轮回填参考作答位置 | '+str(len(drafts))+' |',
        '| 其中完整作文 | '+str(summary['authored_full_essays'])+' |',
        '| 修改原卷MD | '+str(result['modified_papers'])+' |',
        '| 仍缺完整作答或需修复旧版本 | '+str(pending)+' |',
        '| 题目结构仍需核对 | 9 |','',
        '新增正文均按本卷材料和作答要求独立撰写，标明ChatGPT原创及未经实考评分。已有完整参考答案不覆盖；旧不完整版本保留对照；原题、材料和历史修复凭据不更改。','',
        '## 逐卷实际新增','', '| 原卷 | 本轮已回填原题号 |','|---|---|']
    for r in records(ROOT):
        lines.append('| ['+r['path']+'](../'+quote(r['path'],safe='/')+') | '+', '.join(str(a['number']) for a in r['added_references'])+' |')
    lines+=['','## 必须保留的题源限制','']
    for w in result['source_limitations']:lines.append('- '+w['id']+' '+w['path']+' 第'+str(w['number'])+'题：'+w['source_limit'])
    lines+=['','完整逐题剩余清单：ROUND9-REMAINING-20261013.json；可逆实际交付凭据：ROUND9-AUTHORED-20261013.jsonl。',
        '行测25道原题缺失、重点年度科目空白及其他占位属于不同范围，不因本轮申论作答增加而自动消除。','']
    (ROOT/'reports/QUALITY-REPAIR-20261013-R9.md').write_text('\n'.join(lines),encoding='utf-8')
    old=subprocess.check_output(['git','show','HEAD:PROGRESS.md']).decode('utf-8')
    old=re.sub(r'\n## 第九轮：[\s\S]*\Z','',old)
    generated=(ROOT/'PROGRESS.md').read_text(encoding='utf-8')
    generated=re.sub(r'\n## 第三轮：[\s\S]*\Z','',generated).rstrip()+'\n'
    at=re.search(r'(?m)^## 第三轮：',old)
    if at:generated+='\n'+old[at.start():].rstrip()+'\n'
    generated+='\n## 第九轮：按题面材料补写完整学习参考（2026-10-13）\n\n'
    generated+=f"本轮已实际回填{len(drafts)}处原创参考作答，涉及{result['modified_papers']}份原卷，其中{summary['authored_full_essays']}篇为完整作文。仍有{pending}处作答空缺或旧稿问题，另9份题目结构待核。稿件未获实考评分，不冒称机构原文。\n\n"
    generated+='[实际补录与限制](reports/QUALITY-REPAIR-20261013-R9.md) · [逐题剩余清单](reports/ROUND9-REMAINING-20261013.json)\n'
    (ROOT/'PROGRESS.md').write_text(generated,encoding='utf-8')
    line_index()
    print('R9_VERIFIED_PROGRESS '+json.dumps({k:v for k,v in summary.items() if k not in ('verification','unparsed_documents','source_limitations','classification')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
