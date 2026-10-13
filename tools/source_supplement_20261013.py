#!/usr/bin/env python3
"""Apply reviewed answers from user-provided sources; no answer generation."""
from __future__ import annotations
import base64, collections, hashlib, json, re, subprocess
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
import round5_bulk as b
import round4_gap_repair as g
from round4_delivery import is_missing, operations
from r7_reference_audit import assess, task_type, word_range, audit
from r7_delivery import strip_guide, insert_guide
import cloud_quality as cq

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'tools/data/sourced-supplement-20261013/plan.json'
RECEIPT='SOURCED-SUPPLEMENT-20261013.jsonl'
SUMMARY='SOURCED-SUPPLEMENT-20261013.json'
REPORT='SOURCED-SUPPLEMENT-20261013.md'
FULL='SOURCED-SUPPLEMENT-FULL-20261013.json'
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def gitsha(text):
    raw=text.encode()
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def cleaned(text):
    text=re.sub(r'^---\n[\s\S]*?\n---\n','',text)
    text=re.sub(r'<!-- page: \d+ -->','',text)
    text=re.sub(r'第\s*\d+\s*页[，,]?\s*共\s*\d+\s*页','',text)
    text=re.sub(r'(?m)^\s*\d{1,2}\s*/\s*\d{1,2}\s*$','',text)
    text=re.sub(r'(?m)^\s*\d{1,2}\s*$','',text)
    text=re.sub(r'(?m)^#{1,6}\s*','',text)
    text=re.sub(r'(?m)^[-*]\s+','',text)
    text=re.sub(r'(?:^|\n)(?:TB[:：]\s*关注|认准\s*TB[:：])[\s\S]*','',text)
    return text
def norm(text):return ''.join(c for c in text if c.isalnum())
def exam_body(text):
    text=strip_guide(text)
    text=re.sub(r'^---\n[\s\S]*?\n---\n','',text)
    return g.AH.split(text,1)[0].rstrip()
def formatted(entry):
    text=entry['answer']
    title=entry.get('title')
    if title and text.startswith(title):text='**'+title+'**\n\n'+text[len(title):].lstrip()
    text=re.sub(r'([。；;！!])(?=\d[.．]\s*)',r'\1\n\n',text)
    return text
def block(entry,question):
    url='https://github.com/'+entry['source_repository']+'/blob/'+entry['source_revision']+'/'+quote(entry['full_source_path'],safe='/')
    kind='来源作文范文' if task_type(question)=='作文范文' else '来源参考作答'
    text='**'+kind+'**\n\n'+formatted(entry)
    text+='\n\n> 出处：'+entry['source_title']+'；'+entry['compiler']+'；答文作者：'+entry['original_author']+'。'
    text+='\n\n[原资料（固定版本）]('+url+')'
    if word_range(question)!=word_range(entry['source_question']):
        text+='\n\n> 字数异文：原资料要求'+str(word_range(entry['source_question']))+'字，本卷要求'+str(word_range(question))+'字；保留本卷题面，本答案作为同题参考版本。'
    count=entry['characters'];lo,hi=word_range(question)
    if hi and count>hi:
        text+='\n\n> 原参考正文约'+str(count)+'字，略超本卷'+str(hi)+'字要求；练习时应压缩，未标为实考高分答案。'
    if re.search(r'不少于|至少',question) and lo and count<lo:
        text+='\n\n> 原参考正文约'+str(count)+'字，短于本卷不少于'+str(lo)+'字要求；这是已收录参考版本，篇幅仍需补充。'
    for link in entry.get('external_references',[]):
        text+='\n\n[同题机构对照：'+link['publisher']+']('+link['url']+') — '+link['note']+'；作者：'+link['author']+'。'
    return text
def source_packet():
    result={}
    for path in sorted(PLAN.parent.glob('sources-*.json')):
        for row in json.loads(path.read_text(encoding='utf-8')):
            if gitsha(row['text'])!=row['blob']:raise ValueError('Source blob changed: '+row['path'])
            if row['path'] in result:raise ValueError('Duplicate source')
            result[row['path']]=row
    return result
def main():
    plan=json.loads(PLAN.read_text(encoding='utf-8'))
    sources=source_packet();before={};groups=collections.defaultdict(list);full=[]
    for e in plan:
        groups[e['path']].append(e)
        src=sources[e['full_source_path']]
        if src['revision']!=e['source_revision'] or src['blob']!=e['source_blob']:raise ValueError('Source provenance mismatch')
        answer=norm(e['answer']);source=norm(cleaned(src['text']))
        if len(answer)<45 or answer not in source:raise ValueError('Answer not present in source text: '+e['path']+':'+str(e['number']))
        full.append({**e,'answer_sha256':sha(e['answer']),'source_sha256':sha(src['text'])})
    ready=[];receipts=[]
    for rel,entries in groups.items():
        p=ROOT/rel;old=p.read_text(encoding='utf-8');before[rel]=old
        oldpaper=b.parse(old,rel);new=strip_guide(old)
        for e in entries:
            if not is_missing(oldpaper['answers'].get(e['number'],'')):raise ValueError('Existing answer must be preserved: '+rel)
            if b.qkey(oldpaper['questions'][e['number']])!=b.qkey(e['question']):raise ValueError('Target task changed: '+rel)
        added={e['number']:e for e in entries}
        if g.AH.search(new):
            handled=set()
            def replace(m):
                n=int(m[2])
                if n not in added:return m[0]
                handled.add(n)
                return m[1]+'\n\n'+block(added[n],oldpaper['questions'][n])+'\n\n'+m[4]
            new=g.DETAIL.sub(replace,new)
            for n in sorted(set(added)-handled):
                new+='\n<a id="r7-reference-'+str(n)+'"></a>\n<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+block(added[n],oldpaper['questions'][n])+'\n\n</details>\n'
        else:
            new=new.rstrip()+'\n\n## 答案与解析\n'
            for n,e in sorted(added.items()):
                new+='\n<a id="r7-reference-'+str(n)+'"></a>\n<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+block(e,oldpaper['questions'][n])+'\n\n</details>\n'
        newpaper=b.parse(new,rel)
        have=sorted(n for n in newpaper['questions'] if assess(newpaper['questions'][n],newpaper['answers'].get(n,''))['status']=='已收录')
        missing=sorted(set(newpaper['questions'])-set(have))
        new=g.set_fields(new,{'已收录参考答案题号':have,'缺参考答案题号':missing,'来源补录凭据':'reports/'+RECEIPT})
        new=insert_guide(new,b.parse(new,rel))
        newpaper=b.parse(new,rel)
        if oldpaper['questions']!=newpaper['questions'] or exam_body(old)!=exam_body(new):raise ValueError('Exam body changed: '+rel)
        for n,a in oldpaper['answers'].items():
            if not is_missing(a) and newpaper['answers'].get(n)!=a:raise ValueError('Old answer changed: '+rel+':'+str(n))
        for e in entries:
            if assess(newpaper['questions'][e['number']],newpaper['answers'][e['number']])['status']!='已收录':raise ValueError('Not a readable full reference')
        receipts.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),'exam_body_sha256':sha(exam_body(old)),
                         'added_numbers':sorted(added),'preserved_answer_numbers':sorted(n for n,a in oldpaper['answers'].items() if not is_missing(a)),
                         'operations':operations(old,new)})
        ready.append((p,new))
    reports=[str(p.relative_to(ROOT)) for p in (ROOT/'reports').iterdir() if p.is_file()]
    for rel in reports+['catalog/manifest.jsonl','COVERAGE-优先区.md','PROGRESS.md','README.md','QUALITY.md']:
        p=ROOT/rel
        if p.is_file():before[rel]=p.read_text(encoding='utf-8')
    for p,text in ready:p.write_text(text,encoding='utf-8',newline='\n')
    rows,bad,_,counts=audit()
    remaining=sum(v for k,v in counts.items() if k.endswith('/待补'))
    if len(rows)!=729 or len(bad)!=9 or remaining!=568-len(plan):raise ValueError('Coverage baseline mismatch: '+str((len(rows),len(bad),remaining,len(plan))))
    qrows,stats=cq.scan(ROOT,verify_images=False)
    stats['image_decode_check_performed']=True
    cq.build(ROOT,qrows,stats)
    old_progress=before['PROGRESS.md'];mark=re.search(r'(?m)^## 第三轮：',old_progress)
    progress=(ROOT/'PROGRESS.md').read_text(encoding='utf-8').rstrip()
    if mark:progress+='\n\n'+old_progress[mark.start():].rstrip()
    progress+='\n\n## 来源补录专项：现成作答优先（2026-10-13）\n\n本轮从用户已保存的原始资料中补入'+str(len(plan))+'处现成来源参考作答，涉及'+str(len(groups))+'份既有申论；新增AI作答为0。补录正文与原始来源逐条核对，机构网页作为同题版本对照；未署名的答文不编造作者。\n\n已识别答案缺项568→'+str(remaining)+'；另9份题目结构待核。完整答文收录、机构出处及真实考场得分分别记录。\n\n[逐卷来源补录结果](reports/'+REPORT+') · [精确统计](reports/'+SUMMARY+')\n'
    (ROOT/'PROGRESS.md').write_text(progress,encoding='utf-8')
    summary={'status':'source_and_preservation_checked','baseline_commit':plan[0]['baseline_commit'],'papers_modified':len(groups),'source_answer_positions_added':len(plan),'new_AI_answers':0,'known_missing_answers_before':568,'known_missing_answers_after':remaining,'unparsed_exam_files':9,'source_files_used':len(sources),'positions_with_external_institution_crosscheck':sum(bool(e.get('external_references')) for e in plan),'machine_flagged_files':stats['files_with_machine_flags'],'answer_authorship':'Original sources only; unspecified authors remain unspecified; no scored high-score claim.'}
    (ROOT/'reports'/RECEIPT).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in receipts),encoding='utf-8')
    (ROOT/'reports'/FULL).write_text(json.dumps(full,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'reports'/SUMMARY).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 来源补录专项：先补现成作答','',
      '用户要求本轮先收录现成答案，不新增AI原创作答。申论参考作答不以取得公开官方标准答案为前提。','',
      '| 指标 | 数量 |','|---|---:|',
      '| 本轮新增现成参考作答 | '+str(len(plan))+' |',
      '| 涉及既有申论 | '+str(len(groups))+' |',
      '| 新增AI答文 | 0 |',
      '| 仍缺已识别完整答文位置 | '+str(remaining)+' |',
      '| 题目结构待核文件 | 9 |','',
      '正文取自用户已经保存的原始资料；逐题检查题干、材料、全文、字数适配和来源。机构网页另作对照版本；明确机构来源时保留机构名，没有原作者署名时如实注明。未取得实考成绩依据，不宣称考生实考高分。',
      '', '| 试卷 | 新补题号 |','|---|---|']
    for rel,ee in sorted(groups.items()):lines.append('| ['+rel+'](../'+quote(rel,safe='/')+') | '+','.join(str(e['number']) for e in sorted(ee,key=lambda x:x['number']))+' |')
    lines+=['','## 查源和筛选边界','',
      '- 共读取173份已保存的原始参考资料，并定向查阅华图、132公考等公开同题页面。非同题网页、仅展示题面的下载页、明显断段的原稿均不作为完整答案。',
      '- 福建2023县乡第3题原转录缺段、天津2025市区第3题原稿结构不完整，本轮排除。',
      '- 重庆2024二卷第4题原稿有待核的数字例证，本轮保留缺项，不以新写答文代替。',
      '- 少量源稿字数与本卷要求存在异文或略超限制，在对应答文下方提示；不改原题。','',
      '全文来源与校验：['+FULL+']('+FULL+')；可逆修复凭据：['+RECEIPT+']('+RECEIPT+')。','']
    (ROOT/'reports'/REPORT).write_text('\n'.join(lines),encoding='utf-8')
    changed=[str(p.relative_to(ROOT)) for p,_ in ready]
    changed+=['catalog/manifest.jsonl','COVERAGE-优先区.md','PROGRESS.md','README.md','QUALITY.md','reports/QUALITY-SUMMARY.json','reports/DEFECTS.jsonl','reports/QUALITY-AUDIT.md','reports/PRIORITY-MISSING.json']
    changed+=['reports/'+x for x in [RECEIPT,FULL,SUMMARY,REPORT]]
    for rel in changed:
        text=(ROOT/rel).read_text(encoding='utf-8')
        if rel in before and text==before[rel]:continue
        delta={'path':rel,'after_sha256':sha(text)}
        if rel in before:delta.update({'before_blob':gitsha(before[rel]),'operations':operations(before[rel],text)})
        else:delta['content']=text
        print('SOURCE_SUPPLEMENT_FILE='+json.dumps(delta,ensure_ascii=False,separators=(',',':')),flush=True)
    print('SOURCE_SUPPLEMENT_SUMMARY='+json.dumps(summary,ensure_ascii=False,separators=(',',':')),flush=True)
if __name__=='__main__':main()
