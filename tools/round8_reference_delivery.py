#!/usr/bin/env python3
"""First batch of independently authored essay examples; preserve historical text and evidence."""
from __future__ import annotations
import argparse,collections,json,re
from pathlib import Path
import round4_gap_repair as g
import round5_bulk as b
from round4_delivery import operations,is_missing
ROOT=g.ROOT
DRAFT=ROOT/'reports/ROUND8-ORIGINAL-ANSWER-DRAFTS-20261013.json'
RECEIPT='ROUND8-ORIGINAL-ANSWERS-20261013.jsonl'
SUMMARY='REPAIR-SUMMARY-20261013-R8.json'
PENDING='本题参考答案尚未核实收录，不以空白或默认选项冒充答案。'
DETAIL=re.compile(r'(<summary>第\s*(\d+)\s*题</summary>)(.*?)(</details>)',re.S)
HEADING=re.compile(r'(?m)^## 答案与解析\s*$')

def digest(text):return g.digest(text)
def content_body(text):
    if not text.startswith('---\n'):raise ValueError('Not an essay Markdown with frontmatter')
    core=text.split('---',2)[2]
    return HEADING.split(core,1)[0].rstrip()

def count_chars(text):return len(re.sub(r'\s|\*','',text))
def draft_entries():
    entries=json.loads(DRAFT.read_text(encoding='utf-8'))
    assert len(entries)==7
    keys=[(a['path'],a['n']) for a in entries]
    if len(keys)!=len(set(keys)):raise ValueError('Repeated answer target')
    for a in entries:
        if (not a['path'].startswith('省考/') or not a['path'].endswith('.md')
            or not a['source'].startswith('https://') or not a['answer'].strip()):
            raise ValueError('Invalid authored source/target')
        count=count_chars(a['answer'])
        if not a['min']<=count<=a['max']:raise ValueError('Length requirement not satisfied '+a['path'])
        if any(tag in a['answer'] for tag in ('<script','</details>','## 答案与解析')):
            raise ValueError('Unsafe nested answer markup')
    return entries

def answer_block(entry):
    return ('**原创示范作答（AI辅助编写；非机构原文，未经实考评分）**\n\n'
      + entry['answer'].strip()+'\n\n'
      + '> 写作依据：本卷给定资料'+','.join(map(str,entry['materials']))
      +'及该题作答要求。本文为独立撰写的学习示例，不是考试机关答案，也不是有成绩证明的考场高分卷。\n\n'
      + '[同题机构参考作答／范文对照入口]('+entry['source']+')'
      + '（链接仅供比较，未转载其正文，发布方答案不等同于考试机关统一答案）。')

def render(path,old,entries):
    paper=b.parse(old,path)
    if paper is None:raise ValueError('Not an essay')
    byid={a['n']:a for a in entries}
    if set(byid)-set(paper['questions']):raise ValueError('Missing question ID')
    for n in byid:
        if not is_missing(paper['answers'].get(n,'')):
            raise ValueError('Refusing to replace a nonempty pre-existing answer '+str(n))
    new=old
    if not HEADING.search(old):
        # Jiangsu 2026B: keep the initial filing note as a historical source note;
        # add a separate modern example section rather than replacing the exam.
        if path!='省考/江苏/2026/申论-B类.md' or set(byid)!=set(paper['questions']):
            raise ValueError('An existing answer section is missing unexpectedly')
        parts=['## 答案与解析','',
            '> **更新说明**：上述“参考答案均尚未核实取得”仅是本卷首次入库时的历史状态。'
            '以下新增内容是基于材料独立写作的学习参考，不是机构正文的复制或实际考场高分卷。','']
        for n in sorted(byid):
            parts.extend(['<details>',f'<summary>第 {n} 题</summary>','',answer_block(byid[n]),'','</details>',''])
        new=old.rstrip()+'\n\n'+'\n'.join(parts)
    else:
        captured=[]
        def sub(m):
            n=int(m.group(2))
            if n not in byid:return m.group(0)
            oldanswer=m.group(3).strip()
            if not is_missing(oldanswer) and PENDING not in oldanswer:
                raise ValueError('Existing answer not empty '+str(n))
            captured.append(n)
            return m.group(1)+'\n\n'+answer_block(byid[n])+'\n\n'+m.group(4)
        new=DETAIL.sub(sub,new)
        if sorted(captured)!=sorted(byid):raise ValueError('Missing exact answer blocks '+path)
    preexisting=set(paper['questions'])-set(paper['missing'])
    present=sorted(preexisting|set(byid))
    new=g.set_fields(new,{
        '已收录参考答案题号':present,
        '缺参考答案题号':sorted(set(paper['questions'])-set(present)),
        '新增原创示范作答题号':sorted(byid),
        '新增示范性质':'独立写作的AI辅助学习样例，未经实考成绩认证；链接为独立同题对照资料',
        '第八轮示范修复凭据':'reports/'+RECEIPT,
    },'2026-10-13：新增同题独立原创示范作答，原始给定资料与题目保持。')
    if content_body(old)!=content_body(new):
        raise ValueError('Original paper material/question text changed')
    nd=b.parse(new,path)
    if set(nd['questions'])!=set(paper['questions']):
        raise ValueError('Question ID set changed')
    for n,ans in paper['answers'].items():
        if not is_missing(ans) and nd['answers'].get(n)!=ans:
            raise ValueError('Altered pre-existing answer '+path+':'+str(n))
    for n in byid:
        if is_missing(nd['answers'].get(n,'')):
            raise ValueError('New answer still missing '+str(n))
        if byid[n]['answer'].strip() not in nd['answers'][n]:
            raise ValueError('Written reference answer text damaged')
    rec={'path':path,'kind':'independent_original_study_answers',
         'before_sha256':digest(old),'after_sha256':digest(new),
         'before_body_sha256':digest(content_body(old)),
         'question_count':len(paper['questions']),
         'added_answers':[{'number':n,'chars':count_chars(e['answer']),
             'reference_link':e['source'],'model_authored':True,
             'text_sha256':digest(e['answer']),'delivered_answer_sha256':digest(nd['answers'][n])}
             for n,e in sorted(byid.items())],
         'preserved_answers':{str(n):digest(ans) for n,ans in paper['answers'].items() if not is_missing(ans)},
         'remaining_answer_ids':nd['missing'],'operations':operations(old,new)}
    return new,rec

def prepare():
    groups=collections.defaultdict(list)
    for a in draft_entries():groups[a['path']].append(a)
    result=[]
    for path,entries in sorted(groups.items()):
        file=ROOT/path
        if not file.is_file():raise ValueError('Missing original paper '+path)
        old=file.read_text(encoding='utf-8')
        new,rec=render(path,old,entries)
        result.append((file,new,rec))
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    results=prepare()
    count=sum(len(r['added_answers']) for _,_,r in results)
    if count!=7 or len(results)!=4:raise ValueError('Unexpected validated set')
    summary={'status':'validated','apply':args.apply,
             'papers':len(results),'complete_model_authored_answers_added':count,
             'authored_answers_with_external_comparison_urls':count,
             'scope':'Original examples only, no third-party text reproduction and no real-score claim.',
             'docs':[{'path':r['path'],'numbers':[a['number'] for a in r['added_answers']]} for _,_,r in results]}
    print('R7_PRECHECK',json.dumps(summary,ensure_ascii=False),flush=True)
    if not args.apply:return
    recfile=ROOT/'reports'/RECEIPT
    if recfile.exists():raise ValueError('Round7 is already applied')
    for file,new,rec in results:
        if digest(file.read_bytes())!=rec['before_sha256']:
            raise ValueError('Source changed during preparation')
    for file,new,rec in results:
        file.write_text(new,encoding='utf-8',newline='\n')
        if digest(file.read_bytes())!=rec['after_sha256']:
            raise ValueError('Writeback mismatch')
    recfile.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,_,r in results),
                       encoding='utf-8')
    (ROOT/'reports'/SUMMARY).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
