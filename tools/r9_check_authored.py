#!/usr/bin/env python3
"""Check actual authored answer text against the frozen, source-derived task map."""
from __future__ import annotations
import argparse,collections,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def characters(text):
    return len(re.sub(r'\s|\*|(?m:^#{1,6}\s*)','',text))

def read_drafts():
    manifest=json.loads((ROOT/'reports/r9-context/manifest.json').read_text(encoding='utf-8'))
    tasks={t['id']:t for t in manifest['tasks']}
    edits_file=ROOT/'reports/r9-authored-corrections.json'
    edits=json.loads(edits_file.read_text(encoding='utf-8')) if edits_file.is_file() else []
    by_id=collections.defaultdict(list)
    for edit in edits:
        if edit['id'] not in tasks or not edit['find']:raise ValueError('Invalid manual correction')
        by_id[edit['id']].append(edit)
    found={};issues=[];seen_text={}
    for file in sorted((ROOT/'reports/r9-authored').glob('*.json')):
        rows=json.loads(file.read_text(encoding='utf-8'))
        if not isinstance(rows,list):raise ValueError('Draft file is not an array: '+str(file))
        for row in rows:
            key=row.get('id')
            if key not in tasks or key in found:raise ValueError('Unknown or duplicate task ID '+str(key))
            if row.get('authorship') not in ('ChatGPT原创参考作答，未经实考评分','ChatGPT原创学习范文，未经实考评分'):
                raise ValueError('Missing honest authorship label '+key)
            answer=row.get('answer','')
            if not isinstance(answer,str) or not answer.strip():raise ValueError('Empty answer '+key)
            for edit in by_id.get(key,[]):
                if answer.count(edit['find'])!=1:raise ValueError('Manual correction is not uniquely anchored '+key)
                answer=answer.replace(edit['find'],edit['replace'],1)
            if any(x in answer for x in ('</details>','<script','TODO','待补答案','此处填写','略。')):
                raise ValueError('Placeholder/unsafe markup in '+key)
            if re.search(r'(^|\n)(写作思路|答题步骤|以下是|作为AI)',answer):
                issues.append({'id':key,'issue':'unexpected_meta_answer'})
            digest=hashlib.sha256(re.sub(r'\s','',answer).encode()).hexdigest()
            if digest in seen_text:issues.append({'id':key,'issue':'duplicate_answer','other':seen_text[digest]})
            seen_text[digest]=key
            task=tasks[key];n=characters(answer);lo,hi=task['word_range']
            if hi:
                if lo<hi:
                    minimum,maximum=lo,hi
                elif '不超过' in task['question'] or '以内' in task['question']:
                    minimum,maximum=max(50,int(hi*.45)),hi
                elif '左右' in task['question']:
                    minimum,maximum=int(hi*.85),int(hi*1.15)
                else:
                    minimum,maximum=max(50,int(hi*.8)),int(hi*1.1)
                if n<minimum or n>maximum:
                    issues.append({'id':key,'issue':'word_count','actual':n,'allowed':[minimum,maximum],
                                   'path':task['path'],'number':task['number']})
            elif n<50:issues.append({'id':key,'issue':'answer_too_short','actual':n})
            if task['kind']=='作文范文' and len([p for p in answer.split('\n\n') if p.strip()])<5:
                issues.append({'id':key,'issue':'essay_not_full_paragraphs'})
            if not re.search(r'[。！？!?）】]$',answer.strip()):
                issues.append({'id':key,'issue':'possibly_cutoff_last_sentence'})
            found[key]={**row,'answer':answer,'characters':n,'task':task,'answer_sha256':hashlib.sha256(answer.encode()).hexdigest()}
    if set(by_id)-set(found):raise ValueError('Correction refers to unwritten draft')
    return tasks,found,issues,manifest['unparsed']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--require-all',action='store_true');args=ap.parse_args()
    tasks,found,issues,unparsed=read_drafts()
    summary={'frozen_pending_positions':len(tasks),'authored_positions':len(found),
      'documents_with_authored_answers':len({x['task']['path'] for x in found.values()}),
      'not_yet_authored':len(tasks)-len(found),'unparsed_documents':len(unparsed),
      'by_kind':dict(collections.Counter(x['task']['kind'] for x in found.values())),'issues':issues,
      'boundary':'Draft integrity and length only; not proof of semantic quality or MD delivery.'}
    print('R9_DRAFT_CHECK '+json.dumps(summary,ensure_ascii=False),flush=True)
    if issues:raise ValueError('Authored drafts require correction')
    if args.require_all and set(tasks)!=set(found):raise ValueError('Not all frozen pending positions are written')
if __name__=='__main__':main()
