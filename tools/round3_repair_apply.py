#!/usr/bin/env python3
"""Third-round execution adapter; source reads and writes run on GitHub only."""
from __future__ import annotations
import argparse,json,re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import round3_priority_repair as base
from round3_priority_repair import ROOT,sha,plain,load,paragraphs,split_paper,set_fields


def parse_complete(ps,expected):
    """Preserve native numbers, or recover HTML list order from scored stems.
    A scored subquestion must never be mistaken for a new major question.
    """
    ps=list(ps)
    first=next((i for i,t in enumerate(ps) if re.fullmatch(r'一[、.．]?\s*注意事项[：:]?',t)),None)
    if first is not None:ps=ps[first:]
    for i,t in enumerate(ps):
        if t.startswith(('欢迎使用公开真题库','备案编号','若有网络数据')):
            ps=ps[:i];break
    end=next((i for i,t in enumerate(ps) if re.fullmatch(r'三[、.．]?\s*(?:作答|答题|申论)要求[：:]?',t)),None)
    if end is None:raise ValueError('No explicit question section')
    tail=ps[end+1:]
    native=bool(tail and base.QRE.match(tail[0]))
    numbering='source_explicit_question_numbers'
    if not native:
        starts=[i for i,t in enumerate(tail) if re.search(r'[（(]\s*\d+\s*分\s*[）)]\s*[。.]?$',t) and len(t)>18 and not t.startswith(('要求','（','('))]
        if len(starts)!=expected or starts[0]!=0:raise ValueError('Ambiguous HTML scored-stem boundaries '+str(starts))
        for n,i in enumerate(starts,1):tail[i]=f'第{n}题：'+tail[i]
        ps=ps[:end+1]+tail
        numbering='source_scored_paragraph_order_cross_matched_to_existing_stems'
    result=base.parse_whole(ps,expected)
    result['numbering_basis']=numbering
    return result


def render(rel,parsed,src,extras=None):
    new,r=base.render_whole(rel,parsed,src,extras)
    new=set_fields(new,{'题号口径':'完整题源作答段落顺序；同年同卷逐题题干交叉映射'},'2026-10-12第三轮：题号依据与同题映射单独留证')
    r['after_sha256']=sha(new);r['numbering_basis']=parsed['numbering_basis']
    return new,r


def national(item):
    (year,kind),id=item;rel=f'国考/{year}/申论-{kind}.md';url=f'https://www.aipta.com/article/{id}.html'
    try:
        soup,src=load(url);h=soup.select_one('.detail-info h1') or soup.find('h1');title=h.get_text('',strip=True) if h else ''
        if str(year) not in title or ('副省' not in title if kind=='副省级' else kind not in title):raise ValueError('Wrong year/class '+title)
        node=soup.select_one('.info-body')
        if node is None:raise ValueError('Missing article body')
        ps=paragraphs(node)
        # Images occurring in article body require a dedicated visual import, never silent omission.
        imgs=[i.get('src','') for i in node.find_all('img') if i.get('src')]
        if imgs:raise ValueError('Source has images requiring separate inspection: '+str(imgs))
        parsed=parse_complete(ps,4 if (year,kind)==(2016,'地市级') else 5)
        return (*render(rel,parsed,{**src,'title':title}),None)
    except Exception as e:return None,None,{'path':rel,'url':url,'error':str(e),'tail':ps[-8:] if 'ps' in locals() else []}


def old_materials(text):
    result={}
    for n,q in split_paper(text)['qs'].items():
        raw=q['text'].split('### 作答要求')[0]
        for m in re.finditer(r'^材料\s*(\d+)\s*\n(.*?)(?=^材料\s*\d+\s*\n|\Z)',raw,re.M|re.S):
            result[n,int(m[1])]=m[2].strip()
    return result


def retain_material(parsed,number,old,receipt):
    current='\n\n'.join(parsed['materials'][number]);a=plain(old);b=plain(current)
    ratio=SequenceMatcher(None,a,b,autojunk=False).ratio()
    if ratio<.93 or len(a)<.90*len(b):raise ValueError(f'Material identity not established {number}: {ratio:.3f}')
    # Remove PDF soft line wraps only, retaining every non-whitespace character.
    lines=[x.strip() for x in old.splitlines() if x.strip()]
    ps=[];pending=''
    for line in lines:
        pending+=line
        if re.search(r'[。！？][”’」』]?$|[。！？]$',line):ps.append(pending);pending=''
    if pending:ps.append(pending)
    if re.sub(r'\s','',''.join(ps))!=re.sub(r'\s','',old):raise ValueError('Old material altered')
    parsed['materials'][number]=ps
    receipt.append({'material':number,'method':'existing_material_preserved_nonwhitespace','old_sha256':sha(old),'source_variant_sha256':sha(current),'similarity':round(ratio,6),'existing_nonwhitespace_sha256':sha(re.sub(r'\s','',old))})


def get_gk_paper(url):
    soup,src=load(url);ps=paragraphs(soup)
    if not any(base.MRE.fullmatch(x) for x in ps):ps=[x.strip() for x in soup.get_text('\n').splitlines() if x.strip()]
    return parse_complete(ps,3),src


def mountaineer_source():
    url='https://ha.huatu.com/2020/0318/1805454_6.html';s,src=load(url)
    ls=[x.strip() for x in s.get_text('\n').splitlines() if x.strip()]
    a=next(i for i,t in enumerate(ls) if re.match(r'乔治[·.．]马洛里是英国',t))
    b=next(i for i in range(a,len(ls)) if ls[i].startswith('从某种意义上说'))
    ps=ls[a:b+1];full=''.join(ps)
    if not all(k in full for k in ['气瓶','气管','面罩','调节器','辞去','8300','1924']):raise ValueError('Incomplete independent mountaineer paragraph')
    return ps,src


def zhejiang():
    results=[];errors=[]
    try:
        a,asrc=get_gk_paper('https://gwy.gkzhenti.cn/paper/20160802100920')
        b,bsrc=get_gk_paper('https://gwy.gkzhenti.cn/paper/20160802100821')
        if len(a['materials'])!=7 or len(b['materials'])!=7:raise ValueError('Unexpected 2016 material structure')
        if '众筹的特点' not in a['questions'][1] or '讲话稿' not in a['questions'][2] or '提高创业成功率' not in b['questions'][1] or '展板' not in b['questions'][2]:raise ValueError('A/B paper mixed')
        m7,m7src=mountaineer_source()
        for kind,p,src in [('A',a,asrc),('B',b,bsrc)]:
            rel=f'省考/浙江/2016/申论-{kind}类.md';old=(ROOT/rel).read_text();oldm=old_materials(old);overrides=[]
            retain_material(p,2,oldm[1,1],overrides)
            if kind=='A':
                for oldn,newn in [(1,3),(2,4),(3,5)]:retain_material(p,newn,oldm[2,oldn],overrides)
            # A publicly labelled B source has an exact repeated clause and a missing initial character.
            if kind=='B':
                changes=[(4,'每一个项目做完之后，每一个项目做完之后，','每一个项目做完之后，'),(6,'轻女孩小丁','年轻女孩小丁')]
                for n,bad,good in changes:
                    raw='\n\n'.join(p['materials'][n]);witness='\n\n'.join(a['materials'][n])
                    if raw.count(bad)!=1 or good not in witness:raise ValueError('Unproven source correction')
                    p['materials'][n]=[x.replace(bad,good) for x in p['materials'][n]]
                    overrides.append({'material':n,'before':bad,'after':good,'witness':asrc,'method':'exact_local_correction_with_matching_independent_text'})
            original_m7='\n\n'.join(p['materials'][7])
            if SequenceMatcher(None,plain(original_m7),plain(''.join(m7)),autojunk=False).ratio()<.85:raise ValueError('Mountaineer paragraphs differ materially')
            p['materials'][7]=m7
            overrides.append({'material':7,'method':'independent_matching_paragraph_replaces_garbled_OCR','before_sha256':sha(original_m7),'after_sha256':sha('\n\n'.join(m7)),'source':m7src,'scope':'只用同段材料，不沿用该网页错配的A/B作答题'})
            if kind=='A':
                q=p['questions'][3]
                for bad,good in [('乔治·马格里','乔治·马洛里'),('影响力无数','影响了无数')]:
                    if bad not in q:raise ValueError('Expected OCR error absent')
                    q=q.replace(bad,good)
                    overrides.append({'question':3,'before':bad,'after':good,'witness':bsrc})
                p['questions'][3]=q
            p['notes']='> 本卷采用7则材料编排，A/B题目严格分开。旧稿已有材料保持非空白字符；明显乱码的登山材料按另一公开同段来源校订。不同网站的8材料版本、题目分值或字数异文未直接拼入。校订细节见第三轮凭据。'
            # Preserve exact source variants separately; do not mislabel a rendered paragraph as original.
            p['source_paragraphs']=[x for ps in p['materials'].values() for x in ps]+list(p['questions'].values())
            new,r=render(rel,p,src)
            r['material_and_question_corrections']=overrides;r['sources'] += [m7src,bsrc if kind=='A' else asrc]
            results.append((new,r))
    except Exception as e:errors.append({'path':'省考/浙江/2016/申论-A/B类.md','error':str(e)})
    return results,errors


def jiangsu():
    results=[];errors=[]
    try:
        s,src=load('https://iget100.com/gongkao/shengkao/jiangsu/2018/shenlun-a');q,a=base.javascript_free_answers(s)
        results.append(base.answer_patch('省考/江苏/2018/申论-A类.md',src,{n:a[n] for n in [1,3,4]},q))
    except Exception as e:errors.append({'path':'省考/江苏/2018/申论-A类.md','error':str(e)})
    try:
        s,src=load('https://www.yjbys.com/edu/gongwuyuankaoshi/125956.html');ls=[x.strip() for x in s.get_text('\n').splitlines() if x.strip()]
        i=next(i for i,t in enumerate(ls) if re.fullmatch(r'[（(]一[）)]【参考答案】',t));j=next(i for i,t in enumerate(ls) if re.fullmatch(r'[（(]二[）)]【参考答案】',t))
        answer='\n\n'.join(ls[i+1:j])
        results.append(base.answer_patch('省考/江苏/2016/申论-A类.md',src,{1:answer},checks=['完整同卷A类题面及德孝、磨刀老人、红包、家风等案例匹配']))
        # B is the same first question, not the different C-class question. Retain the
        # source's A label instead of inventing an independent B-class publication.
        aold=(ROOT/'省考/江苏/2016/申论-A类.md').read_text();bold=(ROOT/'省考/江苏/2016/申论-B类.md').read_text()
        qa=base.body_questions(aold)[1];qb=base.body_questions(bold)[1]
        mapping=base.match_questions({1:qa},{1:qb})
        if mapping[0]['original_stem_coverage']<.97:raise ValueError('A/B common question not exact enough')
        ma=dict(re.findall(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',aold,re.S|re.M));mb=dict(re.findall(r'^## 给定资料 (\d+)\n(.*?)(?=^## |\Z)',bold,re.S|re.M))
        if set(ma)!=set(mb) or len(ma)!=8:raise ValueError('Different source material range')
        pairs=[]
        for n in ma:
            ratio=SequenceMatcher(None,plain(ma[n]),plain(mb[n]),autojunk=False).ratio()
            if ratio<.97:raise ValueError('A/B material difference requires manual review: '+n+' '+str(ratio))
            pairs.append({'number':int(n),'a_sha256':sha(ma[n]),'b_sha256':sha(mb[n]),'similarity':round(ratio,6)})
        bs,bsource=load('https://gwy.gkzhenti.cn/paper/1512709661015');bt=bs.get_text('',strip=True)
        if '2016年江苏省公考《申论》真题（B卷）' not in bt or '归纳概括出这些现象对形成社会风气所产生的影响' not in bt:raise ValueError('Independent B identity missing')
        text='> **同题参考答案，非独立B卷发布答案。** 下列参考内容来源页面标注A类；经对照，本卷第1题与A类第1题题干、作答范围一致，8则材料逐段交叉核对。保留来源卷型标签，不将C类答案移用，也不称为官方答案。\n\n'+answer
        new,r=base.answer_patch('省考/江苏/2016/申论-B类.md',src,{1:text},checks=['同题异卷来源限制明确标注','8则材料逐段匹配，不以卷型标签相似替代核对'])
        r['sources'].append(bsource);r['common_question_material_evidence']=pairs;r['common_question_mapping']=mapping
        results.append((new,r))
    except Exception as e:errors.append({'path':'省考/江苏/2016/申论-B类.md','error':str(e)})
    return results,errors


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    results,errors=jiangsu();zr,ze=zhejiang();results+=zr;errors+=ze
    with ThreadPoolExecutor(max_workers=6) as ex:
        for new,r,e in ex.map(national,base.NATIONAL.items()):
            if e:errors.append(e)
            else:results.append((new,r))
    for new,r in results:print('READY',json.dumps({k:v for k,v in r.items() if k in ['path','kind','new_questions','questions_after','materials_after','added_answers','points','numbering_basis']},ensure_ascii=False),flush=True)
    for e in errors:print('REJECTED',json.dumps(e,ensure_ascii=False),flush=True)
    if args.apply:
        if len(results)<18:raise ValueError('Unexpected mass rejection; no corpus write')
        rp=ROOT/'reports'/base.RECEIPT
        if rp.exists():raise ValueError('Receipt already exists; use a follow-up repair instead')
        for _,r in results:
            if sha((ROOT/r['path']).read_bytes())!=r['before_sha256']:raise ValueError('Concurrent change')
        for new,r in results:(ROOT/r['path']).write_text(new,encoding='utf-8',newline='\n')
        rp.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for _,r in results),encoding='utf-8')
        (ROOT/'reports/ROUND3-SOURCE-EXCEPTIONS-20261012.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SUMMARY',json.dumps({'ready':len(results),'rejected':len(errors),'new_questions':sum(r['new_questions'] for _,r in results),'new_answers':sum(len(r['added_answers']) for _,r in results),'apply':args.apply},ensure_ascii=False))
if __name__=='__main__':main()
