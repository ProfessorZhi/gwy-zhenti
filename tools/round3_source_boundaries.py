#!/usr/bin/env python3
"""Explicit source-format corrections, shared by dry-run, application and tests."""
import re
import round3_repair_apply as app
from round3_priority_repair import load,sha

_parse_original=app.parse_complete

def parse_complete(ps,expected):
    corrected=[];edits=[]
    for text in ps:
        m=re.fullmatch(r'(材料|资料)(\d+)[（(](\d{5,})[）)]',text)
        if m:
            clean=m[1]+m[2];edits.append({'source_header':text,'rendered_header':clean,'source_internal_id':m[3]});text=clean
        corrected.append(text)
    result=_parse_original(corrected,expected)
    refs={int(n) for q in result['questions'].values() for n in re.findall(r'给定[材资]料\s*(\d+)',q)}
    if not refs.issubset(result['materials']):raise ValueError('Question references absent global material '+str(sorted(refs-set(result['materials']))))
    result['source_header_corrections']=edits
    return result


def mountaineer_source():
    urls=['https://ha.huatu.com/2020/0318/1805454_5.html','https://ha.huatu.com/2020/0318/1805454_6.html']
    starts=[r'^乔治[·.．]马洛里',r'^当马洛里',r'^马洛里第二次',r'^1924',r'^从某种意义上说']
    original,original_source=app.get_gk_paper('https://gwy.gkzhenti.cn/paper/20160802100920')
    first=original['materials'][7][0]
    if not first.startswith('乔治·马洛里') or '1921年到1924年' not in first:raise ValueError('Original first paragraph identity mismatch')
    found={0:first};sources=[]
    for url in urls:
        soup,src=load(url);sources.append(src)
        ls=[x.strip() for x in soup.get_text('\n').splitlines() if x.strip()]
        for text in ls:
            for i,pattern in enumerate(starts[1:],1):
                if re.match(pattern,text) and len(text)>50:
                    if i in found and found[i]!=text:raise ValueError('Multiple independent material variants')
                    found[i]=text
    if set(found)!=set(range(5)):raise ValueError('Incomplete matching pagination '+str(sorted(found)))
    ps=[found[i] for i in range(5)];text=''.join(ps)
    if not all(x in text for x in ['气瓶','气管','面罩','调节器','辞去','8300','1924']):raise ValueError('Unverified mountaineer wording')
    source={**sources[0],'continuation_sources':sources[1:]+[original_source],'extracted_material_sha256':sha('\n\n'.join(ps)),'scope':'Original first paragraph preserved; only four matching material paragraphs cross-checked; source questions NOT adopted.'}
    return ps,source

_render_original=app.render

def render(rel,parsed,src,extras=None):
    new,r=_render_original(rel,parsed,src,extras)
    r['source_header_corrections']=parsed.get('source_header_corrections',[])
    return new,r

app.parse_complete=parse_complete
app.mountaineer_source=mountaineer_source
app.render=render
if __name__=='__main__':app.main()
