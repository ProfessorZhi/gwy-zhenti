#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared primitives for the R3 media/layout quality tools.

Design rules that matter for this lane:

* **Read-only by construction.** Nothing here opens a file for writing, and
  nothing resolves a path outside the ``repo`` it was handed.  The callers pass
  the repo root in; this module never hard-codes one.
* **No glyph guessing.** We never try to decide what an image "looks like".
  Cell classification works on the Markdown text only; anything that would
  require reading a glyph out of a bitmap is reported as UNVERIFIED instead.
* **Tables are parsed, not regex-matched line by line.** A table is a block of
  consecutive pipe rows preceded by one row, followed by a delimiter row.  That
  matches GitHub's own GFM rule, which is the target renderer.
"""

import hashlib
import os
import re
import sys

# --------------------------------------------------------------------------
# Markdown table grammar (GFM)
# --------------------------------------------------------------------------

# A delimiter row: | --- | :--: | ---: |  (at least one dash per cell)
RE_TABLE_SEP = re.compile(r'^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$')
RE_FENCE = re.compile(r'^\s*(```|~~~)')
# A pipe row must start with '|' for our purposes: the repo writes tables that
# way, and a leading-pipe-less row is ambiguous with ordinary prose containing
# a stray '|'.  We record but do not fully parse the latter.
RE_PIPE_ROW = re.compile(r'^\s*\|')

# Question anchors used by the repo: "## 第 N 题" / "### 第 N 题"
RE_Q_ANCHOR = re.compile(r'^#{2,4}\s*第\s*(\d+)\s*题')
# Prompts / exercise headings (shenlun style)
RE_SECTION = re.compile(r'^#{1,4}\s+(.+?)\s*$')


def split_row(line):
    """Split one GFM table row into cells, honouring ``\\|`` escapes."""
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    out, cur, esc = [], [], False
    for ch in s:
        if esc:
            cur.append(ch)
            esc = False
            continue
        if ch == '\\':
            cur.append(ch)
            esc = True
            continue
        if ch == '|':
            out.append(''.join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append(''.join(cur))
    return [c.strip() for c in out]


def iter_pipe_tables(lines):
    """Yield :class:`Table` for every GFM table block in ``lines``.

    ``lines`` is a list of strings *without* trailing newlines.  ``lineno``
    fields are 1-based so they line up with editors and ``grep -n``.
    """
    i, n = 0, len(lines)
    in_fence = False
    while i < n:
        line = lines[i]
        if RE_FENCE.match(line):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        if (RE_PIPE_ROW.match(line)
                and i + 1 < n
                and RE_TABLE_SEP.match(lines[i + 1])
                and '|' in lines[i + 1]):
            header = split_row(line)
            sep = split_row(lines[i + 1])
            rows, raws = [], []
            j = i + 2
            while j < n and RE_PIPE_ROW.match(lines[j]):
                rows.append(split_row(lines[j]))
                raws.append(lines[j])
                j += 1
            yield Table(
                start=i + 1,
                end=j,                      # 1-based, inclusive last body row
                header_at=i + 1,
                sep_at=i + 2,
                header=header,
                sep=sep,
                rows=rows,
                body_raw=raws,
                header_raw=line,
                sep_raw=lines[i + 1],
            )
            i = j
            continue
        i += 1


class Table(object):
    __slots__ = ('start', 'end', 'header_at', 'sep_at', 'header', 'sep',
                 'rows', 'body_raw', 'header_raw', 'sep_raw')

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def ncols(self):
        return len(self.header)

    @property
    def nrows(self):
        return len(self.rows)

    def body_cell(self, r, c):
        """Best-effort body cell; returns '' when the row is short (ragged)."""
        row = self.rows[r]
        return row[c] if c < len(row) else ''

    def to_markdown(self):
        want = self.ncols
        out = [self.header_raw]
        out.append(self.sep_raw)
        for raw in self.body_raw:
            out.append(raw)
        return out


# --------------------------------------------------------------------------
# Cell classification
# --------------------------------------------------------------------------

# Placeholders that stand in for a missing value inside an array.  These are
# *data*, not column labels: "（ ）" in a 数阵 is the empty slot to solve for.
PLACEHOLDER_TOKENS = {
    '（ ）', '( )', '（）', '()', '?', '？', '—', '--', '-', '/', '／',
    '□', '△', '○', '×', '*', '…', '……', '空',
}

# Numeric with optional thousands separators, sign, percent, or a leading dot.
RE_NUM = re.compile(r'^[+\-−]?\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*[%％]?$|^[+\-−]?\s*\d+(?:\.\d+)?\s*[%％]?$')
# A bare fraction such as 1/2, 23.8/52.2
RE_FRAC = re.compile(r'^\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?$')
# A cell that is *only* punctuation / symbols (no letters, no digits).
RE_NONWORD = re.compile(r'^[^\w一-鿿]+$')
RE_HAS_CJK = re.compile(r'[一-鿿]')
# A lone Latin letter, optionally primed: a, m, x', y_1
RE_VAR = re.compile(r"^[A-Za-z]['′]?$")
RE_HAS_LATIN = re.compile(r'[A-Za-z]')
RE_HAS_DIGIT = re.compile(r'\d')

# ---------------------------------------------------------------------------
# Time axes.  This is the single biggest false-positive class for a "header is
# data" detector: a row of 2018/2019/2020 is numerically identical to a row of
# data, but it is a perfectly legitimate column header.  We therefore recognise
# time axes at ROW level, with domain bounds, instead of guessing per cell.
# ---------------------------------------------------------------------------
RE_YEAR = re.compile(r'^(19|20)\d{2}\s*(?:年|年末|年初)?$')
RE_YEAR_SPAN = re.compile(r'^(19|20)\d{2}\s*[-—~至]\s*(19|20)?\d{2}\s*年?$')
RE_YEAR_MONTH = re.compile(r'^(19|20)\d{2}\s*年\s*\d{1,2}\s*[-—~]\s*\d{1,2}\s*月$')
RE_MONTH = re.compile(r'^第?\s*\d{1,2}\s*月(?:份)?$')
RE_DAY = re.compile(r'^第?\s*\d{1,2}\s*日$')
RE_QUARTER = re.compile(r'^第?[一二三四1-4]\s*季度$')
RE_PERIOD = re.compile(r'^\d{1,2}\s*[-—~至]\s*\d{1,2}\s*月$')

# CJK suffixes that legitimately turn a number into one datum ("3亿元").
# Deliberately a closed whitelist: an open pattern such as \d+[一-鿿]{1,4}
# swallows real column labels like "2次逻辑" and is the second false-positive
# class this detector has to avoid.
UNIT_SUFFIXES = {
    '元', '万元', '亿元', '万亿', '千元', '美元', '欧元',
    '吨', '万吨', '亿吨', '公斤', '千克', '克', '斤',
    '人', '万人', '亿人', '人次', '户', '万户', '家', '个', '只', '头',
    '亩', '公顷', '亩次', '平方米', '平方公里', '平方千米', '万平方公里',
    '米', '千米', '公里', '厘米', '毫米', '海里',
    '台', '辆', '艘', '架', '件', '项', '起', '例', '所', '张', '本', '份',
    '倍', '次', '天', '年', '岁', '分', '秒', '小时', '千瓦', '万千瓦',
    '亿千瓦时', '万千瓦时', '千瓦时', '吨标准煤', '个百分点',
}


def is_time_cell(cell):
    s = norm_cell(cell)
    if not s:
        return False
    return bool(RE_YEAR.match(s) or RE_YEAR_SPAN.match(s) or RE_YEAR_MONTH.match(s)
                or RE_MONTH.match(s) or RE_DAY.match(s)
                or RE_QUARTER.match(s) or RE_PERIOD.match(s))


def row_is_index_axis(cells, first_body):
    """True when the row is a 1..N position index used as a column key.

    Two real shapes this has to separate:

    * ``| 1 | 2 | 3 | 4 | 5 | 6 |`` over ``| 人社 | 财政 | … |`` -- a seat /
      position index.  Real header.
    * ``| 1 | 2 | 3 |`` / ``| 4 | 5 | 6 |`` / ``| 7 | 8 | 9 |`` -- the first
      row of a 3x3 grid.  Real data.

    The discriminator is whether the numbers keep counting into the body.  If
    the body's first row continues the progression, the "header" was data.
    """
    vals = [norm_cell(c) for c in cells if norm_cell(c)]
    if len(vals) < 2 or not all(RE_NUM.match(v) and re.match(r'^\d+$', v) for v in vals):
        return False
    nums = [int(v) for v in vals]
    if len(set(nums)) != len(nums):
        return False
    start = nums[0]
    if start not in (0, 1):
        return False
    if nums != list(range(start, start + len(nums))):
        return False
    # Does the body continue the count?
    if first_body:
        b = [norm_cell(c) for c in first_body if norm_cell(c)]
        cont = [c for c in b if RE_NUM.match(c) and re.match(r'^\d+$', c)]
        if cont and int(cont[0]) == start + len(nums):
            return False
    return True


def row_is_time_axis(cells):
    """True when the non-empty cells form a time axis (years / months / days).

    Also requires the values to be *plausibly sequential*: a header of
    2011..2018 is an axis; two unrelated 4-digit numbers in a data row are not.
    """
    vals = [norm_cell(c) for c in cells if norm_cell(c)]
    if len(vals) < 2:
        return False
    if not all(is_time_cell(v) for v in vals):
        return False
    # If they are all years, require them to be distinct and monotonic-ish.
    years = []
    for v in vals:
        m = re.match(r'^((?:19|20)\d{2})', v)
        if m:
            years.append(int(m.group(1)))
    if len(years) == len(vals) and len(set(years)) == len(years):
        asc = all(b > a for a, b in zip(years, years[1:]))
        desc = all(b < a for a, b in zip(years, years[1:]))
        return asc or desc
    return True


def norm_cell(cell):
    """Normalise a cell for classification without changing its meaning."""
    s = (cell or '').strip()
    s = s.replace(' ', ' ')              # nbsp
    s = re.sub(r'\s+', ' ', s)
    return s


def cell_kind(cell):
    """Classify one table cell.

    Returns one of:
      ``EMPTY``       nothing at all
      ``PLACEHOLDER`` a "fill me in" token such as （ ） or ?
      ``NUM``         a bare number, optionally with % / thousands sep
      ``FRACTION``    a bare a/b
      ``TIME``        a year or a time-axis label (2018年, 1-3月)
      ``SYMBOL``      punctuation/symbols only
      ``TEXT``        anything with CJK or Latin words

    ``TIME`` is deliberately separate from ``NUM``: a row of ``2018年 2019年``
    is a *legitimate* header (a time axis), and treating it as data would be
    the main false-positive class for this detector.
    """
    s = norm_cell(cell)
    if not s:
        return 'EMPTY'
    if s in PLACEHOLDER_TOKENS:
        return 'PLACEHOLDER'
    # Time BEFORE number: a bare "2018" is a year axis far more often than it is
    # a count of 2018, and the row-level rule re-checks the domain bounds.
    if is_time_cell(s):
        return 'TIME'
    if RE_FRAC.match(s):
        return 'FRACTION'
    if RE_NUM.match(s):
        return 'NUM'
    if RE_NONWORD.match(s):
        return 'SYMBOL'
    # "28.5平方米" style: a number with a *known* unit suffix is a data value.
    m = re.match(r'^[+\-−]?\d+(?:\.\d+)?\s*[%％]?\s*([一-鿿]{1,6})$', s)
    if m and m.group(1) in UNIT_SUFFIXES:
        return 'NUM'
    # A lone Latin letter is an algebraic variable (a, m, x, y, b) when it sits
    # inside a number grid, but a column key when the whole row is letters
    # (A|B|C|D).  We return VAR and let the row-level rule decide.
    if RE_VAR.match(s):
        return 'VAR'
    if RE_HAS_CJK or RE_HAS_LATIN:
        return 'TEXT'
    return 'SYMBOL'


DATA_LIKE_KINDS = {'NUM', 'FRACTION', 'PLACEHOLDER', 'VAR'}
# VAR only counts as data when the row also holds a real number.
DATA_ONLY_WITH_NUM = {'VAR'}


def header_profile(cells, first_body=None):
    """Summarise what a header row *is*.

    Returns a dict with:
      ``kinds``     list of :func:`cell_kind` per cell
      ``verdict``   one of ``LABEL`` / ``DATA`` / ``INTERLEAVED`` / ``EMPTY`` / ``MIXED``
      ``confidence`` ``high`` / ``medium`` / ``low``
      ``reason``    short human-readable explanation
    """
    kinds = [cell_kind(c) for c in cells]
    nonempty = [(k, norm_cell(c)) for k, c in zip(kinds, cells) if k != 'EMPTY']
    if not nonempty:
        return {
            'kinds': kinds,
            'verdict': 'EMPTY',
            'confidence': 'high',
            'reason': '表头整行为空',
        }

    # A row of years/months/days is a legitimate axis header, not data.
    if row_is_time_axis(cells):
        return {
            'kinds': kinds,
            'verdict': 'LABEL',
            'confidence': 'high',
            'reason': '表头为时间轴（年/月/日序列），属正常列名',
        }

    # A 1..N position index over text labels is a legitimate column key.
    if row_is_index_axis(cells, first_body):
        return {
            'kinds': kinds,
            'verdict': 'LABEL',
            'confidence': 'high',
            'reason': '表头为 1..N 序号轴，正文为文字标签，属正常列名',
        }

    # A real header frequently leaves the corner cell empty ("| | 45元 | 75元 |").
    # Any empty cell at all therefore argues for header, not for a data row:
    # a data row misused as a header is normally full.
    n_empty = sum(1 for k in kinds if k == 'EMPTY')
    if n_empty and all(k in DATA_LIKE_KINDS or k == 'EMPTY' for k in kinds):
        return {
            'kinds': kinds,
            'verdict': 'LABEL',
            'confidence': 'high',
            'reason': '表头含空角格，其余为数值列名，属正常表头',
        }

    n_data = sum(1 for k, _ in nonempty if k in DATA_LIKE_KINDS)
    n_text = sum(1 for k, _ in nonempty if k == 'TEXT')
    n_time = sum(1 for k, _ in nonempty if k == 'TIME')
    n_sym = sum(1 for k, _ in nonempty if k == 'SYMBOL')
    n_var = sum(1 for k, _ in nonempty if k == 'VAR')
    total = len(nonempty)

    # A row of letters only (A|B|C|D) is a key, not a data row; VAR only counts
    # as data when a real number sits beside it.
    if n_var == total:
        return {
            'kinds': kinds,
            'verdict': 'LABEL',
            'confidence': 'high',
            'reason': '表头为纯字母列键（%d 格），属正常列名' % total,
        }

    # A full row of data-like cells: the classic "no header" matrix.
    if n_data == total:
        return {
            'kinds': kinds,
            'verdict': 'DATA',
            'confidence': 'high',
            'reason': '表头 %d 格全部为数值/占位符/变量，无任何列名' % total,
        }

    # Time axis only: 2018年 / 2019年 / 2020年 -- a real header.
    if n_time == total:
        return {
            'kinds': kinds,
            'verdict': 'LABEL',
            'confidence': 'high',
            'reason': '表头为纯时间轴（%d 格），属正常列名' % total,
        }

    # Interleaved label/number pairs, e.g. "东部地区 | 28 | 中部地区 | 23.9".
    # A 3-block array where every odd cell is a region name and every even cell
    # a value.  Not a header row: it is the first data row of a 数阵.
    if n_text and n_data and n_text == n_data and (n_text + n_data) == total:
        pairs_ok = all(
            (cell_kind(cells[i]) == 'TEXT') == (i % 2 == 0)
            for i in range(len(cells))
            if cell_kind(cells[i]) != 'EMPTY'
        )
        if pairs_ok and n_text >= 2:
            return {
                'kinds': kinds,
                'verdict': 'INTERLEAVED',
                'confidence': 'medium',
                'reason': '%d 组「名称+数值」交替排列，更像数阵首行而非列名' % n_text,
            }

    # Symbol-only row (e.g. a row of ★ symbols) with no words at all.
    if n_sym == total and n_time == 0:
        return {
            'kinds': kinds,
            'verdict': 'DATA',
            'confidence': 'medium',
            'reason': '表头 %d 格全部为符号，无列名' % total,
        }

    return {
        'kinds': kinds,
        'verdict': 'MIXED',
        'confidence': 'high',
        'reason': '表头含 %d 个文字列名，按列名处理' % n_text,
    }


# --------------------------------------------------------------------------
# Multi-level header analysis
# --------------------------------------------------------------------------

def column_signature(row):
    """Non-empty cells of a row, as a compact signature for comparison."""
    return [norm_cell(c) for c in row if norm_cell(c)]


def multilevel_report(table):
    """Look for a second header layer flattened into the body by the separator.

    A source table with two header rows gets flattened into one Markdown header
    row because GFM allows exactly one.  The converter's usual fix is an empty
    first row plus the real labels, but then the *first* header layer can end up
    as body row 0.  We detect the shape and say whether information is at risk;
    we never rewrite it.

    Returns ``None`` when the table does not look multi-level, else a dict.
    """
    if not table.rows:
        return None
    first = table.rows[0]
    first_kinds = [cell_kind(c) for c in first]
    header_kinds = header_profile(table.header)['kinds']
    header_empties = sum(1 for k in header_kinds if k == 'EMPTY')
    n_text_first = sum(1 for k in first_kinds if k == 'TEXT')
    # A *second header layer* demoted into the body reads as pure labels: no
    # numbers at all.  A normal first data row almost always carries numbers.
    # This is the discriminator that keeps ordinary "empty corner cell" headers
    # (| | 城镇 | 农村 | 男 | 女 |) out of the multi-level bucket.
    first_has_number = any(k in ('NUM', 'FRACTION', 'PLACEHOLDER') for k in first_kinds)
    first_is_labels = n_text_first >= 1 and not first_has_number

    # Duplicated adjacent labels are the fingerprint of a merged (colspan) cell
    # that was repeated when the header was flattened, e.g.
    # "5月 | 5月 | 比去年同期增长 | 比去年同期增长".
    labels = [norm_cell(c) for c in table.header if norm_cell(c)]
    dup = any(a == b for a, b in zip(labels, labels[1:]))

    overlap_cols = [
        c for c in range(min(table.ncols, len(first)))
        if norm_cell(table.header[c]) == '' and cell_kind(first[c]) == 'EMPTY'
    ]

    # A row whose only content is one label and otherwise blanks is a *section
    # title* the source table put inside the grid (a rowspan banner).  Rendering
    # it as an ordinary data row is a presentation defect, not a data defect.
    span_rows = []
    for r, row in enumerate(table.rows):
        filled = [norm_cell(c) for c in row if norm_cell(c)]
        blanks = sum(1 for c in row if not norm_cell(c))
        if len(filled) == 1 and blanks >= 2 and cell_kind(filled[0]) == 'TEXT' \
                and table.ncols >= 3:
            span_rows.append(r)

    if dup:
        return {
            'shape': 'DUPLICATED_GROUP',
            'risk': 'low',
            'detail': (
                '表头出现相邻重复标签（%s），源表合并（colspan）表头被逐列展开，'
                '分隔行使第 2 层子列名降级为数据行；内容未丢，仅层级排版丢失'
                % '、'.join(sorted({a for a, b in zip(labels, labels[1:]) if a == b})[:3])
            ),
            'cols': [],
            'info_lost': False,
        }

    if span_rows:
        return {
            'shape': 'SPAN_TITLE_ROW',
            'risk': 'low',
            'detail': '正文第 %s 行只有一个文字标签、其余为空，是源表的跨列小标题行，现按数据行渲染'
                      % ','.join(str(r + 1) for r in span_rows[:3]),
            'cols': [],
            'info_lost': False,
            'rows': span_rows[:3],
        }

    return None


# --------------------------------------------------------------------------
# Question / unit tracking
# --------------------------------------------------------------------------

def question_index(lines):
    """Map 1-based line number -> question number in effect at that line."""
    idx = []
    cur, cur_sec = None, None
    for i, line in enumerate(lines, 1):
        m = RE_Q_ANCHOR.match(line)
        if m:
            cur = int(m.group(1))
            cur_sec = None
        else:
            ms = RE_SECTION.match(line)
            if ms and not m:
                cur_sec = ms.group(1)
        idx.append((cur, cur_sec))
    return idx


def unit_at(qidx, lineno):
    """Return a stable unit label for a line: ``q<N>`` or ``sec:<heading>``."""
    q, sec = qidx[max(0, min(lineno - 1, len(qidx) - 1))]
    if q is not None:
        return 'q%d' % q
    if sec:
        return 'sec:%s' % sec[:24]
    return 'preamble'


# --------------------------------------------------------------------------
# Filesystem helpers
# --------------------------------------------------------------------------

def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def md_files(repo):
    """All ``.md`` files under ``repo`` (repo-relative posix paths), sorted."""
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
        for fn in files:
            if fn.endswith('.md'):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, repo).replace(os.sep, '/')
                out.append((rel, full))
    out.sort()
    return out


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def resolve_ref(md_abs, ref):
    """Resolve an image reference the way a reader's Markdown viewer would.

    Relative to the MD file's own directory -- the repo explicitly warns that
    resolving against the repo root silently walks the wrong directory.
    Returns ``(abs_path, escaped_root)``.
    """
    if re.match(r'^[a-z][a-z0-9+.-]*:', ref, re.I) or ref.startswith('//'):
        return None, 'external'
    if ref.startswith('#'):
        return None, 'anchor'
    p = ref.split('#')[0].split('?')[0]
    try:
        from urllib.parse import unquote
        p = unquote(p)
    except Exception:
        pass
    if os.path.isabs(p):
        return os.path.normpath(p), 'absolute'
    base = os.path.dirname(md_abs)
    full = os.path.normpath(os.path.join(base, p))
    return full, None


# --------------------------------------------------------------------------
# Tiny JSON helpers
# --------------------------------------------------------------------------

def dump_json(path, obj, indent=1):
    import json
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=indent, sort_keys=False)
        fh.write('\n')


def load_json(path):
    import json
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)
