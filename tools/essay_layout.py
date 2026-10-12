#!/usr/bin/env python3
"""Lossless heading insertion for whole-text essay papers, never infer questions from counts."""
from __future__ import annotations
import re,hashlib
from paper_integrity_repair import set_fields
NUM={c:i for i,c in enumerate('零一二三四五六七八九十')}
LABEL=re.compile(r'(?m)^[ \t\u3000]*(?:(?:问题|题目)([一二三四五六七八九十1-9])|第([一二三四五六七八九十1-9])题|([一二三四五六七八九十])[、．.]|[（(]([一二三四五六七八九十])[）)])[：:]?')
ANSWER=re.compile(r'(?m)^## (?:参考答案|答案与解析)[^\n]*\n')
DETAIL=re.compile(r'<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>(.*?)</details>',re.S)

def digest(t:str)->str:return hashlib.sha256(t.encode()).hexdigest()
def parse_whole(text:str,expected:int)->dict:
    front=re.match(r'\A---\n.*?\n---\n',text,re.S)
    if not front:raise ValueError('Missing frontmatter')
    if re.search(r'^#{2,3} 第 \d+ 题',text,re.M):raise ValueError('Already has question headings')
    answer=ANSWER.search(text);end=answer.start() if answer else len(text);body=text[front.end():end]
    # A same-line section label is separated without losing characters.
    body=re.sub(r'(作答要求)[ \t\u3000]+(?=(?:问题|题目|第[一二三四五六七八九十]题))',r'\1\n\n',body)
    anchors=list(re.finditer(r'(?m)^[ \t\u3000]*(?:三[、．.]\s*)?作答要求[ \t\u3000]*$',body))
    if anchors:start=anchors[-1].end()
    else:
        anchors=list(re.finditer(r'(?m)^[ \t\u3000]*(?:作答任务|申论要求|问题及要求|作答要求及问题)[：:]?[ \t\u3000]*$',body))
        if not anchors:raise ValueError('Explicit question section missing')
        start=anchors[-1].end()
    head,part=body[:start],body[start:];labels=list(LABEL.finditer(part));ids=[];questions=[]
    for i,m in enumerate(labels):
        x=next(g for g in m.groups() if g);n=int(x) if x.isdigit() else NUM[x];ids.append(n)
        questions.append(dict(number=n,original_label=m[0].strip(),text=part[m.start():labels[i+1].start() if i+1<len(labels) else len(part)].strip()))
    if ids!=list(range(1,expected+1)):raise ValueError('Explicit question labels do not match declaration: '+str(ids))
    if any('要求' not in q['text'] for q in questions):raise ValueError('Question lacks visible requirements; do not infer')
    points=[]
    for q in questions:
        marks=re.findall(r'[（(]\s*(\d+)\s*分\s*[）)]',q['text'].split('要求')[0])
        points.append(int(marks[-1]) if marks else None)
    if None not in points and sum(points)!=100:raise ValueError('Question points do not sum to 100')
    existing={int(m[1]):m[2].strip() for m in DETAIL.finditer(text[end:])}
    if answer and set(existing)!=set(ids):raise ValueError('Existing answer IDs differ from question IDs')
    return dict(front=text[:front.end()],body_before=head,questions=questions,answer_tail=text[end:] if answer else '',existing_answers=existing,points=points,original_body=body)

def format_whole(text:str,expected:int,answer_additions:dict[int,str],source_note:str)->tuple[str,dict]:
    d=parse_whole(text,expected)
    if d['existing_answers'] and answer_additions:raise ValueError('Existing answers must not be overwritten')
    if not set(answer_additions)<=set(range(1,expected+1)):raise ValueError('Answer outside question range')
    head=d['body_before'];head=re.sub(r'(?m)^([ \t\u3000]*)(材料[一二三四五六七八九十0-9]+[：:]?)[ \t\u3000]*$',lambda m:'## 给定资料 '+m[2]+'\n',head)
    qs=[]
    for q in d['questions']:qs.append('## 第 '+str(q['number'])+' 题\n\n'+q['text'])
    body=head.rstrip()+'\n\n'+'\n\n'.join(qs)+'\n'
    # The full original material/question characters remain, allowing only heading insertion and whitespace.
    stripped=re.sub(r'^## (?:给定资料 |第 \d+ 题).*\n?',lambda m:m[0].removeprefix('## 给定资料 ') if m[0].startswith('## 给定资料 ') else '',body,flags=re.M)
    if re.sub(r'\s','',stripped)!=re.sub(r'\s','',d['original_body']):raise AssertionError('Original essay body changed')
    answered=sorted(d['existing_answers'] or answer_additions)
    front=set_fields(d['front'],{'题目结构':'整卷给定资料与作答要求分区；显式原题标签核对','实有题数':expected,'对照题本题量':expected,'缺失原题号':[],'题目分值':d['points'],'已收录参考答案题号':answered,'缺参考答案题号':sorted(set(range(1,expected+1))-set(answered)),'分卷核对证据':'reports/ESSAY-REPAIR-20261012.jsonl','整卷核验状态':'结构与题干/作答要求核对；材料逐字真实性未全面认证'},'2026-10-12 申论整卷标题与题目导航规范化；正文保留，答案按同年同类同题匹配，不以题号数量代替逐字验真。')
    out=front.rstrip()+'\n'+body
    if d['answer_tail']:out+='\n'+d['answer_tail'].strip()+'\n'
    elif answer_additions:
        out+='\n## 答案与解析\n\n> '+source_note+'\n\n'
        for n in range(1,expected+1):
            content=answer_additions.get(n,'本题参考答案尚未核实收录，不以空白或默认选项冒充答案。')
            out+='<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+content+'\n\n</details>\n\n'
    else:out+='\n## 参考答案收录情况\n\n本卷参考答案尚未核实收录；题面和作答要求不因此视为缺失。\n'
    report=dict(before_sha256=digest(text),after_sha256=digest(out),questions=expected,points=d['points'],existing_answer_bodies_preserved=len(d['existing_answers']),answer_additions=sorted(answer_additions),unanswered=sorted(set(range(1,expected+1))-set(answered)),body_check='All pre-existing material and question non-whitespace characters preserved; only headings inserted.')
    return out,report
