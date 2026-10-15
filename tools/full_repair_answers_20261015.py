"""Apply reviewed, explicitly attributed full answers; never infer an exam task.

Input: a JSON array (or {'answers': [...]}) with path, number, answer,
attribution_kind, author, sources[{title,url}], optional question,
target_word_range, replace_reason. Existing non-placeholder answers cannot be
replaced without an explicit correction reason. --check validates without writes.
"""
from __future__ import annotations
import argparse,collections,hashlib,html,json,re,os,uuid
from pathlib import Path
import round5_bulk as parser
import round4_gap_repair as g
from round4_delivery import is_missing
import r7_reference_audit as audit

ROOT=Path(__file__).resolve().parents[1]
PENDING=re.compile(r'^(?:本题)?(?:参考答案)?(?:尚未收录|尚未|未收录|暂无|暂缺|未取得|待核|待补)')

def pending(text):
    s=re.sub(r'^[\s>*]+','',text)
    return is_missing(text) or bool(PENDING.match(s))

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def answer_characters(answer):
    answer=re.sub(r'<!--.*?-->','',answer,flags=re.S)
    answer=re.sub(r'<[^>]+>','',answer)
    return len(re.sub(r'\s|[#*`]','',html.unescape(answer)))

def validate_answer(question,entry):
    answer=entry['answer'].strip()
    if pending(answer) or '\ufffd' in answer or re.search(r'答案(?:暂缺|略)|待(?:补充|填写)|TODO|PLACEHOLDER',answer,re.I):
        raise ValueError('Placeholder/invalid answer')
    n=answer_characters(answer)
    if n<45:raise ValueError('Answer too short: '+str(n))
    # Explicit differently capped subquestions cannot share a fictional total cap.
    from full_repair_precise_answer_audit_20261015 import word_rules,inspect_version
    subrules=word_rules(question)
    distinct_subquestions=False
    if subrules['kind']=='multiple_task_limits':
        version={'body':answer,'characters':n,'analysis_only':False}
        _,findings=inspect_version(question,version,subrules)
        if version.get('per_item_characters'):
            if findings:raise ValueError('Exceeds separately numbered subquestion limits: '+str(findings))
            distinct_subquestions=True
    bounds=entry.get('target_word_range')
    if not bounds or not any(bounds):bounds=audit.word_range(question)
    lo,hi=(bounds+[0,0])[:2] if isinstance(bounds,list) else bounds
    if distinct_subquestions:lo=hi=0
    # Maximums are requirements; long tasks must contain an actual full body.
    maximum=bool(re.search(r'(?:不(?:得)?(?:超过|多于)|不超)\s*\d+\s*字|\d+\s*字\s*(?:以内|以下|之内|内|为限)',question))
    minimum_only=bool(re.search(r'(?:不少于|不低于|至少)\s*\d+\s*字|\d+\s*字\s*以上',question)) and not maximum and lo==hi
    per_item=re.search(r'每个问题[^。；]{0,18}不(?:得)?超过\s*(\d+)\s*字',question)
    if per_item:
        parts=[p.strip() for p in re.split(r'(?m)(?=^第[一二三四五六七八九十]+[，、：])',answer) if p.strip()]
        expected=re.search(r'讨论了([一二三四五六七八九十\d]+)个问题',question)
        numerals={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
        expected_count=numerals.get(expected[1],int(expected[1]) if expected[1].isdigit() else 0) if expected else 0
        if len(parts)<2 or (expected_count and len(parts)!=expected_count):raise ValueError('Per-question limit requires separately numbered complete answers')
        if any(answer_characters(p)>int(per_item[1]) for p in parts):raise ValueError('Exceeds per-question maximum')
    if maximum and not per_item and hi and n>hi:raise ValueError(f'Exceeds maximum {n}>{hi}')
    if lo and hi and lo!=hi and n<lo:raise ValueError(f'Below required range {n}<{lo}')
    if lo and hi and lo!=hi and n>hi:raise ValueError(f'Exceeds required range {n}>{hi}')
    if hi and not lo and n>hi:raise ValueError(f'Exceeds upper-only bound {n}>{hi}')
    if lo and not hi and n<lo:raise ValueError(f'Below lower-only bound {n}<{lo}')
    if lo and re.search(r'(?:不少于|不低于|至少)\s*\d+\s*字|\d+\s*字\s*以上',question) and n<lo:raise ValueError(f'Below explicit minimum {n}<{lo}')
    if lo>=300 and lo==hi and re.search(r'字\s*左右',question) and n<int(lo*.90):raise ValueError(f'Below approximate length {n}<{int(lo*.90)}')
    if hi>=700:
        minimum=lo if lo!=hi else int(lo*.90)
        if n<minimum:raise ValueError(f'Long task incomplete {n}<{minimum}')
        if not maximum and lo!=hi and n>hi:raise ValueError(f'Exceeds range {n}>{hi}')
        if lo==hi and not minimum_only and n>int(hi*1.12):raise ValueError(f'Exceeds approximate word count {n}>{hi}')
    if not entry.get('attribution_kind') or not entry.get('author'):raise ValueError('Missing authorship nature')
    for source in entry.get('sources',[]):
        if not source.get('title') or not re.match(r'https://',source.get('url','')):raise ValueError('Invalid source citation')
    return n

def render_answer(entry):
    kind=entry['attribution_kind'];answer=entry['answer'].strip()
    if kind=='ai_revision':
        heading='AI辅助修订示范作答'
        note='依据本卷材料和作答要求，对已有来源参考正文作压缩、补足或纠错修订；不是来源作者原稿，不是官方答案，未经实考评分。'
    elif kind in ('ai_original','original','AI辅助原创示范'):
        heading='AI辅助原创示范作答'
        note='AI辅助原创示范，依据本卷给定材料与作答要求独立编写；不是官方答案，未经实考评分。'
    else:
        heading='同题来源参考作答'
        note='同题来源参考版本；署名以原稿为准，不是官方答案，实考得分未核实，不标作真实高分卷。'
    note+=' 作者／整理性质：'+entry['author']+'。'
    if entry.get('replace_reason'):note+=' 本次纠错：'+entry['replace_reason']+'。'
    text='**'+heading+'**\n\n<!-- full-repair-answer-20261015 -->\n'+answer+'\n<!-- /full-repair-answer-20261015 -->\n\n> 来源说明：'+note
    if entry.get('sources'):
        text+='\n\n'+'\n\n'.join('['+s['title'].replace(']','）')+']('+s['url']+')'+('（'+s['author']+'）' if s.get('author') else '') for s in entry['sources'])
        if kind in ('ai_original','original','AI辅助原创示范'):text+='\n\n> 上述机构／原稿链接用于题面和要点交叉对照，示范正文由本次独立编写。'
        elif kind=='ai_revision':text+='\n\n> 上述链接为修订所据原参考版本；修订后的表述不归属于原作者。'
    return text

def apply_entries(root,entries,write=True):
    root=Path(root);by_path=collections.defaultdict(list);seen=set();receipts=[];errors=[]
    for row in entries:
        key=(row['path'],int(row['number']))
        if key in seen:raise ValueError('Duplicate path/number '+str(key))
        seen.add(key);by_path[row['path']].append(row)
    ready=[]
    for rel,adds in by_path.items():
        try:
            p=(root/rel).resolve()
            if not p.is_relative_to(root.resolve()) or '/申论' not in rel:raise ValueError('Unsafe/non-essay path')
            old=p.read_text(encoding='utf-8');d=parser.parse(old,rel)
            rendered={};metrics=[]
            for e in adds:
                n=int(e['number'])
                if n not in d['questions']:raise ValueError('Unknown task '+str(n))
                q=d['questions'][n]
                if e.get('question') and parser.qkey(e['question'])!=parser.qkey(q):raise ValueError('Task text mismatch '+str(n))
                previous=d['answers'].get(n,'')
                if not pending(previous) and not e.get('replace_reason'):raise ValueError('Existing reference preserved; explicit correction reason required: '+str(n))
                count=validate_answer(q,e);rendered[n]=render_answer(e)
                metrics.append({'number':n,'answer_characters':count,'question_sha256':digest(q),'answer_sha256':digest(e['answer'].strip()),'attribution_kind':e['attribution_kind'],'author':e['author'],'sources':e.get('sources',[]),'replaces_nonempty':not pending(previous),'replace_reason':e.get('replace_reason')})
            new=old
            if d['answer_heading']:
                present=set()
                def sub(m):
                    n=int(m[2]);present.add(n)
                    return m[1]+'\n\n'+rendered[n]+'\n\n'+m[4] if n in rendered else m[0]
                new=g.DETAIL.sub(sub,new)
                absent=set(rendered)-present
                if absent:
                    new=new.rstrip()+'\n\n'+'\n\n'.join('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+rendered[n]+'\n\n</details>' for n in sorted(absent))+'\n'
            else:
                if d['mode']=='unstructured':
                    for n,at in sorted(d['question_spans'].items(),key=lambda x:x[1],reverse=True):new=new[:at]+'\n## 第 '+str(n)+' 题\n\n'+new[at:]
                new=new.rstrip()+'\n\n## 答案与解析\n\n'+'\n\n'.join('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+rendered.get(n,d['answers'].get(n,'本题尚未收录可核对的完整参考作答。'))+'\n\n</details>' for n in d['questions'])+'\n'
            nd=parser.parse(new,rel)
            if {n:parser.qkey(q) for n,q in nd['questions'].items()}!={n:parser.qkey(q) for n,q in d['questions'].items()}:raise ValueError('Question changed during answer insertion')
            for n,a in d['answers'].items():
                if n not in rendered and nd['answers'].get(n)!=a:raise ValueError('Unrelated answer changed')
            receipts.append({'path':rel,'before_sha256':digest(old),'after_sha256':digest(new),'added_answers':metrics})
            ready.append((p,old,new))
        except Exception as exc:errors.append({'path':rel,'error':str(exc)})
    if errors:return {'status':'failed','errors':errors,'papers_ready':len(ready)},receipts
    if write:
        for p,old,new in ready:
            temporary=p.with_name(p.name+'.answer-'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_bytes(new.encode('utf-8'))
                if digest(p.read_text(encoding='utf-8'))!=digest(old):raise ValueError('Concurrent paper edit: '+str(p))
                os.replace(temporary,p)
                if digest(p.read_text(encoding='utf-8'))!=digest(new):raise ValueError('Written paper hash mismatch: '+str(p))
            finally:
                if temporary.exists():temporary.unlink()
    return {'status':'passed','applied':write,'papers':len(ready),'answers':len(entries),'errors':[]},receipts

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('data',type=Path);ap.add_argument('--check',action='store_true');ap.add_argument('--receipt',type=Path);args=ap.parse_args()
    data=json.loads(args.data.read_text(encoding='utf-8'));entries=data['answers'] if isinstance(data,dict) else data
    result,receipts=apply_entries(ROOT,entries,not args.check)
    if args.receipt and not args.check and result['status']=='passed':args.receipt.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in receipts),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(result['status']!='passed')
if __name__=='__main__':main()
