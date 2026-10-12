"""Validate explicit material/question labels in an essay transcript.

This module only parses supplied text. Structural agreement is not proof of
source authenticity. No question, score or reference answer is inferred.
"""
from __future__ import annotations
import hashlib
import re
import unicodedata

NUM={v:i for i,v in enumerate('零一二三四五六七八九十')}
MATERIAL=re.compile(r'^(?:给定)?(?:资料|材料)\s*([0-9一二三四五六七八九十]+)\s*[：:]?$')
LABEL=re.compile(r'^\s*(?:[（(]([一二三四五六七八九十])[）)]|([一二三四五六七八九十])[、．.]|(\d+)[．.、]|第([一二三四五六七八九十])题[：:]?|问题([一二三四五六七八九十])[：:]?)')
SCORE=re.compile(r'[（(]\s*(\d+)\s*分\s*[）)]')
ANSWER_START=re.compile(r'^(?:[【\[]?参考答案[】\]]?$|(?:20\d\d年.*)?[（(]解析[）)]$|\d+[、.]参考答案[：:]?$)')

def digest(text: str)->str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def number(value: str)->int:
    return int(value) if value.isdigit() else NUM[value]

def prompt_key(text: str)->str:
    text=LABEL.sub('',text.strip(),count=1)
    text=SCORE.sub('',text.split('要求')[0]).replace('给定材料','给定资料')
    return ''.join(c for c in unicodedata.normalize('NFKC',text) if c.isalnum())

def parse_transcript(paragraphs: list[str], *, question_count: int, material_count: int)->dict:
    if not isinstance(paragraphs,list) or not all(isinstance(p,str) for p in paragraphs):
        raise ValueError('Expected text paragraphs')
    if not 2 <= question_count <= 6 or not 1 <= material_count <= 50:
        raise ValueError('Reviewed paper dimensions out of range')
    ps=[p.strip() for p in paragraphs if p.strip()]
    if any('\ufffd' in p for p in ps):raise ValueError('Source decoding lost characters')
    gap=re.compile(r'给定(?:材料|资料)暂缺|本题暂缺|全力以赴征集|材料缺失|作答要求缺失')
    if any(gap.search(p) for p in ps):raise ValueError('Explicit source gap')
    mids=[]
    for i,p in enumerate(ps):
        m=MATERIAL.fullmatch(p)
        if m:mids.append((i,number(m[1])))
    if [n for i,n in mids]!=list(range(1,material_count+1)):
        raise ValueError('Material IDs/count differ from reviewed source')
    stops=[i for i,p in enumerate(ps) if i>mids[-1][0] and ANSWER_START.fullmatch(p)]
    end=stops[0] if stops else len(ps)
    starts=[]
    for i in range(mids[-1][0]+1,end):
        label=LABEL.match(ps[i]);score=SCORE.search(ps[i])
        if label and score:starts.append((i,number(next(g for g in label.groups() if g)),int(score[1])))
    if [n for i,n,v in starts]!=list(range(1,question_count+1)):
        raise ValueError('Explicit question IDs differ from reviewed sequence')
    if sum(v for i,n,v in starts)!=100:raise ValueError('Explicit points do not total 100')
    mats=[]
    for j,(i,n) in enumerate(mids):
        stop=mids[j+1][0] if j+1<len(mids) else starts[0][0]
        paras=[p for p in ps[i+1:stop] if not re.fullmatch(r'(?:[一二三四五][、．.]\s*)?(?:作答要求|答题要求)',p)]
        if len(''.join(paras))<40:raise ValueError('Material empty or implausibly short')
        mats.append({'number':n,'paragraphs':paras})
    questions=[]
    for j,(i,n,v) in enumerate(starts):
        stop=starts[j+1][0] if j+1<len(starts) else end
        req=ps[i+1:stop]
        if not req or not any('要求' in p for p in req) or not re.search(r'\d+[^\n]{0,12}字',''.join(req)):
            raise ValueError('Visible requirements and word limit required')
        questions.append({'number':n,'stem':ps[i],'requirements':req,'score':v})
    intro=[i for i,p in enumerate(ps[:mids[0][0]]) if re.fullmatch('[一二三四五][、．.]注意事项',p)]
    start=intro[0] if intro else 0
    instructions=[p for p in ps[start:mids[0][0]] if not re.fullmatch('[一二三四五][、．.]给定(?:材料|资料)',p)]
    return {'instructions':instructions,'materials':mats,'questions':questions,'answer_paragraphs':ps[end:] if end<len(ps) else []}

def source_variants(title: str)->set[str]:
    """All explicitly written A/B/C labels, never infer unstated variants."""
    if re.search('模拟|模考|预测|事业单位',title):return set()
    if '选调' in title:
        # Some public titles explicitly list a civil-service A paper shared with
        # an ordinary selection paper. Accept A only, never invent a selection file.
        common = re.search(r'[（(]A[、,，](?:普通|乡镇)选调卷[）)]',title)
        return {'A'} if common and re.search('公考|省考|公务员考试',title) else set()
    variants=set()
    for group in re.findall(r'[（(]([^）)]+)[）)]',title):
        if re.fullmatch(r'[ABC卷类、,，+＋/与和\s]+',group):
            variants.update(re.findall('[ABC]',group))
    return variants

def parse_publisher_answers(paragraphs: list[str], expected: int)->dict[int,str]:
    markers=[]
    for i,p in enumerate(paragraphs):
        m=re.match(r'^[（(]([一二三四五六])[）)]\s*[【\[]参考(?:答案|范文|例文)[】\]]',p)
        if m:markers.append((i,number(m[1])))
    if not markers or [n for i,n in markers]!=list(range(1,expected+1)):return {}
    end=next((i for i,p in enumerate(paragraphs) if p.startswith(('环球网校友情提示','编辑推荐'))),len(paragraphs))
    out={}
    for j,(i,n) in enumerate(markers):
        stop=markers[j+1][0] if j+1<len(markers) else end
        text='\n\n'.join(paragraphs[i+1:stop]).strip()
        if len(text)<40 or text.endswith(('......','未完','待续')):
            raise ValueError('Truncated or empty reference answer')
        out[n]=text
    return out
