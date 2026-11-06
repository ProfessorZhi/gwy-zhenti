"""Validate explicitly reviewed A1 mappings without changing automatic alignment."""

import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def full_norm(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)|<[^>]+>', '', html.unescape(text))
    return re.sub(r'[\W_]+', '', text)


def stem(block, api):
    body = block.split('\n', 1)[1].split('<details', 1)[0]
    option = api.OPTION_LINE.search(body)
    return full_norm(body[:option.start()] if option else body)


def validate(plan_path, paper, path, cache, text, meta, report, api, option_q=None):
    """Fail closed on stale inputs, incomplete sources or unsupported mappings."""
    raw = plan_path.read_bytes()
    review = json.loads(raw)
    if review.get('schema_version') != 1 or review.get('paper') != paper:
        raise ValueError('人工复核计划版本或试卷路径不匹配')
    mode = 'A2' if option_q is not None else 'A1'
    if review.get('mode', 'A1') != mode:
        raise ValueError('人工复核计划模式与入口不匹配')
    for key, data in [('paper_sha256', path.read_bytes()),
                      ('cache_sha256', (cache / 'paper.json').read_bytes())]:
        if review.get(key) != digest(data):
            raise ValueError(f'人工复核计划已过期：{key}')
    if not review.get('reviewer') or not review.get('reviewed_at'):
        raise ValueError('人工复核计划缺少复核人或时间')
    archive = Path(meta.get('sourceArchive', ''))
    if not archive.is_file() or review.get('source_manifest_sha256') != digest(archive.read_bytes()):
        raise ValueError('原始来源清单哈希不匹配')
    manifest = json.loads(archive.read_bytes())
    source_html = archive.parent / 'content.html'
    expected = review.get('source_html_sha256')
    if (not source_html.is_file() or digest(source_html.read_bytes()) != expected
            or expected != manifest.get('contentSha256') or expected != meta.get('sourceHtmlSha256')
            or manifest.get('url') != meta.get('url') or manifest.get('questionCount') != len(meta['questions'])):
        raise ValueError('原始来源快照或来源身份不匹配')
    if not str(meta.get('paperId', '')).isdigit():
        raise ValueError('华图来源编号无效')
    catalog = Path(review.get('source_catalog', ''))
    if not catalog.is_file() or digest(catalog.read_bytes()) != review.get('source_catalog_sha256'):
        raise ValueError('来源目录证据哈希不匹配')
    entries = json.loads(catalog.read_bytes()).get('list', [])
    entries = [entry for entry in entries if entry.get('title') == meta.get('title')
               and f"共{len(meta['questions'])}题" in entry.get('description', '')]
    identity = {'paperId': str(meta['paperId']), 'catalog_locator': 'paperId', 'catalog_id': str(meta['paperId'])}
    if not any(f"#paperid#:#{meta['paperId']}#" in entry.get('options', '') for entry in entries):
        answer = re.fullmatch(r'/tiku/analysis/(\d+)/?', urlsplit(meta.get('url', '')).path)
        if not answer or not any(f'#answerid#:#{answer.group(1)}#' in entry.get('options', '') for entry in entries):
            raise ValueError('来源目录的来源 ID、标题或题量不匹配')
        identity = {'paperId': str(meta['paperId']), 'paperId_basis': '缓存记录',
                    'catalog_locator': 'answerid', 'catalog_id': answer.group(1)}
    blocks = {n: text[a:b] for n, a, b in api.split_questions(text)}
    if len(blocks) != len(api.split_questions(text)):
        raise ValueError('试卷题号重复')
    present = {n: stem(b, api) for n, b in blocks.items() if api.STUB not in b}
    questions = meta['questions']
    source_stems = [full_norm(q.get('stem_html', '')) for q in questions]
    items = review.get('items', [])
    if not items:
        raise ValueError('人工复核计划为空')
    if option_q is not None and (len(items) != 1 or items[0].get('q') != option_q):
        raise ValueError('A2 人工复核计划必须仅包含指定的选项缺口题')
    mappings, fills = {}, []
    for item in items:
        q, h = item['q'], item['huatu']
        if (type(q) is not int or type(h) is not int or q in mappings or h - 1 in mappings.values()
                or q not in blocks or api.STUB not in blocks[q] or not 1 <= h <= len(questions)):
            raise ValueError('人工复核目标不存在、重复或已经有题')
        source = questions[h - 1]
        if not source_stems[h - 1]:
            raise ValueError(f'华图第 {h} 题缺少可比文字题干，当前人工复核模式不接受纯图片题')
        options = source.get('options', [])
        fragments = [source.get('stem_html', ''), source.get('analysis_html', '')] + [o.get('html', '') for o in options]
        if ([o.get('label') for o in options] != list('ABCD')
                or source.get('answer', '').strip() not in list('ABCD')
                or any(not full_norm(f) and '<img' not in f.lower() for f in fragments)
                or any(re.search(r'暂未收录|占位题|题目暂缺|题目正在.*征集|来源未提供|暂无解析|暂无答案|^(?:缺|缺失|暂缺)$', full_norm(f)) for f in fragments)):
            raise ValueError(f'华图第 {h} 题题干、四选项、答案或解析不完整')
        if any(api.similar(source_stems[h - 1], source_stems[other]) >= api.MIN_MATCH for other in mappings.values()):
            raise ValueError(f'华图第 {h} 题与本计划另一补题题干重复')
        # Scan every existing question, including reordered matches excluded by LIS.
        if any(api.similar(st, source_stems[h - 1]) >= api.MIN_MATCH for st in present.values()):
            raise ValueError(f'华图第 {h} 题可能已存在于本卷')
        anchors = item.get('anchors', [])
        pairs = [(a['q'], a['huatu']) for a in anchors]
        if len({n for n, _ in pairs}) != len(pairs) or len({s for _, s in pairs}) != len(pairs):
            raise ValueError('人工复核锚点重复')
        scores = []
        for anchor, (n, s) in zip(anchors, pairs):
            if n not in present or not 1 <= s <= len(questions) or s == h:
                raise ValueError('人工复核锚点无效')
            score = api.similar(present[n], source_stems[s - 1])
            if score < api.MIN_MATCH:
                passages = [full_norm(p) for p in anchor.get('shared_passages', [])]
                if (len(passages) < 2 or len(set(passages)) != len(passages) or sum(map(len, passages)) < 60
                        or any(len(p) < 10 or p not in present[n] or p not in source_stems[s - 1] for p in passages)
                        or sum(all(p in st for p in passages) for st in present.values()) != 1
                        or sum(all(p in st for p in passages) for st in source_stems) != 1
                        or not anchor.get('rationale')):
                    raise ValueError(f'人工复核锚点 {n}→{s} 题干不匹配')
            scores.append({'q': n, 'huatu': s, 'stem_similarity': round(score, 4)})
        method = item.get('method')
        if method == 'neighbors':
            nearest = sorted(n for n in present if n < q)[-2:] + sorted(n for n in present if n > q)[:2]
            if any(n not in nearest for n, _ in pairs):
                raise ValueError('邻题证据必须使用前后最近各两道已有题')
            supports = [(n, s) for n, s in pairs if s - n == h - q]
            if len(supports) < 3 or not any(n < q for n, _ in supports) or not any(n > q for n, _ in supports):
                raise ValueError('人工复核邻题未达到双侧三票支持')
        elif method in ('elimination', 'material_group'):
            local_range, source_range = item['local_range'], item['source_range']
            local_set = set(range(local_range[0], local_range[1] + 1))
            source_set = set(range(source_range[0], source_range[1] + 1))
            if (len(pairs) < 4 or q not in local_set or h not in source_set
                    or local_set - {q} != {n for n, _ in pairs}
                    or source_set - {h} != {s for _, s in pairs}):
                raise ValueError('整组排除法必须逐题覆盖除唯一缺题外的全部题目')
            if method == 'material_group':
                heading = f"## 材料 {item['local_material']}"
                material = re.search(r'^' + re.escape(heading) + r'\n(.*?)(?=^#{2,3} |\Z)', text, re.M | re.S)
                group = re.search(r'^' + re.escape(heading) + r'\n(.*?)(?=^## |\Z)', text, re.M | re.S)
                source_material = next((m for m in meta.get('materials', []) if m['id'] == item['source_material']), None)
                if (not material or not source_material
                        or sum(m['id'] == item['source_material'] for m in meta.get('materials', [])) != 1
                        or not group or {n for n, _, _ in api.split_questions(group.group(1))} != local_set
                        or api.similar(full_norm(material.group(1)), full_norm(source_material['html'])) < 0.95
                        or {s for s, question in enumerate(questions, 1) if question.get('material_id') == item['source_material']} != source_set):
                    raise ValueError('材料组全文或来源题组归属不匹配')
                if re.search(r'!\[[^\]]*\]\(|<img\b', material.group(1) + source_material['html'], re.I):
                    raise ValueError('材料含图片，当前材料组模式仅接受可完整核对的文字材料')
        else:
            raise ValueError('不支持的人工复核证据类型')
        if not item.get('rationale'):
            raise ValueError('人工复核缺少逐题判断依据')
        mappings[q] = h - 1
        fills.append({'q': q, 'huatu': h, 'sandwich': '人工复核计划', 'method': method, 'anchors': scores,
                      'rationale': item['rationale']})
    report.update({'mode': f'reviewed-{mode}', 'review_plan_sha256': digest(raw), 'source_identity': identity, 'fills': fills,
                   'skipped': [{'q': n, 'reason': '未在人工复核计划内'} for n in report['missing'] if n not in mappings]})
    return mappings, raw


def commit(path, paper, new, root, copies, expected_before):
    """Serialize reviewed writers and reject a changed paper before mutation."""
    lock = root / 'catalog/.huatu-reviewed-fill.lock'
    handle = lock.open('x', encoding='utf8')
    try:
        if digest(path.read_bytes()) != expected_before:
            raise ValueError('试卷在预检后已变化')
        commit_locked(path, paper, new, root, copies)
    finally:
        handle.close()
        lock.unlink()


def commit_locked(path, paper, new, root, copies):
    """Preflight all outputs, then roll back this operation on an I/O failure."""
    manifest = root / 'catalog/manifest.jsonl'
    original_manifest = manifest.read_bytes()
    rows = [json.loads(line) for line in original_manifest.decode('utf8').splitlines() if line.strip()]
    matches = [row for row in rows if row.get('path') == paper]
    if len(matches) != 1:
        raise ValueError('试卷在清单中不存在或不唯一')
    data = new.encode('utf8')
    matches[0].update(sha256=digest(data), bytes=len(data), image_references=len(re.findall(r'!\[[^\]]*\]\(|<img\b', new)))
    manifest_data = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows).encode('utf8')
    outputs = dict((dest, content) for content, dest in copies)
    outputs[path] = data
    outputs[manifest] = manifest_data
    originals = {dest: dest.read_bytes() if dest.exists() else None for dest in outputs}
    staged, backups = {}, {}
    changed = []
    retained = set()
    try:
        for dest, content in outputs.items():
            dest.parent.mkdir(parents=True, exist_ok=True)
            staged[dest] = stage_file(dest, content)
            if originals[dest] is not None:
                backups[dest] = stage_file(dest, originals[dest])
        for dest, temporary in staged.items():
            changed.append(dest)
            os.replace(temporary, dest)
    except OSError as failure:
        rollback_errors = []
        for dest in reversed(changed):
            try:
                if originals[dest] is None:
                    dest.unlink(missing_ok=True)
                else:
                    os.replace(backups[dest], dest)
            except OSError as rollback_error:
                # A failed atomic replace may have left the original intact.
                # Continue restoring other files even when this path is blocked.
                try:
                    restored = dest.read_bytes() == originals[dest] if dest.exists() else originals[dest] is None
                except OSError:
                    restored = False
                if not restored:
                    retained.add(backups.get(dest))
                    rollback_errors.append(f'{dest}: {rollback_error}; backup={backups.get(dest)}')
        if rollback_errors:
            raise OSError('写入失败，部分路径回滚失败：' + ' | '.join(rollback_errors)) from failure
        raise
    finally:
        for temporary in list(staged.values()) + list(backups.values()):
            if temporary not in retained:
                temporary.unlink(missing_ok=True)


def stage_file(destination, content):
    """Prepare complete bytes on the destination volume before any replacement."""
    descriptor, name = tempfile.mkstemp(prefix='.huatu-fill-', suffix='.tmp', dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return temporary
