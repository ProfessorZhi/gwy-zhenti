#!/usr/bin/env python3
"""Verify the delivered third-round bytes, not merely the generator exit code."""
import hashlib,json,re
from pathlib import Path
from paper_integrity_repair import split_paper

def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def verify(root):
    root=Path(root).resolve();records=[json.loads(x) for x in (root/'reports/ROUND3-ESSAY-20261012.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    seen=set();preserved=0;material_count=0;question_count=0;added=0
    for r in records:
        rel=r['path'];p=(root/rel).resolve()
        if rel in seen or not p.is_relative_to(root):raise ValueError('Duplicate/unsafe path')
        seen.add(rel);text=p.read_text(encoding='utf-8');d=split_paper(text)
        if digest(text)!=r['after_sha256']:raise ValueError('Round3 delivered hash mismatch '+rel)
        if len(d['qs'])!=r['questions_after']:raise ValueError('Question count mismatch '+rel)
        if set(d['qs'])!=set(d['answers']):raise ValueError('Question/answer ids mismatch')
        for n,h in r['answer_hashes'].items():
            if digest(d['answers'][int(n)])!=h:raise ValueError('Answer bytes changed')
        for a in r['preserved_answers']:
            if digest(d['answers'][a['number']])!=a['sha256']:raise ValueError('Historical answer altered '+rel)
            preserved+=1
        if r['kind']=='answer_only':
            if digest(text.split('---',2)[2].split('## 答案与解析')[0])!=r['body_sha256']:raise ValueError('Answer-only repair altered body')
        else:
            mats=dict(re.findall(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',text,re.M|re.S))
            if set(mats)!=set(r['material_hashes']):raise ValueError('Material keys mismatch')
            for n,h in r['material_hashes'].items():
                if digest(mats[n].strip())!=h:raise ValueError('Material changed '+rel+':'+n)
                material_count+=1
            for n,h in r['question_hashes'].items():
                q=d['qs'][int(n)]['text'].split('### 作答要求')[-1].strip()
                if digest(q)!=h or not re.search(r'\d+\s*字',q):raise ValueError('Question/word-limit integrity mismatch '+rel+':'+n)
                question_count+=1
            if sum(r['points'])!=100:raise ValueError('Score sum mismatch')
            for change in r.get('material_and_question_corrections',[]):
                if change.get('method')=='existing_material_preserved_nonwhitespace':
                    current=re.sub(r'\s','',mats[str(change['material'])])
                    if digest(current)!=change['existing_nonwhitespace_sha256']:raise ValueError('Old material content lost')
        for source in r['sources']:
            if not re.fullmatch(r'[a-f0-9]{64}',source['sha256']) or not source['url'].startswith(('http://','https://')):raise ValueError('Missing source hash/url')
        added+=len(r['added_answers'])
    if len(records)<18:raise ValueError('Unexpectedly empty/short delivery')
    return {'status':'passed','papers':len(records),'preserved_answers':preserved,'checked_material_blocks':material_count,'checked_full_question_blocks':question_count,'added_reference_answers':added,'new_major_questions':sum(r['new_questions'] for r in records),'boundary':'Source-backed transcription and historical answer preservation, not official-original certification.'}
if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False,sort_keys=True))
