"""Check delivered essay paragraphs and preserved answers against repair receipts."""
from __future__ import annotations
from collections import Counter
import hashlib,json,re
from pathlib import Path

DETAIL=re.compile(r'<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>(.*?)</details>',re.S)
def sha(s:str)->str:return hashlib.sha256(s.encode()).hexdigest()

def verify(root:Path)->dict:
    root=root.resolve();checked=0;preserved=0;new_answers=0
    for name in ['ROUND2-ESSAY-20261012.jsonl','ROUND2-LAYOUT-20261012.jsonl']:
        for line in (root/'reports'/name).read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            r=json.loads(line);p=(root/r['path']).resolve()
            if not p.is_relative_to(root) or p.suffix!='.md':raise ValueError('Invalid paper path')
            t=p.read_text(encoding='utf-8');body=t.split('## 答案与解析')[0]
            present=Counter(sha(x.strip()) for x in body.split('\n\n') if x.strip())
            required=Counter(x['sha256'] for x in r.get('source_paragraphs',[]))
            if required-present:raise ValueError('A source material or question paragraph was lost: '+r['path'])
            answers={int(n):a.strip() for n,a in DETAIL.findall(t)}
            for a in r.get('preserved_answers',[]):
                if sha(answers.get(a['number'],''))!=a['answer_sha256']:
                    raise ValueError('Preserved answer differs: '+r['path']+':'+str(a['number']))
                preserved+=1
            for a in r.get('added_answers',[]):
                if a['number'] not in answers:raise ValueError('Added answer missing')
                new_answers+=1
            for a in r.get('answer_sources',[]):
                if a.get('delivered_answer_sha256'):
                    if sha(answers.get(a['number'],''))!=a['delivered_answer_sha256']:raise ValueError('Added layout answer differs')
                    new_answers+=1
            checked+=sum(required.values())
    return {'essay_source_paragraphs_checked':checked,'essay_old_answers_preserved':preserved,'essay_new_answers_checked':new_answers}
