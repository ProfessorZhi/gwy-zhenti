"""Preserve demonstrated mixed/duplicate Beijing transcripts outside real papers."""
import hashlib,json,os,re,uuid
from pathlib import Path
from difflib import SequenceMatcher
import round5_bulk as parser
from paper_integrity_repair import set_fields
ROOT=Path(__file__).resolve().parents[1]
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def write(p,text):
    p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name(p.name+'.archive-'+uuid.uuid4().hex+'.tmp')
    try:temp.write_bytes(text.encode());os.replace(temp,p)
    finally:
        if temp.exists():temp.unlink()
def main():
    proof=ROOT/'reports/FULL-REPAIR-IDENTITY-DISPOSITION-20261015.json'
    data=json.loads(proof.read_text(encoding='utf-8'));plans=[]
    for year in (2020,2021,2022):
        old=f'省考/北京/{year}/申论-统考.md'
        dest=f'docs/来源校勘/北京{year}申论-原统考'+('混卷来源' if year<2022 else '重复来源')+'.md'
        p=ROOT/old;q=ROOT/dest
        if old in data['relocations']:raise ValueError('Already archived')
        if q.exists():raise ValueError('Archive already exists')
        text=p.read_text(encoding='utf-8')
        if year<2022 and '混卷' not in text:raise ValueError('Missing mixed-source evidence')
        if year==2022:
            canonical=f'省考/北京/{year}/申论-区级.md';correct=(ROOT/canonical).read_text(encoding='utf-8')
            a=parser.parse(text,old);b=parser.parse(correct,canonical)
            if len(a['questions'])!=4 or len(b['questions'])!=4:raise ValueError('Unexpected 2022 tasks')
            matches=[]
            for n,question in a['questions'].items():
                scores=sorted((SequenceMatcher(None,parser.qkey(question),parser.qkey(v),autojunk=False).ratio(),m) for m,v in b['questions'].items())
                if scores[-1][0]<.88:raise ValueError('Insufficient same-exam match')
                matches.append({'old':n,'canonical':scores[-1][1],'similarity':scores[-1][0]})
            if len({v['canonical'] for v in matches})!=4:raise ValueError('Nonunique 2022 correspondence')
        archive=set_fields(text,{'收录状态':'来源校勘档案，不计独立真题分卷','身份校核凭据':'reports/FULL-REPAIR-BEIJING-ARCHIVE-20261015.json'},'2026-10-15旧统考来源经逐题校核后归档；正文及旧作答完整保留。')
        title=re.search(r'(?m)^# [^\n]+\n',archive)
        notice='\n> **来源校勘留存稿。** '+('旧文件混合区级与乡镇两套试题，正式入口见对应年度两份完整分卷。' if year<2022 else '本稿与2022统一卷为同四题不同来源排序，不计另一独立原卷。')+' 原文与原作答保留供比对。依据及逐题映射见 [北京分卷恢复报告](../../reports/FULL-REPAIR-BEIJING-ESSAY-RECONSTRUCTION-20261015.json)。\n'
        archive=archive[:title.end()]+notice+archive[title.end():]
        plans.append({'old':old,'destination':dest,'old_text':text,'new_text':archive.rstrip()+'\n'})
    # Prepare the canonical unified 2022 paper before changing any paths.
    source=ROOT/'省考/北京/2022/申论-区级.md';source_text=source.read_text(encoding='utf-8')
    unified=set_fields(source_text,{'卷型':'统考','卷型校核依据':'2022起不再分区级和乡镇申论；同四题统一试卷'},'2026-10-15依据当年考后报道与逐题对应确认统一卷，纠正历史区级文件名。')
    unified=re.sub(r'(?m)^# .*$', '# 2022年北京市公务员考试《申论》试题（统一卷）',unified,count=1).rstrip()+'\n'
    for plan in plans:
        p=(ROOT/plan['old']).resolve();q=(ROOT/plan['destination']).resolve()
        if not p.is_relative_to(ROOT/'省考/北京') or not q.is_relative_to(ROOT/'docs/来源校勘'):raise ValueError('Path outside reviewed boundary')
        if p.read_text(encoding='utf-8')!=plan['old_text']:raise ValueError('Concurrent edit')
        write(q,plan['new_text'])
        if sha(q.read_text(encoding='utf-8'))!=sha(plan['new_text']):raise ValueError('Archive write mismatch')
        # Exact resolved paper targets have been verified above; archive exists.
        p.unlink()
        data['relocations'][plan['old']]=plan['destination']
    if source.read_text(encoding='utf-8')!=source_text:raise ValueError('Canonical source changed')
    write(ROOT/'省考/北京/2022/申论-统考.md',unified)
    source.unlink()
    data['relocations']['省考/北京/2022/申论-区级.md']='省考/北京/2022/申论-统考.md'
    receipt={'archived':[{'path':p['old'],'destination':p['destination'],'before_sha256':sha(p['old_text']),'after_sha256':sha(p['new_text'])} for p in plans],'canonical_rename':{'old':'省考/北京/2022/申论-区级.md','new':'省考/北京/2022/申论-统考.md','before_sha256':sha(source_text),'after_sha256':sha(unified)},'same_2022_question_matches':matches,'unified_exam_evidence':'https://bj.people.com.cn/n2/2021/1213/c82840-35047589.html','boundary':'No source text discarded. Canonical filenames reflect actual exam variants; all historical files are recoverable from the outer receipts.'}
    write(ROOT/'reports/FULL-REPAIR-BEIJING-ARCHIVE-20261015.json',json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    write(proof,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'archived':3,'renamed':1,'same_2022_question_matches':matches},ensure_ascii=False))
if __name__=='__main__':main()
