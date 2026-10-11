#!/usr/bin/env python3
"""Apply a reviewed four-paper plan; never infer missing exam questions.

PDFs are data only, pinned by SHA-256. Old question, option, material and answer
bodies are preserved after block-edge whitespace. Only order/headings change.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'国考/2022/行测-副省级.md', '省考/江苏/2023/行测-B类.md',
           '省考/广东/2020/行测-县级卷.md', '省考/浙江/2020/行测-A类.md'}
QH = re.compile(r'^(#{2,3}) 第 (\d+) 题[^\n]*\n', re.M)
MH = re.compile(r'^## 材料[^\n]*\n', re.M)
ANS = re.compile(r'<details>\s*<summary>第 (\d+) 题</summary>(.*?)</details>', re.S)
FM = re.compile(r'\A---\n(.*?)\n---\n', re.S)


def sha(b): return hashlib.sha256(b).hexdigest()


def split_paper(t):
    front, answers = t.split('## 答案与解析', 1)
    tokens = sorted([(m.start(), m.end(), 'q', m) for m in QH.finditer(front)] +
                    [(m.start(), m.end(), 'm', m) for m in MH.finditer(front)])
    qs, mats, material = {}, {}, None
    for i, (start, end, typ, m) in enumerate(tokens):
        body = front[end:tokens[i+1][0] if i+1 < len(tokens) else len(front)].strip()
        if typ == 'm':
            material = 'm'+str(len(mats)+1)
            mats[material] = dict(header=m.group(0).strip(), text=body)
        else:
            if m.group(1) == '##': material = None
            n = int(m.group(2))
            if n in qs: raise ValueError('Duplicate question number')
            qs[n] = dict(header=m.group(0).strip(), text=body, material=material)
    aa = {}
    for m in ANS.finditer(answers):
        n = int(m.group(1))
        if n in aa: raise ValueError('Duplicate answer number')
        aa[n] = m.group(2).strip()
    if set(aa) != set(qs): raise ValueError('Old answers do not bijectively match questions')
    return dict(prefix=front[:tokens[0][0]], qs=qs, materials=mats, answers=aa)


def set_fields(prefix, fields, annotation):
    m = FM.match(prefix)
    if not m: raise ValueError('Missing frontmatter')
    lines = m.group(1).splitlines()
    found = set()
    for i, line in enumerate(lines):
        k = line.split(':', 1)[0]
        if k in fields:
            lines[i] = k+': '+json.dumps(fields[k], ensure_ascii=False)
            found.add(k)
        elif k == '校验状态':
            old = json.loads(line.split(':',1)[1])
            lines[i] = k+': '+json.dumps(old+'；'+annotation, ensure_ascii=False)
    for k, v in fields.items():
        if k not in found: lines.append(k+': '+json.dumps(v, ensure_ascii=False))
    return '---\n'+'\n'.join(lines)+'\n---\n'+prefix[m.end():]


def validate_plan(spec, old):
    if spec['path'] not in ALLOWED: raise ValueError('Non-whitelisted paper')
    mapping = {int(k): int(v) for k,v in spec['old_to_source'].items()}
    if set(mapping) != set(old['qs']): raise ValueError('Incomplete old-ID map')
    if len(set(mapping.values())) != len(mapping): raise ValueError('Non-bijective mapping')
    adds = {a['number']: a for a in spec['additions']}
    if len(adds) != len(spec['additions']) or set(adds) & set(mapping.values()):
        raise ValueError('Addition overwrites an existing question')
    expected = set(range(1, spec['expected_questions']+1))
    actual = set(mapping.values()) | set(adds)
    missing = set(spec['missing_original_numbers'])
    if actual & missing or actual | missing != expected:
        raise ValueError('Real question IDs plus explicit missing IDs do not cover reference')
    for a in adds.values():
        if len(a['options']) != 4 or any(not o.strip() for o in a['options']):
            raise ValueError('Incomplete options')
        if a['answer'] not in 'ABCD': raise ValueError('Invalid sourced answer')
        if re.search('未回忆|正在征集|正确答案为A|暂无收集', a['stem']):
            raise ValueError('Source placeholder cannot become an exam question')
    return mapping, adds


def make_candidate(spec, original, source_dir, sources):
    import fitz
    old = split_paper(original)
    mapping, adds = validate_plan(spec, old)
    assigned = {}
    if set(spec['material_members']) != set(old['materials']): raise ValueError('Material plan incomplete')
    for mid, members in spec['material_members'].items():
        for n in members:
            if n not in old['qs'] or n in assigned: raise ValueError('Ambiguous material member')
            assigned[n] = mid
    for n,q in old['qs'].items(): q['material'] = assigned.get(n)
    newqs = {mapping[n]: q.copy() for n,q in old['qs'].items()}
    newans = {mapping[n]: a for n,a in old['answers'].items()}
    images, proofs = {}, []
    for n, a in adds.items():
        p = source_dir/a['answer_pdf']
        with fitz.open(p) as d:
            page = d[a['answer_page']-1]
            box = fitz.Rect(a['answer_crop'])
            if not page.rect.contains(box): raise ValueError('Crop outside source page')
            pix = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=box, alpha=False)
            b = pix.tobytes('png')
        if sha(b) != a['image_sha256']: raise ValueError('Image differs from visually reviewed crop')
        rel = a['image_path']
        if not rel.startswith('图片/') or '..' in Path(rel).parts: raise ValueError('Unsafe image path')
        images[rel] = b
        qtext = a['stem']+'\n\n'+'\n'.join('- **'+ch+'**. '+v for ch,v in zip('ABCD',a['options']))
        ref = os.path.relpath(rel, Path(spec['path']).parent).replace('\\','/')
        body = '**答案**：'+a['answer']+'\n\n**来源参考解析**（不是官方公布答案）\n\n'
        body += '<img src="'+ref+'" alt="第'+str(n)+'题参考解析原件裁图（含公式），来源第'+str(a['answer_page'])+'页" />\n\n'
        body += '[参考解析原件]('+sources[a['answer_pdf']]['url']+')，第'+str(a['answer_page'])+'页。'
        if a.get('note'): body += '\n\n> 校核提示：'+a['note']
        newqs[n] = dict(header='## 第 '+str(n)+' 题　<sub>数字推理 · 据同卷题本补录</sub>', text=qtext, material=None)
        newans[n] = body
        proofs.append(dict(original_number=n, question_source=sources[a['question_pdf']], question_page=a['question_page'],
                           answer_source=sources[a['answer_pdf']], answer_page=a['answer_page'], image_path=rel,
                           crop_pdf_points=a['answer_crop'], image_sha256=sha(b), source_answer=a['answer']))
    for mid in old['materials']:
        group = sorted(mapping[n] for n,q in old['qs'].items() if q['material']==mid)
        if not group or group != list(range(min(group),max(group)+1)): raise ValueError('Material group split by mapping')
    label = '2026-10-11 对照题本重排：现有题干/选项/材料/解析保持原文，答案随旧→原题号映射迁移；新增'+str(len(adds))+'道有据真题；保留实际缺失原题号，不以连续号掩盖缺题。'
    fields = {'题号口径':'对照题本原题号（保留缺号，答案与共用材料联动）', '对照题本题量':spec['expected_questions'],
              '实有题数':len(newqs), '缺失原题号':spec['missing_original_numbers'],
              '整卷核验状态':'仍缺题，见缺失原题号' if spec['missing_original_numbers'] else '题数及题序已对照；非逐字人工验真',
              '题序证据':'reports/PAPER-INTEGRITY-20261011.jsonl', '题序对照来源':sources[spec['reference']]['url']}
    prefix = set_fields(old['prefix'], fields, label)
    prefix = re.sub(r'(>\s*行测\s*·\s*)\d+(\s*题)',lambda m:m.group(1)+str(len(newqs))+m.group(2), prefix,count=1)
    prefix += '\n> 本轮按可核对题本恢复题序。**实有 '+str(len(newqs))+' 题 / 对照题本 '+str(spec['expected_questions'])+' 题**。'
    if spec['missing_original_numbers']: prefix += '原题号 '+ '、'.join(map(str,spec['missing_original_numbers']))+' 仍缺，正文不创建假题或假答案。'
    prefix += '\n> 旧版题号与当前题号映射见 `reports/PAPER-INTEGRITY-20261011.jsonl`；现有选项和解析版本保持原样，不能将另一来源的字母答案机械套入。\n\n'
    pieces = [prefix.rstrip()]; emitted = set()
    for n,q in sorted(newqs.items()):
        mid = q['material']
        if mid and mid not in emitted:
            group = sorted(i for i,v in newqs.items() if v['material']==mid)
            pieces += ['## 材料 '+str(len(emitted)+1)+'（第'+str(min(group))+'—'+str(max(group))+'题共用）',old['materials'][mid]['text']]
            emitted.add(mid)
        h = re.sub(r'^#{2,3} 第 \d+ 题',('###' if mid else '##')+' 第 '+str(n)+' 题',q['header'])
        pieces += [h,q['text']]
    pieces.append('## 答案与解析')
    for n,a in sorted(newans.items()): pieces.append('<details>\n<summary>第 '+str(n)+' 题</summary>\n\n'+a+'\n\n</details>')
    final = '\n\n'.join(pieces).rstrip()+'\n'
    check = split_paper(final)
    if set(check['qs']) != set(newqs): raise AssertionError('Output IDs changed')
    for n,q in old['qs'].items():
        target = check['qs'][mapping[n]]
        assert target['text']==q['text'], ('Question body changed',n)
        assert check['answers'][mapping[n]]==old['answers'][n], ('Answer changed',n)
        before=old['materials'][q['material']]['text'] if q['material'] else None
        after=check['materials'][target['material']]['text'] if target['material'] else None
        assert before==after, ('Shared material detached',n)
    from cloud_quality import image_refs
    old_refs=collections.Counter(image_refs(original));new_refs=collections.Counter(image_refs(final))
    assert not (old_refs-new_refs), 'An existing image reference was lost'
    assert sum((new_refs-old_refs).values())==len(adds)
    rec=dict(path=spec['path'],before_sha256=sha(original.encode()),after_sha256=sha(final.encode()),
             old_count=len(old['qs']),current_count=len(newqs),reference_question_count=spec['expected_questions'],
             missing_original_numbers=spec['missing_original_numbers'], old_to_source=spec['old_to_source'],
             unchanged_existing_question_bodies=len(old['qs']),unchanged_existing_answer_bodies=len(old['answers']),
             unchanged_material_groups=len(old['materials']),visual_matches=spec['visual_matches'],material_members_old_ids=spec['material_members'],
             reference_source=sources[spec['reference']], additions=proofs,notes=spec['notes'],boundary=spec['boundary'])
    return final,images,rec


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=ROOT)
    ap.add_argument('--plan',type=Path,required=True)
    ap.add_argument('--sources',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args();root=args.root.resolve()
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if {s['path'] for s in plan['papers']} != ALLOWED: raise ValueError('Unexpected plan scope')
    for name,s in plan['sources'].items():
        p=(args.sources/name).resolve()
        if not p.is_relative_to(args.sources.resolve()) or sha(p.read_bytes())!=s['sha256']:
            raise ValueError('Source hash mismatch: '+name)
    candidates,images,records={}, {}, []
    for spec in plan['papers']:
        p=root/spec['path'];raw=p.read_bytes()
        if sha(raw)!=spec['before_sha256']: raise RuntimeError('Concurrent or changed base: '+spec['path'])
        text,imgs,record=make_candidate(spec,raw.decode('utf-8'),args.sources,plan['sources'])
        candidates[spec['path']]=text;images.update(imgs);records.append(record)
    for path,b in images.items():
        p=root/path
        if p.exists() and p.read_bytes()!=b:raise RuntimeError('Refusing image overwrite')
    if args.apply:
        for spec in plan['papers']:
            if sha((root/spec['path']).read_bytes())!=spec['before_sha256']:raise RuntimeError('Concurrent edit')
        for path,b in images.items():
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        for path,text in candidates.items():(root/path).write_text(text,encoding='utf-8',newline='\n')
        report=root/'reports';report.mkdir(exist_ok=True)
        (report/'PAPER-INTEGRITY-20261011.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in records),encoding='utf-8')
        summary=['# 原卷题序、漏题与解析图修复（2026-10-11）','','只修四份已有行测试卷；PDF不入库。所有旧题干、选项、材料和解析逐块保留，答案按映射迁移。','','| 文件 | 原实有题数 | 现实有题数 | 对照题本题数 | 仍缺原题号 | 新增来源解析图 |','|---|---:|---:|---:|---|---:|']
        for r in records:summary.append('| '+r['path']+' | '+str(r['old_count'])+' | '+str(r['current_count'])+' | '+str(r['reference_question_count'])+' | '+('、'.join(map(str,r['missing_original_numbers'])) or '无')+' | '+str(len(r['additions']))+' |')
        summary+=['','## 核验边界','','新增9道题及9张逐题解析原件裁图，不是9张旧题缺失题图。既有图形题已按原题本逐图比对编号，原有图片字节不改。',
                  '广东69—75、浙江49—50的所获题本也缺失，缺号明确保留；不把来源占位“正确答案为A”当答案。',
                  '国考2022已将旧第135题放回第4题，并恢复言语文章、其他题目与共用材料对应次序。另一标副省级候选含不同资料分析题，已排除，未污染正式正文。',
                  '题本为第三方/考生回忆资料，恢复的是可证实对应关系；未声称所有选项与官方印刷原卷完全相同。现有题干及解析的其他源内缺陷不因本专项自动通过。',
                  '浙江42题来源解析有9÷9.6＝5/6笔误，已保留来源图并单独标注应以题面末项8核算，未静默修改原图。',
                  '逐题映射、源URL/哈希、PDF页码、裁图坐标、修改前后SHA见同目录JSONL。']
        (report/'PAPER-INTEGRITY-20261011.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    print(json.dumps({'applied':args.apply,'papers':len(records),'new_questions':sum(len(r['additions']) for r in records),
                      'new_source_answer_images':len(images),'preserved_old_question_bodies':sum(r['old_count'] for r in records),
                      'still_missing_original_ids':{r['path']:r['missing_original_numbers'] for r in records if r['missing_original_numbers']}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
