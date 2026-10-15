"""Conservative corpus layout cleanup; preserve source text in reversible receipts.

Does not supply missing exam text or move an unproved question. Only explicit
duplicate prompt tails are moved to a source appendix, with their original text
retained. Run after parallel content writers complete.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,re,unicodedata,os,uuid
from pathlib import Path
from difflib import SequenceMatcher
import round5_bulk as parser
from paper_integrity_repair import set_fields
from r7_delivery import GUIDE,ANCHOR,reading_guide as historical_reading_guide
from r7_reference_audit import assess
from full_repair_answers_20261015 import pending

ROOT=Path(__file__).resolve().parents[1]
DETAIL=re.compile(r'(<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>)(.*?)(</details>)',re.S)
ENTITY=re.compile(r'&#(?:x([0-9a-fA-F]+)|(\d+));')
PROMPT=re.compile(r'(?m)^\s*(?:第[一二三四五六七八九十\d]+题|问题[一二三四五六七八九十\d]+[：:]?)\s*\n')

def reading_guide(paper):
    guide=historical_reading_guide(paper)
    for n,question in paper['questions'].items():
        if re.search(r'写一篇(?:议论性文章|议论文|文章)|写一篇.{0,6}文章',question):
            guide=guide.replace('| '+str(n)+' | 小题参考作答 |','| '+str(n)+' | 作文范文 |')
    return guide

def sha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def chinese_compat(text):
    def entity(m):
        try:c=chr(int(m[1],16) if m[1] else int(m[2]))
        except (ValueError,OverflowError):return m[0]
        return c if ('\u3400'<=c<='\u9fff' or '\u2f00'<=c<='\u2fdf' or '\uf900'<=c<='\ufaff' or '\U0002f800'<=c<='\U0002fa1f') else m[0]
    text=ENTITY.sub(entity,text)
    return ''.join(unicodedata.normalize('NFKC',c) if ('\u2f00'<=c<='\u2fdf' or '\uf900'<=c<='\ufaff' or '\U0002f800'<=c<='\U0002fa1f') else c for c in text)

def normalize_paragraphs(text):
    # Ideographic paragraph indents were flattened by the PDF transcription.
    lines=[]
    for line in text.splitlines():
        if len(line)>500 and line.count('\u3000\u3000')>=2 and not re.search(r'<(?:img|p|table)\b|https?://',line):
            line=re.sub(r'\u3000{2,}','\n\n',line)
        lines.append(line)
    text='\n'.join(lines)
    paragraphs=re.split(r'\n[ \t\u3000]*\n+',text)
    result=[];joins=0
    for item in paragraphs:
        current=item.strip(' \t\u3000\n')
        if not current:continue
        left=result[-1] if result else ''
        simple=lambda t:not re.search(r'(^|\n)\s*(?:[#>|]|[-*]\s|<|\[)|https?://',t)
        continuation=(left and simple(left) and simple(current)
          and not re.match(r'^(?:[一二三四五六七八九十]+[、．.]|[（(]?[0-9一二三四五六七八九十]+[）)、.．])',current)
          and ((40<=len(left.splitlines()[-1])<=140 and re.search(r'[\u3400-\u9fff]$',left) and re.match(r'^[\u3400-\u9fff]',current))
               or (len(left)>30 and re.match(r'^[，、。；：,;]',current))))
        if continuation:result[-1]=left+current;joins+=1
        else:result.append(current)
    return '\n\n'.join(result).rstrip()+'\n',joins

def prompt_tail_to_appendix(answer,questions):
    for marker in PROMPT.finditer(answer):
        tail=answer[marker.start():]
        if not re.search(r'要求[：:]|\d+\s*字',tail):continue
        end=re.search(r'\n\s*>\s*来源说明[：:]|\n\s*\[本题(?:既有)?来源记录\]|\n\s*<!-- /R7 reference text -->',tail)
        cut=tail[:end.start()] if end else tail
        # A duplicate prompt must match a visible current question, not just a topic.
        key=parser.qkey(cut);best=[]
        for n,q in questions.items():
            qk=parser.qkey(q)
            if len(qk)<18:continue
            ratio=SequenceMatcher(None,key,qk,autojunk=False).ratio()
            if ratio>=.96 or qk in key:best.append(n)
        if len(best)!=1:continue
        stripped=answer[:marker.start()]+tail[len(cut):]
        if len(stripped.strip())<50:continue
        return stripped,{'matched_question':best[0],'text':cut,'sha256':sha(cut)}
    return answer,None

def format_essay(old,rel):
    # Frontmatter remains a provenance record; normalize content text separately.
    fm=re.match(r'\A---\n.*?\n---\n',old,re.S)
    if not fm:raise ValueError('Missing frontmatter')
    front=old[:fm.end()];body=old[fm.end():]
    body=chinese_compat(body)
    text=front+body
    text=GUIDE.sub('',text);text=ANCHOR.sub('',text)
    d=parser.parse(text,rel)
    moved=[];joins=0
    def answer_sub(m):
        nonlocal joins
        raw=m[3];clean,move=prompt_tail_to_appendix(raw,d['questions'])
        if move:move['answer_number']=int(m[2]);moved.append(move)
        # Keep source attribution blocks distinct while repairing prose wrapping.
        clean,count=normalize_paragraphs(clean);joins+=count
        return m[1]+'\n\n'+clean.strip()+'\n\n'+m[4]
    text=DETAIL.sub(answer_sub,text)
    # The material/body portion also gets paragraph recovery, independently of answers.
    boundary=re.search(r'(?m)^##\s+(?:答案与解析|参考答案)\s*$',text)
    pre=text[:boundary.start()] if boundary else text
    post=text[boundary.start():] if boundary else ''
    fm=re.match(r'\A---\n.*?\n---\n',pre,re.S)
    cleaned,material_joins=normalize_paragraphs(pre[fm.end():]);joins+=material_joins
    text=pre[:fm.end()]+cleaned+'\n'+post
    if moved:
        text=text.rstrip()+'\n\n## 来源转录校勘附记\n\n以下题面曾夹在来源答案正文中，现移至附记保留。正式作答要求见正文，附记不作为另一道题或另一份答案。\n\n'
        for item in moved:
            text+='### 原第'+str(item['answer_number'])+'题答案中的来源题面片段\n\n'+item['text'].strip()+'\n\n'
    final=parser.parse(text,rel)
    received=sorted(n for n,q in final['questions'].items() if not pending(final['answers'].get(n,'')) and assess(q,final['answers'].get(n,''))['status']=='已收录')
    missing=sorted(set(final['questions'])-set(received))
    meta={'已收录参考答案题号':received,'缺参考答案题号':missing,'排版规范化凭据':'reports/FULL-REPAIR-LAYOUT-20261015.jsonl'}
    text=set_fields(text,meta,'2026-10-15按当前题目重算作答收录状态，规范段落与兼容汉字；来源原文校勘保留。')
    final=parser.parse(text,rel)
    text=DETAIL.sub(lambda m:'\n<a id="r7-reference-'+m[2]+'"></a>\n'+m[0],text)
    title=re.search(r'(?m)^# [^\n]+\n',text)
    if not title:raise ValueError('Missing title')
    text=text[:title.end()]+reading_guide(final)+text[title.end():]
    check=parser.parse(text,rel)
    if {n:parser.qkey(q) for n,q in check['questions'].items()}!={n:parser.qkey(q) for n,q in d['questions'].items()}:raise ValueError('Question content changed unexpectedly')
    return text.rstrip()+'\n',{'paragraph_joins':joins,'moved_prompt_fragments':moved,'current_answered':received,'current_missing':missing}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--apply',action='store_true');ap.add_argument('--only',action='append');ap.add_argument('--exclude',action='append',default=[]);args=ap.parse_args()
    records=[];errors=[];changes=[]
    for top in ('国考','省考'):
        for p in sorted((ROOT/top).rglob('申论*.md')):
            rel=p.relative_to(ROOT).as_posix();old=p.read_text(encoding='utf-8')
            if rel in args.exclude or (args.only and rel not in args.only):continue
            try:
                new,info=format_essay(old,rel)
                if new!=old:records.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(new),**info});changes.append((p,old,new))
            except Exception as exc:errors.append({'path':rel,'error':str(exc)})
    if args.apply and errors:raise ValueError('Layout contains unresolved errors: '+json.dumps(errors,ensure_ascii=False))
    if args.apply:
        for p,old,new in changes:
            if p.read_text(encoding='utf-8')!=old:raise ValueError('Concurrent paper edit: '+str(p))
            temporary=p.with_name(p.name+'.layout-'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_bytes(new.encode('utf-8'))
                if sha(p.read_text(encoding='utf-8'))!=sha(old):raise ValueError('Concurrent paper edit: '+str(p))
                os.replace(temporary,p)
                if sha(p.read_text(encoding='utf-8'))!=sha(new):raise ValueError('Written paper hash mismatch: '+str(p))
            finally:
                if temporary.exists():temporary.unlink()
        receipt=ROOT/'reports/FULL-REPAIR-LAYOUT-20261015.jsonl'
        previous=receipt.read_text(encoding='utf-8') if args.only and receipt.exists() else ''
        receipt.write_text(previous+''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    print(json.dumps({'apply':args.apply,'papers':len(records),'paragraph_joins':sum(r['paragraph_joins'] for r in records),'prompt_fragments_moved':sum(len(r['moved_prompt_fragments']) for r in records),'errors':errors},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
