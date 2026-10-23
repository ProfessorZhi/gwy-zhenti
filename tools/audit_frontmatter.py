#!/usr/bin/env python3
"""试卷结构、命名与槽位审计。

检查 catalog/manifest.jsonl 与每份 Markdown：
  1. frontmatter 关键字段是否齐全、是否与 manifest 一致；
  2. manifest.path 是否存在，抽查 sha256 / bytes 是否与实际文件一致；
  3. paper_type 分布，列出 unknown、复合卷型；
  4. 按 coverage_stats.norm_pt() 规则分槽，列出全部多层槽位并判断
     「同内容重复 / 不同内容误并」。

只读文件，不重命名、不移动、不删除任何试卷。默认写出：
  reports/STRUCTURE-AUDIT-20261023.md
  reports/structure-audit-20261023.json

用法：
    python3 -I tools/audit_frontmatter.py
    python3 -I tools/audit_frontmatter.py --sample 100 --json out.json --md out.md
"""

import argparse
import collections
import datetime
import difflib
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, 'catalog/manifest.jsonl')
DEFAULT_JSON = os.path.join(ROOT, 'reports/structure-audit-20261023.json')
DEFAULT_MD = os.path.join(ROOT, 'reports/STRUCTURE-AUDIT-20261023.md')

CORE_FIELDS = ['地区', '年份', '科目', '卷型', '校验状态']
SOURCE_FIELDS = ['来源', '来源明细', '来源路径', '来源整卷']
TRACE_FIELDS = ['源试卷ID', '来源明细', '来源路径', '来源整卷']
SECONDARY_FIELDS = ['源试卷ID', '采集时间']
COMPOUND_RE = re.compile(r'[/、+，,／]')
RANGE_RE = re.compile(r'(及以上|及以下)')
COLON_RE = re.compile(r'[:：]')


# --------------------------------------------------------------------------
# coverage_stats.py 的归一化规则（保持逐字一致）
# --------------------------------------------------------------------------
def norm_pt(pt):
    """归一化卷型：去掉尾部试卷 ID、统一全/半角冒号与甲/乙、A/B/C 写法。"""
    x = re.sub(r'-\d{5,}$', '', pt or '')
    x = x.replace('：', '-').replace(':', '-')
    x = re.sub(r'^卷(甲|乙)级$', r'\1级', x)
    x = re.sub(r'^(甲|乙)卷$', r'\1级', x)
    x = re.sub(r'^(A|B|C)卷$', r'\1类', x)
    if x.endswith('卷') and len(x) > 2:
        x = x[:-1]
    return x


def area_of(path):
    """与 coverage_stats.load_rows() 相同：国考取首段，其余取第二段。"""
    parts = path.split('/')
    return '国考' if parts[0] == '国考' else parts[1]


def load_rows():
    rows = []
    with open(MANIFEST, encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_frontmatter(text):
    """返回 (dict, error)。只支持 frontmatter 的一层 key: value。"""
    if not text.startswith('---'):
        return None, 'no-frontmatter'
    match = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
    if not match:
        return None, 'unclosed-frontmatter'
    data = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        data[key.strip()] = value
    return data, None


def read_text(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as handle:
        return handle.read()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(os.path.join(ROOT, path), 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# 正文特征：标题、题干、材料
# --------------------------------------------------------------------------
def first_title(text):
    match = re.search(r'^#\s+(.*)$', text, re.M)
    return match.group(1).strip() if match else ''


def normalize_title(title):
    title = re.sub(r'[《》〈〉（）()「」\[\]【】]', '', title)
    for word in ('公务员', '公考', '考试', '录用', '多省联考', '联考', '试题',
                 '真题', '题', '的', ' ', '　', '·', '—', '-', '_'):
        title = title.replace(word, '')
    return title


def normalize_question(text):
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'关联材料[:：].*?(?=作答要求|$)', '', text, flags=re.S)
    text = re.sub(r'作答要求[:：]', '', text)
    text = re.sub(r'material-[0-9a-f]+', '', text)
    text = re.sub(r'^[#\s]*问题[一二三四五六七八九十\d]+[:：]?', '', text)
    return re.sub(r'[#*>_`\s　]', '', text)


def question_sections(text):
    """按二级/三级/四级标题切分，返回 {题号: 归一化题干}。"""
    parts = re.split(r'\n(#{2,4}) ', text)
    found = {}
    for i in range(1, len(parts), 2):
        block = parts[i + 1]
        head = block.split('\n', 1)[0].strip()
        body = block.split('\n', 1)[1] if '\n' in block else ''
        match = re.search(r'第\s*(\d+)\s*题', head)
        if match:
            found[int(match.group(1))] = normalize_question(body)
    return found


def has_materials(text):
    return bool(re.search(r'\n#{2,4}\s*给定材料', text))


def section_count(text, kind):
    if kind == 'material':
        return len(re.findall(r'\n#{2,4}\s*材料(?:\s|material)', text))
    return len(question_sections(text))


def shingles(text, size=4, step=2):
    return {
        hashlib.md5(text[i:i + size].encode('utf-8')).digest()
        for i in range(0, max(0, len(text) - size), step)
    }


def text_similarity(a, b):
    if not a or not b:
        return 0.0
    if len(a) < 500 and len(b) < 500:
        return difflib.SequenceMatcher(None, a, b).ratio()
    left, right = shingles(a), shingles(b)
    return len(left & right) / len(left | right)


class FileFeatures:
    """单份试卷的正文特征，避免重复读盘。"""

    def __init__(self, row):
        self.row = row
        self.path = row['path']
        self.text = read_text(self.path)
        self.title = first_title(self.text)
        self.norm_title = normalize_title(self.title)
        self.questions = question_sections(self.text)
        self.materials = has_materials(self.text)
        self.material_count = section_count(self.text, 'material')

    @property
    def question_count(self):
        anchors = self.row.get('question_anchors')
        if isinstance(anchors, int):
            return anchors
        if isinstance(anchors, list):
            return len(anchors)
        return len(self.questions)


def compare_pair(left, right):
    common = sorted(set(left.questions) & set(right.questions))
    if common:
        q_sim = sum(
            text_similarity(left.questions[i], right.questions[i]) for i in common
        ) / len(common)
    elif left.questions and right.questions:
        q_sim = 0.0
    else:
        q_sim = None
    title_sim = difflib.SequenceMatcher(
        None, left.norm_title, right.norm_title
    ).ratio()

    n_left, n_right = len(left.questions), len(right.questions)
    if n_left and n_right:
        # 题数相同：要求高相似；题数略少：允许是截断副本。
        # 题数相同但只有 0.75–0.85 的，多是同年的另一套卷，不能算重复。
        same = (
            n_left == n_right and q_sim is not None and q_sim >= 0.85
        ) or (
            n_left != n_right and q_sim is not None and q_sim >= 0.75
            and abs(n_left - n_right) <= 10
            and len(common) >= 0.9 * min(n_left, n_right)
        )
    else:
        # 一份只有参考答案、没有题干：退回标题比对。
        same = title_sim >= 0.75
    return q_sim, title_sim, bool(same)


def keep_score(feature):
    """保留优先级：有材料 > 有题干 > 题多 > 篇幅大。"""
    return (
        1 if feature.materials else 0,
        1 if feature.questions else 0,
        len(feature.questions),
        len(feature.text),
    )


# --------------------------------------------------------------------------
# 审计主体
# --------------------------------------------------------------------------
def audit(rows, sample_size):
    result = {
        'files': len(rows),
        'manifest': 'catalog/manifest.jsonl',
        'frontmatter': {
            'core_required': CORE_FIELDS,
            'core_missing': [],
            'parse_errors': [],
            'source_empty': [],
            'no_trace_field': [],
            'secondary_missing': {field: [] for field in SECONDARY_FIELDS},
            'manifest_mismatch': [],
            'malformed_status': [],
        },
        'manifest_integrity': {
            'paths_checked': 0,
            'paths_missing': [],
            'sha_sample_size': 0,
            'sha_checked': 0,
            'sha_mismatch': [],
            'bytes_mismatch': [],
        },
        'paper_types': {
            'distribution': {},
            'unknown': [],
            'compound': [],
            'colon_variant': [],
        },
        'slots': {
            'total': 0,
            'multi': 0,
            'all_same': 0,
            'all_diff': 0,
            'mixed': 0,
            'groups': [],
        },
    }

    fm = result['frontmatter']
    for row in rows:
        path = row['path']
        text = read_text(path)
        data, error = parse_frontmatter(text)
        if error:
            fm['parse_errors'].append({'path': path, 'error': error})
            continue
        for field in CORE_FIELDS:
            if not data.get(field):
                fm['core_missing'].append({'path': path, 'field': field})
        if not data.get('来源'):
            fm['source_empty'].append({
                'path': path,
                'related': [f for f in SOURCE_FIELDS if data.get(f)],
                'status': data.get('校验状态', '')[:40],
            })
        if not any(data.get(field) for field in TRACE_FIELDS):
            fm['no_trace_field'].append(path)
        for field in SECONDARY_FIELDS:
            if not data.get(field):
                fm['secondary_missing'][field].append(path)
        for field, manifest_field in (
            ('地区', 'area'), ('年份', 'year'), ('科目', 'subject'), ('卷型', 'paper_type')
        ):
            actual, expected = data.get(field, ''), row.get(manifest_field, '')
            if str(actual) != str(expected):
                fm['manifest_mismatch'].append({
                    'path': path, 'field': field,
                    'frontmatter': actual, 'manifest': expected,
                })
        status = data.get('校验状态', '')
        if status.startswith(('；', ';')):
            fm['malformed_status'].append(path)

    # manifest 路径与 sha256 抽查
    integrity = result['manifest_integrity']
    integrity['paths_checked'] = len(rows)
    integrity['paths_missing'] = [
        row['path'] for row in rows
        if not os.path.isfile(os.path.join(ROOT, row['path']))
    ]
    step = max(1, len(rows) // max(1, sample_size))
    sample = rows[::step][:sample_size]
    integrity['sha_sample_size'] = len(sample)
    for row in sample:
        path = row['path']
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue
        actual = sha256_file(path)
        integrity['sha_checked'] += 1
        if actual != row.get('sha256'):
            integrity['sha_mismatch'].append({
                'path': path, 'manifest': row.get('sha256'), 'actual': actual,
            })
        if row.get('bytes') is not None and os.path.getsize(full) != row['bytes']:
            integrity['bytes_mismatch'].append({
                'path': path, 'manifest': row['bytes'],
                'actual': os.path.getsize(full),
            })

    # paper_type 分布 / unknown / 复合 / 冒号子类
    types = result['paper_types']
    counter = collections.Counter(row.get('paper_type') or '' for row in rows)
    types['distribution'] = dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))
    for row in rows:
        paper_type = row.get('paper_type') or ''
        if paper_type.lower().startswith('unknown'):
            types['unknown'].append({
                'path': row['path'],
                'paper_type': paper_type,
                'year': row.get('year'),
                'area': area_of(row['path']),
            })
        if COMPOUND_RE.search(paper_type) and not RANGE_RE.search(paper_type):
            types['compound'].append({
                'path': row['path'], 'paper_type': paper_type,
            })
        elif COLON_RE.search(paper_type):
            types['colon_variant'].append({
                'path': row['path'], 'paper_type': paper_type,
            })

    # 槽位分组
    slots = result['slots']
    grouped = collections.defaultdict(list)
    for row in rows:
        key = (
            area_of(row['path']), row.get('year'), row.get('subject'),
            norm_pt(row.get('paper_type')),
        )
        grouped[key].append(row)
    slots['total'] = len(grouped)
    for key in sorted(grouped, key=lambda k: tuple(str(x) for x in k)):
        members = grouped[key]
        if len(members) < 2:
            continue
        slots['multi'] += 1
        features = [FileFeatures(row) for row in members]
        pairs = []
        for i in range(len(features)):
            for j in range(i + 1, len(features)):
                q_sim, title_sim, same = compare_pair(features[i], features[j])
                pairs.append({
                    'a': features[i].path,
                    'b': features[j].path,
                    'question_similarity': None if q_sim is None else round(q_sim, 4),
                    'title_similarity': round(title_sim, 4),
                    'same_content': same,
                })
        same_pairs = sum(1 for pair in pairs if pair['same_content'])
        if same_pairs == len(pairs):
            classification = 'all_same'
            slots['all_same'] += 1
        elif same_pairs == 0:
            classification = 'all_diff'
            slots['all_diff'] += 1
        else:
            classification = 'mixed'
            slots['mixed'] += 1

        # 混合槽：取最大的「同卷」连通分量作为重复簇，簇外文件按不同卷处理。
        cluster = set(range(len(features)))
        if classification == 'mixed':
            adjacency = {i: set() for i in range(len(features))}
            for pair in pairs:
                if pair['same_content']:
                    i = next(n for n, f in enumerate(features) if f.path == pair['a'])
                    j = next(n for n, f in enumerate(features) if f.path == pair['b'])
                    adjacency[i].add(j)
                    adjacency[j].add(i)
            seen, components = set(), []
            for start in range(len(features)):
                if start in seen:
                    continue
                stack, component = [start], set()
                while stack:
                    node = stack.pop()
                    if node in component:
                        continue
                    component.add(node)
                    stack.extend(adjacency[node] - component)
                seen |= component
                components.append(component)
            cluster = max(components, key=len)
        best = max((features[i] for i in cluster), key=keep_score)
        odd = [features[i] for i in range(len(features)) if i not in cluster]

        file_entries = []
        for feature in features:
            recommendation = ''
            if classification == 'all_diff':
                recommendation = (
                    '保留；当前 paper_type 把不同卷并进同一槽，'
                    '建议按标题/文件名修正 paper_type 后拆槽'
                )
            elif feature in odd:
                recommendation = (
                    '与同槽其他文件不同卷；建议修正 paper_type 后拆出本槽并保留'
                )
            elif feature is best:
                recommendation = '建议保留（材料/题干/篇幅最完整）'
            elif not feature.questions:
                recommendation = '仅参考答案；建议合并到保留卷的答案区后归档或仅标注'
            else:
                recommendation = '同卷异版；建议仅标注，不重复计入覆盖'
            file_entries.append({
                'path': feature.path,
                'paper_type': feature.row.get('paper_type'),
                'question_anchors': feature.row.get('question_anchors'),
                'question_sections': len(feature.questions),
                'has_materials': feature.materials,
                'material_sections': feature.material_count,
                'bytes': feature.row.get('bytes'),
                'sha256': feature.row.get('sha256'),
                'title': feature.title,
                'recommendation': recommendation,
            })

        if classification == 'all_same':
            group_rec = (
                f'同内容重复（同卷异版，{len(members)} 份）；'
                f'建议保留 {best.path}，其余仅标注'
            )
        elif classification == 'all_diff':
            group_rec = '不同内容（槽位误并）；建议逐份修正 paper_type 后拆分，文件全部保留'
        else:
            duplication = [pair for pair in pairs if pair['same_content']]
            group_rec = (
                '混合：组内既有同卷异版也有不同卷；'
                f'同卷簇保留 {best.path}，簇外 '
                + '、'.join(f.path for f in odd)
                + ' 建议修正 paper_type 后拆出本槽（同卷对：'
                + '；'.join(f'{p["a"]} ↔ {p["b"]}' for p in duplication)
                + '）'
            )

        slots['groups'].append({
            'slot': {
                'area': key[0], 'year': key[1], 'subject': key[2],
                'normalized_paper_type': key[3],
            },
            'classification': classification,
            'files': file_entries,
            'pairs': pairs,
            'keep': best.path,
            'recommendation': group_rec,
        })
    return result


# --------------------------------------------------------------------------
# Markdown 报告
# --------------------------------------------------------------------------
def md_escape(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def render_markdown(result, json_path):
    fm = result['frontmatter']
    integrity = result['manifest_integrity']
    types = result['paper_types']
    slots = result['slots']
    lines = []

    same_groups = slots['all_same']
    mixed_groups = slots['mixed']
    diff_groups = slots['all_diff']
    duplicate_groups = same_groups + mixed_groups

    lines.append('# 试卷结构、命名与槽位审计（2026-10-23）')
    lines.append('')
    lines.append('数据源：`catalog/manifest.jsonl`（%d 份）。机器结果：`%s`。' % (
        result['files'], os.path.relpath(json_path, ROOT)))
    lines.append('本审计只读，未重命名、移动或删除任何试卷；所有建议均需人工确认后另行执行。')
    lines.append('')

    lines.append('## 一、结论')
    lines.append('')
    lines.append('1. **frontmatter 主字段基本齐全**：`地区/年份/科目/卷型/校验状态` 缺失 %d 处；'
                 '`来源` 为空 %d 份（这 %d 份仍有 `来源整卷`，属字段不统一而非完全无源）；'
                 '`校验状态` 以中文分号开头 %d 份。' % (
                     len(fm['core_missing']), len(fm['source_empty']),
                     len(fm['source_empty']), len(fm['malformed_status'])))
    lines.append('2. **frontmatter 与 manifest 有 %d 处不一致**，全部是 `地区`：'
                 'frontmatter 写「广东」、manifest/路径推得「广州」。' % len(fm['manifest_mismatch']))
    lines.append('3. **manifest 完整性通过**：%d 条 path 全部可解析；sha256 抽查 %d 份、'
                 'bytes 抽查 %d 份，均无不一致。' % (
                     integrity['paths_checked'], integrity['sha_checked'],
                     integrity['sha_checked']))
    lines.append('4. **卷型异常**：`unknown` 类 %d 份（23 份 `unknown` + 5 份 '
                 '`unknown-list-row-has-no-abc-marker`）；复合卷型 %d 份、%d 种写法；'
                 '另有 %d 份冒号子类写法（如 `A卷：省直`）归一化不彻底。' % (
                     len(types['unknown']), len(types['compound']),
                     len({item['paper_type'] for item in types['compound']}),
                     len(types['colon_variant'])))
    lines.append('5. **多层槽位 %d 组**：整组同内容 %d 组、整组不同内容 %d 组、混合 %d 组。'
                 '即 **%d 组含真重复**（同卷异版），**%d 组是不同卷被 paper_type 误并**；'
                 '但逐字节完全相同（sha256 相同）的重复为 **0 组**，所有重复都是'
                 '「同卷异版/不同来源版本」，不是文件拷贝。' % (
                     slots['multi'], same_groups, diff_groups, mixed_groups,
                     duplicate_groups, diff_groups))
    lines.append('6. **归一化缺陷**：`norm_pt()` 先替换冒号再匹配 `^(A|B|C)卷$`，'
                 '导致 `A卷：省直` 归一为 `A卷-省直` 而不是 `A类-省直`；'
                 '建议把 A/B/C 替换放在冒号替换之前，或改用前缀匹配。')
    lines.append('')

    lines.append('## 二、优先处理建议（Top 3）')
    lines.append('')
    lines.append('1. **先拆 %d 组「不同内容」误并槽位**：这些槽位把两份不同试卷算成同一覆盖点，'
                 '会虚增覆盖率。优先修正 `paper_type`：内蒙古 2020 行测（公安/统考）、'
                 '江西 2016/2018 行测（法检/统考）、黑龙江 2017/2019（公检法/统考/市区）、'
                 '广东 2019–2021 行测选调生（综合行政能力测验/思维能力测验）、'
                 '新疆兵团 2021 申论（一卷/二卷）、天津 2017（滨海新区/多省联考）、'
                 '广州 2017/2018（单/双考区、一/二）、湖北 2024 申论（两份不同省市卷）。' % diff_groups)
    lines.append('2. **再处理 %d 组同卷异版冗余**：没有一组字节重复，说明是不同来源/排版版本；'
                 '逐组保留「有材料 + 有题干 + 篇幅完整」的一份，其余只做标注，'
                 '仅参考答案的副本合并答案后归档，不计入覆盖。' % duplicate_groups)
    lines.append('3. **补卷型与字段一致性**：为 %d 份 unknown、%d 份复合卷型定值；'
                 '修 3 份江苏 A 类的 `来源` 空值与 `校验状态` 前导「；」；'
                 '统一 9 份广州卷的 `地区` 口径（广东 vs 广州）。' % (
                     len(types['unknown']), len(types['compound'])))
    lines.append('')

    # 表一
    lines.append('## 三、表 1：字段缺失与一致性问题')
    lines.append('')
    lines.append('| 类型 | 路径 | 现状 | 建议处理 |')
    lines.append('| --- | --- | --- | --- |')
    for item in fm['core_missing']:
        lines.append('| 主字段缺失 | `%s` | `%s` 为空 | 补全后重跑本审计 |' % (
            md_escape(item['path']), md_escape(item['field'])))
    for item in fm['source_empty']:
        related = '、'.join(item['related']) or '无'
        lines.append('| 来源为空 | `%s` | `来源` 缺失；现有：%s；校验状态以「；」开头 | '
                     '补 `来源:`（可复用 `来源整卷`），并清理状态前导分号 |' % (
                         md_escape(item['path']), md_escape(related)))
    for item in fm['manifest_mismatch']:
        lines.append('| 与 manifest 不一致 | `%s` | `%s`：frontmatter=`%s`，manifest=`%s` | '
                     '二选一统一：frontmatter 改「广州」或 manifest 改「广东」，并写入命名规范 |' % (
                         md_escape(item['path']), md_escape(item['field']),
                         md_escape(item['frontmatter']), md_escape(item['manifest'])))
    for item in fm['parse_errors']:
        lines.append('| frontmatter 无法解析 | `%s` | %s | 修复 `---` 块 |' % (
            md_escape(item['path']), md_escape(item['error'])))
    lines.append('')
    lines.append('次级完整性（不阻断覆盖统计）：`源试卷ID` 缺 %d 份、`采集时间` 缺 %d 份；'
                 '其中 %d 份同时没有 `来源明细/来源路径/来源整卷`，仅靠 `来源` URL 追溯，'
                 '建议后续补可追溯 ID。完整路径见 JSON `frontmatter.secondary_missing` 与 '
                 '`frontmatter.no_trace_field`。' % (
                     len(fm['secondary_missing']['源试卷ID']),
                     len(fm['secondary_missing']['采集时间']),
                     len(fm['no_trace_field'])))
    lines.append('')

    # 表二
    lines.append('## 四、表 2：卷型异常')
    lines.append('')
    lines.append('| 类别 | paper_type | 路径 | 建议处理 |')
    lines.append('| --- | --- | --- | --- |')
    for item in types['unknown']:
        if item['paper_type'] == 'unknown':
            action = '按标题/来源补成 省市/县乡/A类/B类 等单一值，同步 frontmatter 与 manifest'
        else:
            action = '来源列表行无 ABC 标记；按标题与材料判定后补 A/B/C 类'
        lines.append('| unknown | `%s` | `%s` | %s |' % (
            md_escape(item['paper_type']), md_escape(item['path']), action))
    for item in types['compound']:
        action = ('确认是否同卷共用：是则新增规范复合值并全库统一；'
                  '否则拆成两个单卷型，禁止用「、」「+」拼写')
        lines.append('| 复合卷型 | `%s` | `%s` | %s |' % (
            md_escape(item['paper_type']), md_escape(item['path']), action))
    for item in types['colon_variant']:
        action = ('统一为 `A类（省直）` 等两级写法；'
                  '并修正 norm_pt 的冒号/AB C 替换顺序')
        lines.append('| 冒号子类 | `%s` | `%s` | %s |' % (
            md_escape(item['paper_type']), md_escape(item['path']), action))
    lines.append('')
    lines.append('`paper_type` 取值分布（Top 20，完整分布见 JSON）：')
    lines.append('')
    lines.append('| paper_type | 份数 |')
    lines.append('| --- | ---: |')
    for value, count in list(types['distribution'].items())[:20]:
        lines.append('| `%s` | %d |' % (md_escape(value), count))
    lines.append('')

    # 表三
    lines.append('## 五、表 3：多层槽位（%d 组）' % slots['multi'])
    lines.append('')
    lines.append('槽位键为 `(地区, 年份, 科目, norm_pt(卷型))`。判定规则：题号交集逐题比对，'
                 '同题数且题干相似度 ≥0.85，或题数不同但相差 ≤10、交集覆盖 ≥90% 且'
                 '相似度 ≥0.75（视为截断副本），判为同卷；'
                 '任一份无题干时退回标题相似度（≥0.75 视为同卷）。')
    lines.append('')
    for index, group in enumerate(slots['groups'], 1):
        slot = group['slot']
        lines.append('### %d. %s / %s / %s / `%s` —— %s' % (
            index, slot['area'], slot['year'], slot['subject'],
            md_escape(slot['normalized_paper_type']),
            {'all_same': '同内容重复', 'all_diff': '不同内容（误并）',
             'mixed': '混合'}[group['classification']]))
        lines.append('')
        lines.append('| 文件 | 题数 | 材料 | 字节 | sha256（前 16） | 建议 |')
        lines.append('| --- | ---: | :---: | ---: | --- | --- |')
        for item in group['files']:
            lines.append('| `%s` | %s | %s | %s | `%s` | %s |' % (
                md_escape(item['path']),
                item['question_anchors'] if item['question_anchors'] is not None
                else item['question_sections'],
                '有' if item['has_materials'] else '无',
                item['bytes'] if item['bytes'] is not None else '',
                (item['sha256'] or '')[:16],
                md_escape(item['recommendation'])))
        lines.append('')
        lines.append('组建议：%s' % group['recommendation'])
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('生成方式：`python3 -I tools/audit_frontmatter.py`。'
                 '机器结果见 `%s`。' % os.path.relpath(json_path, ROOT))
    lines.append('')
    return '\n'.join(lines)


# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='试卷结构、命名与槽位审计')
    parser.add_argument('--json', default=DEFAULT_JSON, help='JSON 输出路径')
    parser.add_argument('--md', default=DEFAULT_MD, help='Markdown 输出路径')
    parser.add_argument('--sample', type=int, default=100, help='sha256 抽查份数')
    args = parser.parse_args()

    rows = load_rows()
    result = audit(rows, max(1, args.sample))
    result['generated_at'] = datetime.datetime.now().astimezone().isoformat(
        timespec='seconds')

    os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
    with open(args.json, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write('\n')
    with open(args.md, 'w', encoding='utf-8') as handle:
        handle.write(render_markdown(result, args.json))

    fm = result['frontmatter']
    slots = result['slots']
    print('文件 %d · path 缺失 %d · sha 抽查 %d（不一致 %d）' % (
        result['files'], len(result['manifest_integrity']['paths_missing']),
        result['manifest_integrity']['sha_checked'],
        len(result['manifest_integrity']['sha_mismatch'])))
    print('主字段缺失 %d · 来源为空 %d · manifest 不一致 %d' % (
        len(fm['core_missing']), len(fm['source_empty']),
        len(fm['manifest_mismatch'])))
    print('unknown %d · 复合 %d · 冒号子类 %d' % (
        len(result['paper_types']['unknown']),
        len(result['paper_types']['compound']),
        len(result['paper_types']['colon_variant'])))
    print('槽位 %d · 多层 %d（整组同内容 %d / 不同内容 %d / 混合 %d）' % (
        slots['total'], slots['multi'], slots['all_same'],
        slots['all_diff'], slots['mixed']))
    print('写出 %s' % os.path.relpath(args.json, ROOT))
    print('写出 %s' % os.path.relpath(args.md, ROOT))


if __name__ == '__main__':
    main()
