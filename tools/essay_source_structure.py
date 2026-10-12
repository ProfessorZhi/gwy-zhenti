"""Parse a public, data-only essay transcript with explicit sections and scores.

This validates the transcript's internal structure, not official authenticity.
No guessed question, missing requirement, skipped material or answer is generated.
"""
from __future__ import annotations
import re

MATERIAL = re.compile(r'^材料\s*(\d+)(?:\s*[（(]\d+[）)])?[：:]?$')
SCORE = re.compile(r'[（(]\s*(\d+)\s*分\s*[）)]')

def parse_paragraphs(paragraphs: list[str], *, expected_title: str, actual_title: str) -> dict:
    if expected_title.strip() != actual_title.strip():
        raise ValueError('Source title/selected identity mismatch')
    ps=[p.strip() for p in paragraphs if p.strip()]
    if any(re.search(r'本题暂缺|全力以赴征集|给定(?:材料|资料)暂缺|尚未收集',p) for p in ps):
        raise ValueError('Source contains an explicit gap')
    ps=[p for p in ps if not p.startswith('注：篇幅有限')]
    material_sections=[i for i,p in enumerate(ps) if re.fullmatch(r'(?:[一二三四五][、．.]\s*)?给定(?:材料|资料)',p)]
    question_sections=[i for i,p in enumerate(ps) if re.fullmatch(r'(?:[一二三四五][、．.]\s*)?作答要求',p)]
    if len(material_sections)!=1 or len(question_sections)!=1:
        raise ValueError('Unique given-material/question sections required')
    ma,qa=material_sections[0],question_sections[0]
    if ma>=qa:raise ValueError('Material and question sections reversed')
    blocks=[];current=None
    for i in range(ma+1,qa):
        m=MATERIAL.fullmatch(ps[i])
        if m:
            current={'number':int(m[1]),'label':ps[i],'paragraphs':[]};blocks.append(current)
        elif current:current['paragraphs'].append(ps[i])
        else:raise ValueError('Unassigned material paragraph')
    if not blocks or [m['number'] for m in blocks]!=list(range(1,len(blocks)+1)):
        raise ValueError('Nonsequential material IDs')
    if any(not b['paragraphs'] for b in blocks):raise ValueError('Empty material')
    points=[(i,int(SCORE.search(p)[1])) for i,p in enumerate(ps) if i>qa and SCORE.search(p)]
    if not 2<=len(points)<=6 or sum(v for i,v in points)!=100:
        raise ValueError('Question count or total scores unverified')
    questions=[]
    for j,(i,score) in enumerate(points):
        end=points[j+1][0] if j+1<len(points) else len(ps)
        req=ps[i+1:end]
        if not req or not any('要求' in p for p in req) or not any(re.search(r'\d+.*字',p) for p in req):
            raise ValueError('Complete visible requirements and word limit required')
        if len(ps[i])<15:raise ValueError('Question stem missing')
        questions.append({'number':j+1,'stem':ps[i],'requirements':req,'score':score,'source_paragraph':i})
    return {'instructions':ps[:ma],'materials':blocks,'questions':questions,'paragraphs':ps}
