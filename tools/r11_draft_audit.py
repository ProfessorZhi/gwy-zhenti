#!/usr/bin/env python3
"""Audit candidate answer bodies, not source labels or links; no corpus mutation."""
from __future__ import annotations
import collections,json,re
from pathlib import Path
from r11_lengths import count,limits
from r11_cloud_writer import digest,invalid_body,material_for
ROOT=Path(__file__).resolve().parents[1]

def gather():
    byid={};origins={};duplicates=[]
    for folder in ('r11-drafts','r11-cloud-drafts'):
        for p in sorted((ROOT/'reports'/folder).glob('*.json')):
            entries=json.loads(p.read_text(encoding='utf-8'))
            if not isinstance(entries,list):raise ValueError('Draft must be an array '+str(p))
            for e in entries:
                key=e['id']
                if key in byid:duplicates.append({'id':key,'files':[origins[key],p.relative_to(ROOT).as_posix()]})
                else:byid[key]=e;origins[key]=p.relative_to(ROOT).as_posix()
    # Explicit, separately reviewed overrides never silently replace source drafts.
    for p in sorted((ROOT/'reports/r11-overrides').glob('*.json')):
        for e in json.loads(p.read_text(encoding='utf-8')):
            if not e.get('revision_reason'):raise ValueError('Override requires a revision reason')
            byid[e['id']]=e;origins[e['id']]=p.relative_to(ROOT).as_posix()
    return byid,origins,duplicates

def audit():
    tasks=json.loads((ROOT/'reports/r11-work/tasks.json').read_text(encoding='utf-8'))
    wanted={t['id']:t for t in tasks};drafts,origins,dups=gather();problems=[];ready={};counts=collections.Counter()
    for key,e in drafts.items():
        if key not in wanted:problems.append({'id':key,'issues':['Unknown task id']});continue
        t=wanted[key];q=t['question'];lo,hi=limits(q);s=e.get('answer','');issues=[]
        if not isinstance(s,str) or not s.strip():issues.append('Empty/non-string answer');s=''
        n=count(s)
        if not lo<=n<=hi:issues.append(f'正文{n}字；要求{lo}—{hi}字')
        bad=invalid_body(s,t['kind']=='作文范文')
        if bad:issues.append(bad)
        if 'authorship_kind' in e and e['authorship_kind']=='open_model_original':
            packet=(ROOT/'reports/r11-work/inputs'/('unit-'+t['unit']+'.md')).read_text(encoding='utf-8')
            if e.get('source_packet_sha256')!=digest(packet):issues.append('Writing source packet changed')
            if e.get('question_sha256')!=t['question_sha256']:issues.append('Wrong question hash')
            if e.get('characters')!=n:issues.append('Stored answer length differs')
            if e.get('selected_material_sha256')!=digest(material_for(packet,q,t['kind']=='作文范文')):issues.append('Selected source material differs')
            review=e.get('model_self_review',{})
            if review.get('ok') is not True or review.get('issues')!=[]:issues.append('No successful model content self-review')
            if e.get('model_provenance',{}).get('model_sha256')!='3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597':issues.append('Unrecognized local generation model')
        if issues:problems.append({'id':key,'path':t['path'],'file':origins[key],'characters':n,'min':lo,'max':hi,'issues':issues})
        else:
            ready[key]=e
            counts[e.get('authorship_kind','chatgpt_original')]+=1
    reuse=json.loads((ROOT/'reports/r11-work/reuse.json').read_text(encoding='utf-8'))
    aliases=json.loads((ROOT/'reports/r11-work/aliases.json').read_text(encoding='utf-8'))
    direct={e['id'] for e in reuse};resolved_aliases={a['id'] for a in aliases if a['write_for'] in ready}
    covered=set(ready)|direct|resolved_aliases
    missing=[t['id'] for t in tasks if t['id'] not in covered]
    summary={'stage':'candidate_draft_audit_not_corpus_delivery','baseline_missing':568,'submitted_independent_drafts':len(drafts),
      'validated_draft_bodies':len(ready),'authorship_counts':dict(counts),'existing_source_reuse_candidates':len(direct),
      'resolved_exact_aliases':len(resolved_aliases),'candidate_positions_covered':len(covered),
      'positions_still_without_validated_candidate':len(missing),'missing_ids':missing,'draft_issues':problems,'duplicate_submissions':dups,
      'boundary':'字数、结构、来源绑定与模型自查不等于专家阅卷。原卷尚未在本步骤写回。'}
    return summary,tasks,drafts,ready,origins

def main():
    summary,tasks,drafts,ready,origins=audit()
    out=ROOT/'reports/r11-review';out.mkdir(parents=True,exist_ok=True)
    (out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    groups=collections.defaultdict(list)
    for t in tasks:
        if t['id'] in drafts:groups[t['unit']].append(t)
    for unit,ts in groups.items():
        lines=['# R11 作答审阅 '+unit,'',ts[0]['path'],'']
        for t in ts:
            e=drafts[t['id']];lo,hi=limits(t['question'])
            lines+=['## '+t['id']+' | '+str(count(e.get('answer','')))+'字 | '+str(lo)+'—'+str(hi)+'字','',
               '**原题**','',t['question'],'','**完整作答**','',e.get('answer',''),'','作者性质：'+e.get('author','ChatGPT直接编写的原创示范')+'。',
               '草稿来源文件：'+origins[t['id']],'机器检查：'+('通过' if t['id'] in ready else '有问题，见SUMMARY.json')+'。','']
            if e.get('notes'):lines+=['编辑说明：'+e['notes'],'']
            if e.get('revision_reason'):lines+=['本次修订原因：'+e['revision_reason'],'']
        (out/('unit-'+unit+'.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    status=ROOT/'reports/r11-cloud-status';status.mkdir(parents=True,exist_ok=True)
    (status/'draft-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('R11_DRAFT_AUDIT '+json.dumps({k:v for k,v in summary.items() if k!='missing_ids'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
