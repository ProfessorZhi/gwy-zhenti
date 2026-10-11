#!/usr/bin/env python3
"""Repository-native exact-source tail repair and reproducible quality inventory.

--check is read-only. --build writes guides/catalog/reports. --repair-source
uses a pinned data-only snapshot, never generates exam text or executes a source.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import quote, unquote, urlsplit

SOURCE_REPO = 'zzcc-nb/gongkao-tiku'
SOURCE_COMMIT = 'ef3c7def82544fb8fe8a4913bebc6024910a6dc0'
PRIORITY = ('浙江','江苏','上海','北京','天津','广东','广州','深圳','福建')
DATE = '2026-10-11'
FM = re.compile(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', re.S)
QBLOCK = re.compile(r'^## 第 (\d+) 题[^\n]*\n(.*?)(?=^## |\Z)', re.M | re.S)
MAT = re.compile(r'^### 给定材料[^\S\n]*\n(.*?)\n### 作答要求[^\S\n]*\n(.*)', re.M | re.S)
HEAD_Q = re.compile(r'^#{2,3}\s+第\s*(\d+)\s*题', re.M)
DETAIL = re.compile(r'<details>\s*<summary>\s*第\s*(\d+)\s*题\s*</summary>(.*?)</details>', re.S)
NO_EXAM = re.compile(r'模考|模拟|大赛|预测|训练|押题|原创')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def meta(text: str) -> dict:
    m = FM.match(text)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        v = v.strip()
        try:
            value = json.loads(v)
        except (ValueError, TypeError):
            value = v.strip('"\'')
        out[k.strip()] = value
    return out


def normalized(text: str) -> str:
    # Matching only; never normalize source characters in the delivered text.
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if not c.isspace())


def normalized_offsets(text: str) -> tuple[str, list[int]]:
    chars, offsets = [], []
    for i, c in enumerate(text):
        for n in unicodedata.normalize('NFKC', c):
            if not n.isspace():
                chars.append(n)
                offsets.append(i + 1)
    return ''.join(chars), offsets


def suffix_after_prefix(old: str, full: str) -> str | None:
    a = normalized(old)
    b, offsets = normalized_offsets(full)
    if not a or not b.startswith(a) or len(b) <= len(a):
        return None
    if len(a) < len(offsets) and offsets[len(a)-1] == offsets[len(a)]:
        return None
    return full[offsets[len(a)-1]:]


def papers(root: Path) -> list[Path]:
    return sorted(p for top in ('国考','省考') for p in (root/top).rglob('*.md')
                  if p.name.startswith(('行测-','申论-')) and not p.is_symlink())


def read_source(source: Path) -> dict[str, list[dict]]:
    info = json.loads((source/'_source.json').read_text(encoding='utf-8'))
    if info.get('repository') != SOURCE_REPO or info.get('commit') != SOURCE_COMMIT:
        raise ValueError('Source is not the reviewed pinned snapshot')
    pool = collections.defaultdict(list)
    for f in sorted((source/'申论题库').glob('*/*.md')):
        if f.is_symlink():
            continue
        raw = f.read_bytes()
        text = raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
        title = re.search(r'\*\*来源\*\*[：:]\s*([^\n]+)', text)
        if not title or NO_EXAM.search(title.group(1)):
            continue
        title = title.group(1).strip()
        year = re.search(r'20\d{2}', title)
        if not year or not 2016 <= int(year.group()) <= 2026:
            continue
        prompt = re.search(r'^## .*?题目\s*\n(.*?)(?=^## |\Z)',text,re.M|re.S)
        material = re.search(r'^## .*?给定材料\s*\n(.*?)(?=^## |\Z)',text,re.M|re.S)
        qid = re.search(r'\*\*编号\*\*[：:]\s*(\d+)',text)
        if not prompt or not material:
            continue
        material = material.group(1).strip()
        pool[normalized(prompt.group(1))].append({
            'title':title, 'material':material, 'normalized':normalized(material),
            'path':f.relative_to(source).as_posix(), 'sha256':sha(raw),
            'question_id':qid.group(1) if qid else None})
    return pool


def plan_repair(text: str, candidates: dict[str,list[dict]]) -> tuple[str,list[dict]]:
    fm = meta(text)
    pending = int(fm.get('现仍截断题数',0))
    if pending <= 0 or fm.get('科目') != '申论':
        return text, []
    year, area = str(fm.get('年份','')), str(fm.get('地区',''))
    insertions, proof = [], []
    for block in QBLOCK.finditer(text):
        material = MAT.search(block.group(2))
        if not material:
            continue
        old = material.group(1).rstrip()
        if len(old.strip()) < 5000:
            continue
        prompt = re.sub(r'-+$','',normalized(material.group(2).strip()))
        viable = []
        for c in candidates.get(prompt,[]):
            if year not in c['title'] or area not in c['title']:
                continue
            tail = suffix_after_prefix(old.strip(),c['material'])
            if tail is None or not normalized(tail):
                continue
            if re.search(r'<img\b|!\[|^\s*#{1,6}\s|^\s*(?:[ABＣABC]卷|作答要求|题目及要求|问题及要求)\s*[:：]?\s*$', tail, re.M|re.I):
                continue
            if c['material'].rstrip()[-1:] not in '。！？.!?”"』」）)…' and not re.search(r'——摘自[^\n]*(?:\n[^\n]*){0,2}(?:讲话|报告|文章)\s*$', c['material']):
                continue
            viable.append((c,tail))
        # Duplicates are not independent corroboration; conflicting versions halt.
        variants = {v[0]['normalized'] for v in viable}
        if len(variants) != 1:
            continue
        c, tail = viable[0]
        start = block.start(2) + material.start(1)
        at = start + len(material.group(1).rstrip())
        assert normalized(old.strip()+tail) == c['normalized']
        insertions.append((at,tail))
        proof.append({'question':int(block.group(1)), 'source_title':c['title'],
                      'source_url':f'https://github.com/{SOURCE_REPO}/blob/{SOURCE_COMMIT}/'+quote(c['path'],safe='/'),
                      'source_path':c['path'], 'source_file_sha256':c['sha256'],
                      'source_question_id':c['question_id'],
                      'matched_prefix_chars':len(normalized(old)),
                      'suffix_chars':len(tail),'suffix_sha256':sha(tail.encode('utf-8')),
                      'full_source_material_sha256':sha(c['material'].encode('utf-8'))})
    if not proof:
        return text, []
    if len(proof) > pending:
        raise ValueError('Matched more tails than the declared defect count')
    rebuilt = text
    for at,tail in sorted(insertions,reverse=True):
        rebuilt = rebuilt[:at]+tail+rebuilt[at:]
    fm_end = FM.match(rebuilt)
    assert fm_end is not None
    head = fm_end.group(0)
    head,n = re.subn(r'(?m)^现仍截断题数:\s*\d+\s*$', '现仍截断题数: '+str(pending-len(proof)),head,count=1)
    if n != 1:
        raise ValueError('Expected one current-state field')
    annotation = f'；{DATE} 按同题同年同地区 GitHub 固定源补回 {len(proof)} 处材料尾部；原材料归一化后完整前缀逐字相等；只消除该截断项，不代表整卷验收'
    head,n = re.subn(r'(?m)^(校验状态:\s*")(.*)("\s*)$',
                    lambda m:m.group(1)+m.group(2)+annotation+m.group(3),head,count=1)
    if n != 1:
        raise ValueError('Unexpected validation-state encoding')
    extra = '补全来源: '+json.dumps(SOURCE_REPO+'@'+SOURCE_COMMIT,ensure_ascii=False)+'\n'
    extra += '补全证据: "reports/REPAIRS-20261011.jsonl"\n'
    head = re.sub(r'\n---\n$', '\n'+extra+'---\n',head,count=1)
    rebuilt = head + rebuilt[fm_end.end():]
    old_requirements = [m.group(2) for b in QBLOCK.finditer(text) if (m:=MAT.search(b.group(2)))]
    new_requirements = [m.group(2) for b in QBLOCK.finditer(rebuilt) if (m:=MAT.search(b.group(2)))]
    assert old_requirements == new_requirements
    assert DETAIL.findall(text) == DETAIL.findall(rebuilt)
    assert HEAD_Q.findall(text) == HEAD_Q.findall(rebuilt)
    return rebuilt, proof


def repair(root: Path, source: Path) -> list[dict]:
    pool = read_source(source)
    changes, records = [], []
    for p in papers(root):
        raw = p.read_bytes()
        text = raw.decode('utf-8-sig')
        fixed, proof = plan_repair(text,pool)
        if not proof:
            continue
        new = fixed.encode('utf-8')
        records.append({'path':p.relative_to(root).as_posix(), 'before_sha256':sha(raw),
                        'after_sha256':sha(new),'restored_material_instances':len(proof),
                        'appended_chars':sum(x['suffix_chars'] for x in proof),
                        'evidence':proof, 'scope':'existing recorded tail defects only'})
        changes.append((p,new,sha(raw)))
    for p,new,before in changes:
        if sha(p.read_bytes()) != before:
            raise RuntimeError('Concurrent change: '+str(p))
    for p,new,before in changes:
        p.write_bytes(new)
    if records:
        out=root/'reports';out.mkdir(exist_ok=True)
        (out/'REPAIRS-20261011.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in records),encoding='utf-8')
    return records


def image_refs(text: str) -> list[str]:
    out = re.findall(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']',text,re.I)
    out += [a or b for a,b in re.findall(r'!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))',text)]
    return [html.unescape(s) for s in out]


def resolve_image(rel: str, ref: str) -> str | None:
    u = urlsplit(ref)
    if u.scheme or u.netloc:
        return None
    p = unquote(u.path)
    if p.startswith('/'):
        return '!absolute:'+p
    clean = os.path.normpath(str(Path(rel).parent/p)).replace('\\','/')
    return '!outside:'+clean if clean.startswith('../') else clean


def tracked_paths(root: Path) -> set[str]:
    try:
        return {s for s in subprocess.check_output(['git','ls-files','-z'],cwd=root,stderr=subprocess.DEVNULL).decode('utf-8').split('\0') if s}
    except (subprocess.CalledProcessError,FileNotFoundError):
        snapshot=root/'_tracked-paths.json'
        if not snapshot.exists():
            raise RuntimeError('A tracked repository or exported tree is required')
        return set(json.loads(snapshot.read_text(encoding='utf-8')))


def scan(root: Path, verify_images: bool=False) -> tuple[list[dict],dict]:
    tracked=tracked_paths(root)
    rows=[];refs_all=[];hard=[];by_area=collections.defaultdict(collections.Counter)
    for p in papers(root):
        raw=p.read_bytes();t=raw.decode('utf-8-sig');fm=meta(t);rel=p.relative_to(root).as_posix()
        area='国考' if rel.startswith('国考/') else str(fm.get('地区',p.parent.parent.name))
        if fm.get('考试系列')=='广州市考' or p.name.startswith(('行测-广州市考','申论-广州市考')):
            area='广州'
        subject=str(fm.get('科目',''))
        qids=list(map(int,HEAD_Q.findall(t)))
        declared=re.search(r'>\s*(?:行测|申论)\s*·\s*(\d+)\s*题',t)
        count=int(declared.group(1)) if declared else len(qids)
        details=DETAIL.findall(t)
        usable=[int(n) for n,body in details if (re.search(r'\*\*答案\*\*[：:]\s*(?:[A-G]+|正确|错误)', body) or len(re.sub(r'<[^>]*>','',body).strip())>40) and not re.fullmatch(r'\s*(?:答案缺失|待核实|暂无答案)[。\s]*',body)]
        has_answer=bool(usable) or bool(re.search(r'^##\s*(?:参考答案|答案与解析)\s*\n[\s\S]{100,}',t,re.M))
        now=fm.get('现仍截断题数')
        if now is None:
            m=re.search(r'材料截断\s*(\d+)\s*题',str(fm.get('校验状态','')))
            now=int(m.group(1)) if m else None
        else:now=int(now)
        old=fm.get('上游截断题数');old=int(old) if old is not None else None
        issues=[];notes=[];image_missing=[]
        for ref in image_refs(t):
            resolved=resolve_image(rel,ref)
            if resolved is None:issues.append('外链图片需核验');continue
            refs_all.append(resolved)
            if resolved not in tracked:image_missing.append(resolved)
        if image_missing:hard.extend({'path':rel,'missing':x} for x in image_missing);issues.append('图片文件缺失')
        if len(set(qids))!=len(qids):issues.append('题号重复')
        if qids and qids!=list(range(1,len(qids)+1)):issues.append('题号非连续（需核原卷）')
        if now is not None and now>0:issues.append('材料尾部截断')
        if count and usable and len(usable)!=count:issues.append('答案数量与题量不一致')
        if not has_answer:issues.append('未检测到参考答案（需复核正文）')
        if not qids:notes.append('题号未结构化；不据此认定题面残缺')
        state=str(fm.get('校验状态',''))
        if '★来源无图片' in state:issues.append('来源声明题图或共用材料缺失')
        if '回忆版不全' in state:issues.append('来源声明回忆版不全')
        if '解析区公式碎片未重建' in state:issues.append('解析公式尚待核验')
        if fm.get('卷型')=='统考':notes.append('内部未归属卷型标签，不自动视为独立原卷')
        notes.append('有参考答案不代表其为官方答案或已经验真')
        row={'path':rel,'sha256':sha(raw),'bytes':len(raw),'area':area,'year':str(fm.get('年份',p.parent.name)),
             'subject':subject,'paper_type':str(fm.get('卷型','未标注')),'declared_questions':count,
             'question_anchors':len(qids),'answer_blocks':len(usable),'has_answer_content':has_answer,
             'historical_truncated_questions':old,'current_truncated_questions':now,
             'image_references':len(image_refs(t)),'issues':sorted(set(issues)),'notes':notes,
             'source_validation':state,'whole_paper_acceptance':'not_certified_by_this_audit'}
        rows.append(row)
        by_area[area]['files']+=1;by_area[area][subject]+=1
        if now and now>0:by_area[area]['truncated_files']+=1;by_area[area]['truncated_questions']+=now
    unique=sorted(set(refs_all));decode_errors=[]
    if verify_images:
        from PIL import Image
        for rel in unique:
            try:
                with Image.open(root/rel) as im:im.verify()
            except Exception as exc:decode_errors.append({'path':rel,'error':type(exc).__name__+': '+str(exc)[:120]})
        hard.extend(decode_errors)
    forbidden=sorted(p for p in tracked if Path(p).suffix.lower() in {'.pdf','.zip','.rar','.7z','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.tar','.gz'})
    placeholder_index=root/'资料缺失/INDEX.jsonl'
    placeholders=[json.loads(s) for s in placeholder_index.read_text(encoding='utf-8-sig').splitlines() if s.strip()] if placeholder_index.exists() else []
    digest=sha(''.join(r['path']+'\0'+r['sha256']+'\n' for r in rows).encode('utf-8'))
    stats={'schema_version':1,'inventory_sha256':digest,'paper_files':len(rows),
           'subjects':dict(collections.Counter(r['subject'] for r in rows)),
           'areas':{k:dict(v) for k,v in sorted(by_area.items())},
           'image_references':len(refs_all),'unique_referenced_images':len(unique),
           'missing_image_references':len([x for x in hard if 'missing' in x]),
           'image_decode_check_performed':verify_images,'image_decode_errors':decode_errors,
           'forbidden_tracked_files':forbidden,'hard_integrity_errors':hard,
           'placeholder_files':len(placeholders),'placeholder_states':dict(collections.Counter(x['state'] for x in placeholders)),
           'historical_truncated_files':sum(bool(r['historical_truncated_questions']) for r in rows),
           'historical_truncated_questions':sum(r['historical_truncated_questions'] or 0 for r in rows),
           'current_truncated_files':sum(bool(r['current_truncated_questions']) for r in rows),
           'current_truncated_questions':sum(r['current_truncated_questions'] or 0 for r in rows),
           'files_with_machine_flags':sum(bool(r['issues']) for r in rows),
           'whole_paper_acceptance':'not_established_by_structural_checks'}
    return rows,stats


def md_link(label: str, path: str, up: str='') -> str:
    return '['+label.replace('|','／')+']('+up+quote(path,safe='/')+')'


def build(root: Path, rows: list[dict], stats: dict) -> None:
    for d in ('catalog','reports'):(root/d).mkdir(exist_ok=True)
    (root/'catalog/manifest.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8')
    (root/'reports/QUALITY-SUMMARY.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    defects=[{k:r[k] for k in ('path','area','year','subject','paper_type','current_truncated_questions','issues','notes')} for r in rows if r['issues']]
    (root/'reports/DEFECTS.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in defects),encoding='utf-8')
    cover=['# 九个重点地区覆盖表（按当前正文状态生成）','',
           '由 `tools/cloud_quality.py --build` 读取已收录文件生成。以 `现仍截断题数` 为准，不再把历史截断当作现行缺陷。',
           '没有题号锚点仅表示格式尚未结构化；没有发现机器告警不等于原卷内容已全部验真。',
           '“未收录”只描述本库；同年另一科目或邻年存在，不能单独证明该卷当年必然开考。',
           '广州按独立考试系列列出，广东行不重复计算广州。2019年起不展开独立广州市考缺卷矩阵。','']
    missing=[]
    for area in PRIORITY:
        cover+=['## '+area,'','| 年份 | 行测 | 申论 |','|---|---|---|']
        for year in range(2016,2027):
            if area=='广州' and year>=2019:continue
            cols=[]
            for sub in ('行测','申论'):
                selected=[r for r in rows if (r['area'],r['year'],r['subject'])==(area,str(year),sub)]
                if not selected:
                    cols.append('未收录；开考及具体卷型待证')
                    missing.append({'area':area,'year':year,'subject':sub,'state':'not_collected_exam_identity_pending'})
                else:
                    cells=[]
                    for r in selected:
                        desc=md_link(r['paper_type'],r['path'])
                        if r['current_truncated_questions']:desc+=' · 材料截断 '+str(r['current_truncated_questions'])+' 题'
                        other=[x for x in r['issues'] if x!='材料尾部截断']
                        if other:desc+=' · '+'；'.join(other)
                        if not r['issues']:desc+=' · 未检出本轮规则缺陷（非整卷验收）'
                        cells.append(desc)
                    cols.append('<br>'.join(cells))
            cover.append('| '+str(year)+' | '+' | '.join(cols)+' |')
        cover.append('')
    cover+=['## 解释边界','','本表枚举已收录的卷型；缺失的 A/B/C 等细分卷型必须依开考公告或原卷证据另行核实。',
            '“统考”保留为历史内部桶，不自动合并、拆分或计作已确认独立原卷。',
            '题面、材料、图片、答案、卷型身份分别验收，不再使用一个未经定义的“完整率”。','']
    (root/'COVERAGE-优先区.md').write_text('\n'.join(cover),encoding='utf-8')
    (root/'reports/PRIORITY-MISSING.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    defect_md=['# 当前内容与质量待办','',
               '这是当前规则检出的事项，不是全库缺陷全集。保留来源限定，不把未检测到等同于不存在。',
               f"正文文件 {len(rows)} 份；有规则告警 {len(defects)} 份；当前仍有尾部截断 {stats['current_truncated_files']} 份 / {stats['current_truncated_questions']} 道受影响题。",'',
               '| 试卷 | 当前事项 |','|---|---|']
    for r in defects:defect_md.append('| '+md_link(r['path'],r['path'],'../')+' | '+'；'.join(r['issues'])+' |')
    defect_md+=['','## 仍需原卷证据的部分','','来源标记为未截断并不能证明中间没有漏材料；本轮未逐字验全卷。',
                '未收录地区/年度科目详见 [重点区未收录清单](PRIORITY-MISSING.json)。其他地区不开展新卷搜索。',
                '有答案内容不代表它是政府发布的官方答案；缺少可靠来源的仍需核实。','']
    (root/'reports/QUALITY-AUDIT.md').write_text('\n'.join(defect_md),encoding='utf-8')
    progress=['# 真题库总进度','',f'更新批次：{DATE}。机器清单指纹：`{stats["inventory_sha256"]}`。','',
              '**图文库已交付；内容质量分项维护，不宣称全国所有原卷已经完整。**','',
              '| 指标 | 当前数量 |','|---|---:|',f'| 已收录 MD | {len(rows)} |',
              f'| 行测 / 申论 | {stats["subjects"].get("行测",0)} / {stats["subjects"].get("申论",0)} |',
              f'| 独立引用图片 | {stats["unique_referenced_images"]} |',
              f'| 图片引用次数 | {stats["image_references"]} |',
              f'| 缺失 / 待核实占位 | {stats["placeholder_files"]} |',
              f'| 历史已标记材料截断 | {stats["historical_truncated_files"]} 份 / {stats["historical_truncated_questions"]} 道受影响题 |',
              f'| 当前仍有该截断项 | {stats["current_truncated_files"]} 份 / {stats["current_truncated_questions"]} 道受影响题 |',
              f'| 重点区年度科目未收录 | {len(missing)} 格（不等于全部卷型缺口） |','',
              '## 当前入口','',
              '- [重点地区逐年图文试卷](COVERAGE-优先区.md)',
              '- [当前质量事项](reports/QUALITY-AUDIT.md)',
              '- [逐卷机器清单及 SHA-256](catalog/manifest.jsonl)',
              '- [质量汇总数据](reports/QUALITY-SUMMARY.json)',
              '- [逐题补全来源与前后 SHA](reports/REPAIRS-20261011.jsonl)',
              '- [非重点地区资料缺失](资料缺失/README.md)','',
              '## 本轮具体边界','',
              '仅对已标记尾部截断的既有材料，使用固定版本的同题来源逐题校对，补入原文尾部。题干、作答要求、答案、原题号和图片未由补全程序改写。',
              '接回尾部不等于整卷原文已逐字验真，亦不等于已补全所有缺卷、缺答案或中间漏段。',
              '来源候选中的模考、训练和题干/材料不能精确对齐的项不会自动入库。未收录状态继续保留；非重点地区不主动找新卷。',
              '上海2017行测此前已恢复136题、38张题干/材料图片及6组共用材料，仍以卷内声明为质量边界。',
              '原始 PDF/ZIP 不随仓库交付；MD和实际引用的图片一起维护。仓库保持私有。','',
              '## 复现','',
              '```bash','python tools/cloud_quality.py --build --verify-images',
              'python tools/cloud_quality.py --check --verify-images','```','',
              '`catalog/manifest.jsonl` 是 GitHub 可直接读取的版本化清单；Windows `work/manifest.jsonl` 是工作台副本，拉取新提交后须由本地管线刷新。','']
    (root/'PROGRESS.md').write_text('\n'.join(progress),encoding='utf-8')
    readme=root/'README.md'
    if readme.exists():
        t=readme.read_text(encoding='utf-8')
        banner='<!-- CURRENT-STATUS -->\n> 当前数据以 [总进度](PROGRESS.md)、[逐卷清单](catalog/manifest.jsonl) 和 [质量事项](reports/QUALITY-AUDIT.md) 为准。下方历史阶段叙述不作为现行完整率。\n<!-- /CURRENT-STATUS -->\n'
        if '<!-- CURRENT-STATUS -->' in t:t=re.sub(r'<!-- CURRENT-STATUS -->.*?<!-- /CURRENT-STATUS -->\n?',banner,t,flags=re.S)
        else:t=t.replace('\n','\n\n'+banner,1)
        t=t.replace('逐卷见 `work/manifest.jsonl`','逐卷见 `catalog/manifest.jsonl`')
        t=t.replace('详见下方「交付与同步」','当前核验见 [质量汇总](reports/QUALITY-SUMMARY.json)')
        readme.write_text(t,encoding='utf-8')
    quality=root/'QUALITY.md'
    if quality.exists():
        t=quality.read_text(encoding='utf-8')
        h='\n## GitHub 当前质量清单（'+DATE+'）\n\n'
        h+='当前截断数量读取 `现仍截断题数`；没有锚点仅列格式提醒，不推断题面缺失。\n'
        h+=f"最新重新生成：历史 {stats['historical_truncated_files']} 份 / {stats['historical_truncated_questions']} 道受影响题；现仍 {stats['current_truncated_files']} 份 / {stats['current_truncated_questions']} 道受影响题。\n"
        h+='以前的阶段数字和规则记录是历史，不覆盖当前字段。机器检查通过不等于逐字、逐图、逐答案验真。\n'
        h+='当前证据：[逐卷清单](catalog/manifest.jsonl)、[告警](reports/QUALITY-AUDIT.md)、[本轮逐题补全证据](reports/REPAIRS-20261011.jsonl)。\n'
        t=re.sub(r'\n## GitHub 当前质量清单[\s\S]*\Z','',t)
        quality.write_text(t.rstrip()+'\n'+h,encoding='utf-8')


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repair-source',type=Path)
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--verify-images',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    repairs=repair(root,args.repair_source) if args.repair_source else []
    rows,stats=scan(root,args.verify_images)
    if args.build:build(root,rows,stats)
    if args.check:
        manifest=root/'catalog/manifest.jsonl'
        if not manifest.exists():raise RuntimeError('Versioned inventory is missing')
        saved=[json.loads(s) for s in manifest.read_text(encoding='utf-8').splitlines() if s]
        if saved != rows:raise RuntimeError('Inventory stale or content changed; run --build and review')
    print(json.dumps({'papers':len(rows),'images':stats['unique_referenced_images'],
                      'image_refs':stats['image_references'],'truncated_files':stats['current_truncated_files'],
                      'truncated_questions':stats['current_truncated_questions'],
                      'restored_files_this_run':len(repairs),
                      'restored_material_instances_this_run':sum(x['restored_material_instances'] for x in repairs),
                      'appended_characters_this_run':sum(x['appended_chars'] for x in repairs),
                      'machine_flagged_files':stats['files_with_machine_flags'],
                      'hard_errors':len(stats['hard_integrity_errors']),
                      'forbidden_files':len(stats['forbidden_tracked_files'])},ensure_ascii=False,indent=2))
    return int(bool(stats['hard_integrity_errors'] or stats['forbidden_tracked_files']))

if __name__=='__main__':
    sys.exit(main())
