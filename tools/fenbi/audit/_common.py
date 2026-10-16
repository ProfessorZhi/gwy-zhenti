"""Shared parsing helpers for the missing-25 evidence audit.

Pure standard library, no network, no credentials. Every path this module
touches is derived from the caller-supplied repository root.
"""

import os
import re

# A question heading in this repository's 行测 markdown, at any level, e.g.
#   ## 第 42 题　<sub>qid 13319300 · 逻辑填空</sub>
#   ### 第 46 题　<sub>qid 13319302 · 逻辑填空</sub>
HEAD_RE = re.compile(r"^#{1,6}\s*第\s*(\d+)\s*题")

# Shared-material blocks ("## 材料 1（第46—50题共用）") are boundaries, not
# question bodies. Treating them as boundaries stops a question block from
# absorbing an adjacent material group.
MATERIAL_RE = re.compile(r"^#{1,6}\s*材料")

# Boilerplate that marks an unresolvable collection placeholder rather than a
# real stem. Kept short on purpose: these identify a slot's state, they are not
# reproductions of any source's question text.
PLACEHOLDER_MARKERS = {
    "collection_pending": r"题目正在全力以赴征集|正在搜集中",
    "not_collected": r"本题暂无收集到|暂无收集到",
    "recollection_missing": r"网友未回忆起",
    "stub_options": r"正确答案[是为]A",
    "absent_options": r"缺失|暂缺|^\s*A\.\s*缺",
    "grading_stub": r"题目缺失|非客观题，请交卷后查看参考解析估分",
    "bracketed_absent": r"\d+\s*题暂缺|暂缺$",
}

FRONTMATTER_FIELDS = (
    "考试", "地区", "年份", "科目", "卷型", "真题性质", "命题形式",
    "对照题本题量", "实有题数", "缺失原题号", "整卷核验状态", "题号口径",
    "题序对照来源",
)

# "## 材料 1（第46—50题共用）" — a shared-material block and the question range
# it covers. Range separators vary across papers, so accept the common ones.
MATERIAL_HEAD_RE = re.compile(r"^#{1,6}\s*材料\s*(\d+)")
MATERIAL_RANGE_RE = re.compile(r"第\s*(\d+)\s*[—–\-~～至]\s*(\d+)\s*题")

# Repository images are written as <img ... src="../../../图片/<paper>/题目图|<公式图>/<f>.png" />
# `flag="tex"` marks a typeset formula rather than a figure.
IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc=\"([^\"]+)\"", re.I)
IMG_FLAG_RE = re.compile(r"<img\b[^>]*?\bflag=\"([^\"]*)\"", re.I)


def default_repo_root():
    """Repository root inferred from this file's location (tools/fenbi/audit/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir))


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_frontmatter(text):
    """Split a markdown file into (frontmatter dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip().strip('"')
    return fm, text[end + 4:]


def parse_int_list(raw):
    return [int(x) for x in re.findall(r"\d+", raw or "")]


def question_numbers(body):
    """Every question number carrying a heading, in document order."""
    return [int(m.group(1)) for line in body.splitlines()
            if (m := HEAD_RE.match(line))]


def question_blocks(body):
    """Question number -> stem+options text (shared material excluded)."""
    blocks, current, number = {}, [], None
    for line in body.splitlines():
        if MATERIAL_RE.match(line):
            if number is not None:
                blocks[number] = "\n".join(current).strip()
            current, number = [], None
            continue
        m = HEAD_RE.match(line)
        if m:
            if number is not None:
                blocks[number] = "\n".join(current).strip()
            number, current = int(m.group(1)), [line]
        elif number is not None:
            current.append(line)
    if number is not None:
        blocks[number] = "\n".join(current).strip()
    return blocks


def fold_for_compare(block_text):
    """Fold a block to a comparison key: drop the heading, option markers, whitespace.

    Used only to decide whether two blocks are the same text. Never used to
    rewrite content.
    """
    body = "\n".join(l for l in block_text.splitlines() if not HEAD_RE.match(l))
    body = re.sub(r"[-\*]\s*\*\*[A-D]\*\*[\.、]?", "", body)
    return re.sub(r"\s+", "", body)


def detect_placeholders(text):
    """Names of placeholder markers found in a chunk of text."""
    return [name for name, pattern in PLACEHOLDER_MARKERS.items()
            if re.search(pattern, text, re.M)]


# A stub is boilerplate standing in for a question the source never collected,
# e.g. "题目正在全力以赴征集，将会第一时间上传". Real stems can be short (analogy
# items), so a marker must be present AND the whole body must be about that
# marker — length alone is not the test.
STUB_MAX_CHARS = 60


def looks_like_placeholder_stub(text):
    """True when the text is a collection stub rather than question content.

    The presence of a question number or a question container proves only that
    a slot exists. This is the check that distinguishes a slot from content.
    """
    normalized = normalize_comparison_text(text)["strict"]
    if not normalized or len(normalized) > STUB_MAX_CHARS:
        return False
    return bool(detect_placeholders(normalized))


IMAGE_TOKEN = " ⟦IMAGE⟧ "

import html as _html  # noqa: E402
from html.parser import HTMLParser  # noqa: E402


class _TextExtractor(HTMLParser):
    """Approximate the aligner's cheerio-based text extraction.

    cheerio is not available offline, so this reproduces the parts that matter
    for comparison: script/style dropped, images replaced by a position token,
    block elements padded with spaces, <br> turned into newlines.
    """

    _BLOCK = {"p", "div", "li", "tr", "table", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.images = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("img", "image", "source"):
            attr = dict(attrs)
            src = (attr.get("src") or attr.get("data-src")
                   or attr.get("href") or attr.get("xlink:href") or "")
            self.images.append(src)
            self.parts.append(IMAGE_TOKEN)
        elif tag == "br":
            self.parts.append("\n")
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def normalize_comparison_text(value):
    """Port of normalizeComparisonText() from tools/fenbi/src/align.mjs.

    Returns {strict, formatOnly, images}. NFKC is deliberately NOT applied:
    it would erase meaningful mathematics (x² -> x2). Only fullwidth ASCII and
    the ideographic space are folded, matching the JS implementation.
    """
    markdown = "" if value is None else str(value)

    def _md_image(match):
        reference = (match.group(1) or match.group(2) or "")
        reference = (reference.replace("&", "&amp;").replace('"', "&quot;")
                     .replace("<", "&lt;"))
        return f'<img src="{reference}">'

    markdown = re.sub(r"!\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\"']*[\"'])?\)",
                      _md_image, markdown)
    markdown = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", markdown)
    markdown = re.sub(r"\*\*([^*]+)\*\*", r"\1", markdown)
    markdown = re.sub(r"`([^`]+)`", r"\1", markdown)

    extractor = _TextExtractor()
    extractor.feed(markdown)
    extractor.close()

    text = extractor.text()
    text = "".join(
        chr(ord(ch) - 0xFEE0) if "！" <= ch <= "～" else ch for ch in text)
    text = text.replace("　", " ")
    strict = re.sub(r"\s+", " ", text).strip()
    return {
        "strict": strict,
        "formatOnly": re.sub(r"\s+", "", strict),
        "images": extractor.images,
    }


def compare_text(source, repository):
    """Port of compareText() from align.mjs, same statuses and reasons."""
    a, b = normalize_comparison_text(source), normalize_comparison_text(repository)
    if not a["strict"]:
        return {"status": "unknown", "reason": "source-content-not-observed"}
    if not b["strict"]:
        return {"status": "different", "reason": "repository-content-absent"}
    if a["strict"] == b["strict"]:
        return {"status": "same", "reason": "normalized-text-equal", "formatOnly": False}
    if a["formatOnly"] == b["formatOnly"]:
        return {"status": "same", "reason": "whitespace-only-difference", "formatOnly": True}
    return {"status": "different", "reason": "content-differs"}


def compare_options(source, repository):
    """Port of compareOptions() from align.mjs for non-essay subjects."""
    if not source:
        return {"status": "unknown", "reason": "source-options-not-observed"}
    if len(source) != len(repository):
        return {"status": "different", "reason": "option-count-differs",
                "sourceCount": len(source), "repositoryCount": len(repository)}
    if any(not o.get("label") for o in source):
        return {"status": "unknown", "reason": "source-option-labels-not-observed"}
    parts = []
    for index, option in enumerate(source):
        other = repository[index]
        if option.get("label") != other.get("label"):
            parts.append({"status": "different", "reason": "option-label-or-order-differs"})
        else:
            parts.append(compare_text(option.get("text", ""), other.get("text", "")))
    if any(p["status"] == "different" for p in parts):
        return {"status": "different",
                "reason": "option-content-label-or-order-differs"}
    if any(p["status"] == "unknown" for p in parts):
        return {"status": "unknown", "reason": "option-content-not-observed"}
    return {"status": "same", "reason": "all-options-equal",
            "formatOnly": any(p.get("formatOnly") for p in parts)}


def compare_images(source_digests, repository_digests):
    """Compare image sets by content digest.

    The capture side records sha256 for every asset it downloaded; the library
    side is digested here. Byte equality is the only thing that counts as
    `same` — a matching count is not enough.
    """
    if len(source_digests) != len(repository_digests):
        return {"status": "different", "reason": "image-reference-count-differs",
                "sourceCount": len(source_digests),
                "repositoryCount": len(repository_digests)}
    if not source_digests:
        return {"status": "not_compared", "reason": "no-image-references",
                "sourceCount": 0, "repositoryCount": 0}
    if any(not d for d in source_digests) or any(not d for d in repository_digests):
        return {"status": "unknown", "reason": "image-bytes-not-compared",
                "sourceCount": len(source_digests),
                "repositoryCount": len(repository_digests)}
    if sorted(source_digests) != sorted(repository_digests):
        return {"status": "different", "reason": "image-bytes-differ",
                "sourceCount": len(source_digests),
                "repositoryCount": len(repository_digests)}
    return {"status": "same", "reason": "all-image-bytes-equal",
            "sourceCount": len(source_digests),
            "repositoryCount": len(repository_digests)}


def parse_materials(body):
    """Shared-material blocks: [{id, range, head_line, text}]."""
    materials, current = [], None
    for index, line in enumerate(body.splitlines()):
        m = MATERIAL_HEAD_RE.match(line)
        if m:
            if current:
                materials.append(current)
            rng = MATERIAL_RANGE_RE.search(line)
            current = {
                "id": m.group(1),
                "range": [int(rng.group(1)), int(rng.group(2))] if rng else None,
                "head_line": index,
                "text": line,
            }
        elif current is not None:
            current["text"] += "\n" + line
    if current:
        materials.append(current)
    return materials


def material_ids_for(number, materials):
    """Material ids whose declared question range covers this question number."""
    return [m["id"] for m in materials
            if m["range"] and m["range"][0] <= number <= m["range"][1]]


def image_refs(text):
    """Image srcs in order of appearance, with their flag attribute if present."""
    refs = []
    for tag in re.findall(r"<img\b[^>]*>", text, re.I):
        src = IMG_SRC_RE.search(tag)
        flag = IMG_FLAG_RE.search(tag)
        refs.append({
            "src": src.group(1) if src else "",
            "flag": flag.group(1) if flag else "",
        })
    return refs


def is_formula_ref(ref):
    """A formula (typeset) reference rather than a figure."""
    return ref.get("flag") == "tex" or "/公式图/" in ref.get("src", "")


def resolve_image_ref(repo_root, paper_rel_path, src):
    """Resolve a paper-relative image reference to a file and digest it."""
    import hashlib
    import posixpath
    if not src or re.match(r"^[a-z][a-z0-9+.-]*:", src, re.I):
        return {"src": src, "kind": "remote-or-empty", "exists": False}
    decoded = src.replace("%20", " ")
    base = posixpath.dirname(paper_rel_path.replace("\\", "/"))
    rel = posixpath.normpath(posixpath.join(base, decoded))
    abs_path = os.path.join(repo_root, rel.replace("/", os.sep))
    info = {"src": src, "resolved": rel, "exists": os.path.isfile(abs_path)}
    if info["exists"]:
        with open(abs_path, "rb") as fh:
            data = fh.read()
        info["bytes"] = len(data)
        info["sha256"] = hashlib.sha256(data).hexdigest()
        info["kind"] = "formula" if "/公式图/" in rel else "figure"
    else:
        info["kind"] = "missing"
    return info


def parse_paper(markdown):
    """Parse this repository's 行测 markdown into questions and materials.

    Mirrors tools/fenbi/src/align.mjs `parseRepositoryPaper` so an offline audit
    and the capture-time aligner agree on what the library contains: question
    bodies stop at the next heading of any level, options are `- **A**.` lines,
    materials declare a question range, and answers live in <details> blocks
    under an `答案与解析` heading.
    """
    answer_start = -1
    for m in re.finditer(r"(?m)^#{1,6}\s+答案与解析\s*$", markdown):
        answer_start = m.start()
        break
    body = markdown if answer_start < 0 else markdown[:answer_start]
    answers = "" if answer_start < 0 else markdown[answer_start:]

    headings = [(m.start(), m.end(), m.group(1))
                for m in re.finditer(r"(?m)^#{1,6}\s+(.+)$", body)]
    questions, materials = {}, []
    for i, (start, end, title) in enumerate(headings):
        chunk = body[end: headings[i + 1][0] if i + 1 < len(headings) else len(body)].strip()
        material = re.match(r"^材料\s*(\d+)", title)
        if material:
            rng = MATERIAL_RANGE_RE.search(title)
            materials.append({
                "id": material.group(1),
                "range": [int(rng.group(1)), int(rng.group(2))] if rng else None,
                "text": chunk,
            })
            continue
        question = re.match(r"^第\s*(\d+)\s*题", title)
        if not question:
            continue
        number = int(question.group(1))
        option_spans = list(re.finditer(r"(?m)^\s*-\s*\*\*([A-Z])\*\*\s*[.．、:]?\s*", chunk))
        options = []
        for j, m in enumerate(option_spans):
            stop = option_spans[j + 1].start() if j + 1 < len(option_spans) else len(chunk)
            options.append({"label": m.group(1),
                            "text": chunk[m.end():stop].strip()})
        stem = chunk[:option_spans[0].start()].strip() if option_spans else chunk
        qid = re.search(r"\bqid\s+([\w-]+)", title)
        questions[number] = {
            "qid": qid.group(1) if qid else "",
            "number": number,
            "heading": title,
            "stem": stem,
            "options": options,
        }

    for number, question in questions.items():
        question["material_ids"] = [m["id"] for m in materials
                                    if m["range"] and m["range"][0] <= number <= m["range"][1]]

    for block in re.finditer(r"(?is)<details\b[^>]*>(.*?)</details>", answers):
        content = block.group(1)
        summary = re.search(r"(?is)<summary[^>]*>\s*第\s*(\d+)\s*题", content)
        if not summary:
            continue
        number = int(summary.group(1))
        if number not in questions:
            continue
        rest = content[summary.end():]
        answer = re.search(r"\*\*答案\*\*\s*[：:]\s*([^\r\n]+)", rest)
        questions[number]["answer"] = answer.group(1).strip() if answer else ""
        explanation = re.sub(r"\*\*答案\*\*\s*[：:]\s*[^\r\n]+", "", rest)
        questions[number]["explanation"] = explanation.strip()

    for question in questions.values():
        question.setdefault("answer", "")
        question.setdefault("explanation", "")
    return {"questions": questions, "materials": materials}
