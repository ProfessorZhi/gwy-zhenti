"""Static / semantic layout checker for published 粉笔 papers.

Read-only. One paper at a time, line-oriented; no global state beyond the
git tree index of image paths.

The corpus has four layout templates (measured on main efea3003):

  fenbi-new       ## 题目 + ### 第 N 题 + per-question <details>   (1826)
  fenbi-legacy    ## 参考作答与范文导读, no <details>              (13)
  qid-h2          ## 第 N 题　<sub>qid …> per question             (2)
  mixed-level     12 papers where 资料分析 questions are ### under
                  a ## 材料 heading while the rest are ##          (9)

Rules are template-aware: a style that is consistent across a paper is a
variant, not a defect; a style that changes *within* one paper is a layout
problem.  Nothing here rewrites text; the fixer only touches whitespace.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #

SEV_ERROR = "error"
SEV_WARN = "warn"
SEV_REVIEW = "review"
SEV_INFO = "info"

REQUIRED_FIELDS = ("考试", "地区", "年份", "科目", "卷型", "真题性质")
SUBJECTS = ("行测", "申论")

TAG_BALANCE = (
    "b", "i", "u", "em", "strong", "sub", "sup", "span", "div", "p",
    "details", "summary", "table", "thead", "tbody", "tr", "td", "th",
    "ul", "ol", "li", "blockquote", "article", "section", "font", "small",
)

PLACEHOLDER_RE = re.compile(
    r"全力以赴征集|正在搜集中|本题暂无收集到|暂无收集到|网友未回忆起|题目缺失|尚未收录|"
    r"暂未收录|来源缺题|题位保留|缺原题"
)

IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)>]+?)>?\s*\)")
IMG_TAG_RE = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.I)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
Q_HEADING_RE = re.compile(r"^#{2,4}\s*第\s*(\d+)\s*题\s*(.*)$")
MAT_HEADING_RE = re.compile(r"^#{2,3}\s*(?:给定)?材料\s*(\d+)\s*(?:[（(].*)?$")
DETAILS_RE = re.compile(r"<details\b[^>]*>(.*?)</details>", re.S | re.I)
DETAILS_OPEN_RE = re.compile(r"<details\b[^>]*>", re.I)
DETAILS_CLOSE_RE = re.compile(r"</details\s*>", re.I)
SUMMARY_RE = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.S | re.I)
SUMMARY_NUM_RE = re.compile(r"第\s*(\d+)\s*题")
OPT_PLAIN_RE = re.compile(r"^([A-H])\s*[.．]\s*(.*)$")
OPT_DUNHAO_RE = re.compile(r"^([A-H])\s*、\s*(.*)$")
OPT_BULLET_RE = re.compile(r"^[-*+]\s+\*\*([A-H])\*\*\s*[.、．]?\s*(.*)$")
OPT_BOLD_RE = re.compile(r"^\*\*([A-H])\*\*\s*[.、．]\s*(.*)$")
MATREF_RE = re.compile(r"^关联材料\s*[：:]\s*(.+)$")
MATREF_NUM_RE = re.compile(r"材料\s*(\d+)")
STEM_MAT_RE = re.compile(r"资料\s*(\d+)(?:\s*[-—~～至]\s*(\d+))?")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SLUG_STRIP_RE = re.compile(r"[^\w一-鿿\- ]+", re.UNICODE)

ENTITY_NAMES = {
    "amp", "lt", "gt", "quot", "apos", "nbsp", "hellip", "mdash", "ndash",
    "ldquo", "rdquo", "lsquo", "rsquo", "copy", "reg", "trade", "times",
    "divide", "deg", "plusmn", "sup2", "sup3", "frac12", "frac14", "frac34",
    "laquo", "raquo", "middot", "bull", "prime", "rarr", "larr",
}


@dataclass
class Finding:
    code: str
    severity: str
    line: int
    message: str
    evidence: str = ""
    fixable: bool = False

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence[:200],
            "fixable": self.fixable,
        }


@dataclass
class PaperReport:
    path: str
    sha256: str
    bytes: int
    subject: str
    template: str
    questions: int = 0
    materials: int = 0
    details: int = 0
    images: int = 0
    tables: int = 0
    placeholders: int = 0
    legacy_answers: bool = False
    findings: list[Finding] = field(default_factory=list)

    def counts(self) -> dict:
        out = {SEV_ERROR: 0, SEV_WARN: 0, SEV_REVIEW: 0, SEV_INFO: 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> dict:
        c = self.counts()
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "subject": self.subject,
            "template": self.template,
            "stats": {
                "questions": self.questions,
                "materials": self.materials,
                "details": self.details,
                "images": self.images,
                "tables": self.tables,
                "placeholders": self.placeholders,
                "legacy_answers": self.legacy_answers,
            },
            "counts": c,
            "issues": [f.to_dict() for f in self.findings],
        }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def slugify(text: str) -> str:
    """Approximate GitHub heading slug (enough for anchor checks)."""
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    text = re.sub(r"`", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = SLUG_STRIP_RE.sub("", text)
    return text.replace(" ", "-")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def parse_frontmatter(lines: list[str]) -> tuple[dict, int, list[str]]:
    """Return (fields, body_start_line_index, problems)."""
    problems: list[str] = []
    if not lines or lines[0].strip() != "---":
        return {}, 0, ["missing"]
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, 0, ["unclosed"]
    fields: dict[str, str] = {}
    dupes: list[str] = []
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            problems.append(f"bad-line:{line[:40]}")
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if k in fields:
            dupes.append(k)
        if v.startswith('"') and v.endswith('"') and len(v) >= 2:
            try:
                v = json.loads(v)
            except Exception:
                problems.append(f"bad-quote:{k}")
        elif v.startswith("[") and v.endswith("]"):
            try:
                v = json.loads(v)
            except Exception:
                problems.append(f"bad-array:{k}")
        fields[k] = v
    if dupes:
        problems.append("duplicate:" + ",".join(sorted(set(dupes))))
    return fields, end + 1, problems


def mask_code(lines: list[str]) -> list[bool]:
    """True where a line is inside a fenced code block (fences included)."""
    mask = [False] * len(lines)
    inside = False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            mask[i] = True
            inside = not inside
            continue
        mask[i] = inside
    return mask


def strip_inline_code(text: str) -> str:
    return re.sub(r"`[^`]*`", "", text)


# --------------------------------------------------------------------------- #
# checker
# --------------------------------------------------------------------------- #


def check_paper(rel_path: str, blob: bytes, tree_paths: set[str]) -> PaperReport:
    rep = PaperReport(
        path=rel_path,
        sha256=sha256_bytes(blob),
        bytes=len(blob),
        subject="",
        template="unknown",
    )
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        rep.findings.append(Finding("ES000", SEV_ERROR, 0, f"文件不是 UTF-8：{exc}", "", False))
        return rep

    if "\r\n" in text:
        rep.findings.append(Finding("LX008", SEV_WARN, 0, "CRLF 换行，GitHub 渲染会出现多余空行", "", True))
    if not text.endswith("\n"):
        rep.findings.append(Finding("LX007", SEV_WARN, 0, "文件末尾缺少换行", "", True))

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    report_lines = lines
    n = len(lines)
    in_code = mask_code(lines)

    # ---- frontmatter ------------------------------------------------------
    fields, body_start, fm_problems = parse_frontmatter(lines)
    for p in fm_problems:
        if p == "missing":
            rep.findings.append(Finding("FM001", SEV_ERROR, 1, "缺少 frontmatter（--- 包裹的元数据块）", "", False))
        elif p == "unclosed":
            rep.findings.append(Finding("FM002", SEV_ERROR, 1, "frontmatter 没有闭合的 ---", "", False))
        elif p.startswith("duplicate:"):
            rep.findings.append(Finding("FM007", SEV_WARN, 1, f"frontmatter 重复字段：{p.split(':',1)[1]}", "", True))
        else:
            rep.findings.append(Finding("FM003", SEV_WARN, 1, f"frontmatter 行无法解析：{p}", "", False))
    for key in REQUIRED_FIELDS:
        if key not in fields or str(fields.get(key, "")).strip() == "":
            rep.findings.append(Finding("FM004", SEV_ERROR, 1, f"frontmatter 缺字段或为空：{key}", "", False))
    subject = str(fields.get("科目", "")).strip()
    rep.subject = subject
    if subject and subject not in SUBJECTS:
        rep.findings.append(Finding("FM005", SEV_ERROR, 1, f"科目取值非法：{subject}", subject, False))
    year = str(fields.get("年份", "")).strip()
    if year and not re.fullmatch(r"\d{4}", year):
        rep.findings.append(Finding("FM006", SEV_WARN, 1, f"年份不是四位数字：{year}", year, False))
    src = str(fields.get("来源", ""))
    if "fenbi" in src and not str(fields.get("源试卷ID", "")).strip():
        rep.findings.append(Finding("FM009", SEV_WARN, 1, "粉笔来源卷缺少 源试卷ID", src[:60], False))

    # ---- headings ---------------------------------------------------------
    headings: list[tuple[int, str, int]] = []  # level, text, line
    for i in range(body_start, n):
        if in_code[i]:
            continue
        m = HEADING_RE.match(lines[i])
        if m:
            headings.append((len(m.group(1)), m.group(2), i + 1))
    h1 = [h for h in headings if h[0] == 1]
    if len(h1) == 0:
        rep.findings.append(Finding("HD001", SEV_ERROR, 1, "缺少一级标题（# 卷名）", "", False))
    elif len(h1) > 1:
        rep.findings.append(
            Finding("HD002", SEV_ERROR, h1[1][2], f"出现 {len(h1)} 个一级标题：{', '.join(h[1][:20] for h in h1[:4])}", "", False)
        )
    for prev, cur in zip(headings, headings[1:]):
        if cur[0] - prev[0] > 1:
            rep.findings.append(
                Finding("HD003", SEV_ERROR, cur[2], f"标题层级跳跃：H{prev[0]} → H{cur[0]}（{cur[1][:30]}）", "", False)
            )
            break

    # question headings (H2..H4)
    q_heads: list[tuple[int, int, int, str]] = []  # level, num, line, extra
    mat_heads: list[tuple[int, int, int]] = []  # level, num, line
    for level, htext, line_no in headings:
        mq = Q_HEADING_RE.match("#" * level + " " + htext)
        if mq:
            q_heads.append((level, int(mq.group(1)), line_no, mq.group(2)))
            continue
        mm = MAT_HEADING_RE.match("#" * level + " " + htext)
        if mm and line_no > body_start:
            mat_heads.append((level, int(mm.group(1)), line_no))

    rep.questions = len({q[1] for q in q_heads})
    rep.materials = len({m[1] for m in mat_heads})

    levels = {q[0] for q in q_heads}
    n_h2q = sum(1 for q in q_heads if q[0] == 2)
    n_h3q = sum(1 for q in q_heads if q[0] == 3)
    if n_h2q and not n_h3q:
        rep.template = "qid-h2"
    elif n_h2q and n_h3q:
        rep.template = "mixed-level"
    else:
        rep.template = "fenbi"
    if levels and len(levels) > 1:
        rep.findings.append(
            Finding(
                "HD008",
                SEV_REVIEW,
                0,
                f"同一卷内题目标题层级不一致：H{min(levels)} 与 H{max(levels)} 混用",
                f"{len(q_heads)} 个题目标题",
                False,
            )
        )

    nums = [q[1] for q in q_heads]
    dup = sorted({x for x in nums if nums.count(x) > 1})
    if dup:
        rep.findings.append(Finding("HD004", SEV_ERROR, 0, f"题号重复：{', '.join(map(str, dup[:10]))}", "", False))
    if nums:
        uniq = sorted(set(nums))
        gaps = [x for x in range(1, uniq[-1] + 1) if x not in set(uniq)]
        if gaps:
            rep.findings.append(
                Finding("HD005", SEV_WARN, 0, f"题号不连续（缺 {len(gaps)} 个）", ",".join(map(str, gaps[:15])), False)
            )
        if uniq[0] != 1:
            rep.findings.append(Finding("HD006", SEV_WARN, 0, f"题号不是从 1 开始（首个为 {uniq[0]}）", "", False))

    mat_nums = [m[1] for m in mat_heads]
    mdup = sorted({x for x in mat_nums if mat_nums.count(x) > 1})
    if mdup:
        rep.findings.append(Finding("MT001", SEV_ERROR, 0, f"材料标题重复：材料 {', '.join(map(str, mdup[:10]))}", "", False))
    if mat_nums:
        mu = sorted(set(mat_nums))
        mgaps = [x for x in range(1, mu[-1] + 1) if x not in set(mu)]
        if mgaps:
            rep.findings.append(Finding("MT002", SEV_WARN, 0, f"材料编号不连续", ",".join(map(str, mgaps[:15])), False))
    if len({m[0] for m in mat_heads}) > 1:
        rep.findings.append(Finding("MT007", SEV_REVIEW, 0, "同一卷内材料标题层级不一致（H2/H3 混用）", "", False))

    for level, htext, line_no in headings:
        if htext.endswith(("：", ":", "。", "；")) and not Q_HEADING_RE.match("#" * level + " " + htext):
            rep.findings.append(Finding("HD010", SEV_WARN, line_no, f"标题以标点结尾：{htext[:30]}", "", True))
        if not htext.strip():
            rep.findings.append(Finding("HD011", SEV_ERROR, line_no, "空标题", "", False))

    # legacy answer layouts
    legacy_sections = [h for h in headings if h[1] in ("参考作答与范文导读", "未自动迁移的旧版答案", "答案与解析")]
    rep.legacy_answers = bool(legacy_sections)

    # ---- details / summary ------------------------------------------------
    details_blocks = []
    for m in DETAILS_RE.finditer(text):
        start_line = text.count("\n", 0, m.start()) + 1
        inner = m.group(1)
        sm = SUMMARY_RE.search(inner)
        num = None
        if sm:
            nm = SUMMARY_NUM_RE.search(sm.group(1))
            if nm:
                num = int(nm.group(1))
        details_blocks.append((start_line, num, m.group(0)))
    rep.details = len(details_blocks)

    opens = len(DETAILS_OPEN_RE.findall(text))
    closes = len(DETAILS_CLOSE_RE.findall(text))
    if opens != closes:
        rep.findings.append(Finding("DT002", SEV_ERROR, 0, f"<details> 与 </details> 数量不等：{opens}/{closes}", "", False))

    seen_details: dict[int, int] = {}
    prev_q_line = None
    for line_no, num, block in details_blocks:
        if num is None:
            rep.findings.append(Finding("DT003", SEV_WARN, line_no, "<details> 的 <summary> 没有「第 N 题」", block[:60], False))
            continue
        if num in seen_details:
            rep.findings.append(Finding("DT005", SEV_WARN, line_no, f"第 {num} 题有多个答案折叠块（前一个在 {seen_details[num]} 行）", "", False))
        seen_details[num] = line_no
        # nearest question heading above
        above = [q for q in q_heads if q[2] < line_no]
        if above:
            nearest = above[-1]
            if nearest[1] != num:
                rep.findings.append(
                    Finding(
                        "DT004",
                        SEV_ERROR,
                        line_no,
                        f"折叠块题号与所在题目不一致：块为第 {num} 题，最近题目标题是第 {nearest[1]} 题（第 {nearest[2]} 行）",
                        "",
                        False,
                    )
                )
        body = SUMMARY_RE.sub("", block)
        body = re.sub(r"</?details[^>]*>", "", body).strip()
        if not body:
            rep.findings.append(Finding("DT007", SEV_WARN, line_no, f"第 {num} 题折叠块内容为空", "", False))
        if re.search(r"\*\*解析\*\*\s*\n\s*\*\*解析\*\*", block):
            rep.findings.append(Finding("DT008", SEV_WARN, line_no, f"第 {num} 题出现重复的空解析标题", "", False))


    overview = ""
    ov_s, ov_e = text.find("<!-- gwy:overview:start -->"), text.find("<!-- gwy:overview:end -->")
    if ov_s != -1 and ov_e > ov_s:
        overview = text[ov_s:ov_e]
    claims_fold = "答案随题折叠" in overview and "不含答案" not in text and "未收录答案" not in text
    if q_heads and not rep.legacy_answers and rep.template == "fenbi" and claims_fold:
        missing = sorted({q[1] for q in q_heads} - set(seen_details))
        if missing:
            rep.findings.append(
                Finding("DT006", SEV_REVIEW, 0, f"{len(missing)} 题没有答案折叠块（摘要声明答案随题折叠）", ",".join(map(str, missing[:15])), False)
            )

    # details style mix (inline `<details><summary>` vs block)
    inline_style = len(re.findall(r"<details[^>]*>[ \t]*<summary", text))
    block_style = len(re.findall(r"<details[^>]*>[ \t]*\n[ \t]*<summary", text))
    if inline_style and block_style:
        rep.findings.append(
            Finding("DT011", SEV_REVIEW, 0, f"折叠块两种写法混用（同行 {inline_style} / 换行 {block_style}）", "", False)
        )

    # ---- options ----------------------------------------------------------
    opt_styles: set[str] = set()
    op_missing: list[tuple[int, str]] = []
    op_with = 0
    for level, num, line_no, extra in q_heads:
        end = _block_end(lines, line_no, in_code)
        block = lines[line_no - 1 : end]
        det_at = None
        for idx, ln in enumerate(block):
            if DETAILS_OPEN_RE.search(ln):
                det_at = idx
                break
        pre = block[: det_at if det_at is not None else len(block)]
        pre_text = "\n".join(pre)

        # Option lines.  Two traps in this corpus:
        #   * a stem may start with "A、B两地…" (looks like option A);
        #   * options may be separated by blank lines and have continuation lines.
        # Strategy: group option-like lines that are separated only by blank
        # lines, take the last group with >=2 members, and validate that group.
        cands: list[tuple[int, str, str, str]] = []  # idx, label, style, raw
        for idx, ln in enumerate(pre):
            stripped = ln.strip()
            m = OPT_BULLET_RE.match(stripped)
            if m:
                cands.append((idx, m.group(1), "bullet-bold", ln))
                continue
            m = OPT_BOLD_RE.match(stripped)
            if m:
                cands.append((idx, m.group(1), "bold", ln))
                continue
            m = OPT_PLAIN_RE.match(stripped)
            if m:
                cands.append((idx, m.group(1), "plain", ln))
                continue
        if len(cands) < 2:
            # "A、…" is usually prose ("A、B两地…"); accept it as an option style
            # only when the block has no dot-style options at all.
            alt: list[tuple[int, str, str, str]] = []
            for idx, ln in enumerate(pre):
                m = OPT_DUNHAO_RE.match(ln.strip())
                if m:
                    alt.append((idx, m.group(1), "dunhao", ln))
            if len(alt) >= 3:
                cands = alt
        # inline concatenation is checked on every line, before grouping
        for idx, ln in enumerate(pre):
            m = re.match(r"^([A-H])\s*[.、．]\s*", ln)
            if m:
                nxt = chr(ord(m.group(1)) + 1)
                if re.search(r"(?<=\s)" + nxt + r"\s*[.、．]\s*\S", ln):
                    parts = re.findall(r"[A-H]\s*[.、．]\s*([^A-H\s][^A-H]{0,60}?)(?=\s+[A-H]\s*[.、．]|$)", ln)
                    legend = bool(parts) and all(len(part.strip()) <= 2 for part in parts)
                    rep.findings.append(
                        Finding(
                            "OP001",
                            SEV_REVIEW if legend else SEV_ERROR,
                            line_no + idx,
                            f"第 {num} 题多个选项写在同一行" + ("（单字符图例，可能属表格）" if legend else ""),
                            ln[:80],
                            False,
                        )
                    )
        # All option-like lines in the question block belong to one group;
        # captions/images between them are continuations, not separators.
        group = cands

        # Longest consecutive run A,B,C… inside the group.  Leading items that
        # do not fit are stem artefacts ("A、B两地…").
        best_start, best_seq = 0, []
        for i in range(len(group)):
            if group[i][1] != "A":
                continue
            seq = [group[i]]
            expect = "B"
            for c in group[i + 1 :]:
                if c[1] == expect:
                    seq.append(c)
                    expect = chr(ord(expect) + 1)
                else:
                    break
            if len(seq) > len(best_seq):
                best_start, best_seq = i, seq
        run = best_seq
        after = group[best_start + len(best_seq) :]
        labels = [c[1] for c in run]
        style_set = {c[2] for c in run}
        if style_set:
            opt_styles |= style_set
        if len(run) >= 2:
            op_with += 1
            if after:
                dup = {c[1] for c in after} & set(labels)
                if dup:
                    rep.findings.append(Finding("OP003", SEV_ERROR, line_no, f"第 {num} 题选项标签重复：{''.join(labels + [c[1] for c in after])}", ",".join(labels), False))
                else:
                    rep.findings.append(
                        Finding("OP002", SEV_ERROR, line_no, f"第 {num} 题选项标签不连续：{''.join(labels + [c[1] for c in after])}", ",".join(labels), False)
                    )
            for c in run:
                if c[3][:1].isspace() and c[3].strip():
                    rep.findings.append(Finding("OP004", SEV_WARN, line_no + c[0], f"第 {num} 题选项有缩进，会渲染成嵌套列表", c[3][:60], True))
                    break
        elif group:
            all_labels = [c[1] for c in group]
            if len(set(all_labels)) != len(all_labels):
                rep.findings.append(Finding("OP003", SEV_ERROR, line_no, f"第 {num} 题选项标签重复：{''.join(all_labels)}", ",".join(all_labels), False))
            else:
                rep.findings.append(Finding("OP006", SEV_REVIEW, line_no, f"第 {num} 题只识别到 {len(all_labels)} 个选项", "", False))
        else:
            # no grouped run: report indented option-looking lines separately
            for idx, ln in enumerate(pre):
                if re.match(r"^\s+[A-H][.、．]\s+\S", ln):
                    rep.findings.append(Finding("OP004", SEV_WARN, line_no + idx, f"第 {num} 题选项有缩进，会渲染成嵌套列表", ln[:60], True))
                    break
            table_options = re.findall(r"^\|\s*([A-H])\s*[.、．]", pre_text, re.M)
            if table_options:
                # options rendered as table rows (e.g. 国考 2008 q125)
                opt_styles.add("table")
                op_with += 1
            elif rep.subject == "行测":
                stem_text = pre_text.strip()
                if PLACEHOLDER_RE.search(stem_text):
                    pass  # 占位题，不是排版问题
                else:
                    # 判断题：以句号结尾的陈述，或以「（　）」收尾的填空式判断
                    blank_end = bool(re.search(r"（\s*）\s*[。.]?\s*$", stem_text))
                    statement_like = blank_end or (
                        len(stem_text) < 100
                        and stem_text.endswith(("。", "．", "."))
                        and not re.search(r"[？?]|下列|以下|哪|正确的是|错误的是", stem_text)
                    )
                    if not statement_like:
                        op_missing.append((line_no, f"第 {num} 题没有识别到选项行：{stem_text[:50]}"))
    # Only complain about missing options when the paper is normally option-based:
    # 判断题 / 资料分析 sections legitimately have none.
    total_q = op_with + len(op_missing)
    if total_q and op_with / total_q >= 0.5:
        for line_no, msg in op_missing:
            rep.findings.append(Finding("OP007", SEV_REVIEW, line_no, msg, "", False))
    elif op_missing:
        rep.findings.append(
            Finding("OP007", SEV_REVIEW, 0, f"全卷 {len(op_missing)}/{total_q} 题没有 A-D 选项行（可能整卷是判断题/填空型）", "", False)
        )

    if len(opt_styles) > 1:
        rep.findings.append(Finding("OP005", SEV_REVIEW, 0, f"同一卷内选项写法混用：{', '.join(sorted(opt_styles))}", "", False))

    # ---- materials / references ------------------------------------------
    mat_set = {m[1] for m in mat_heads}
    paper_has_matref = any(MATREF_RE.match(ln.strip()) for ln in lines[body_start:])
    for level, num, line_no, extra in q_heads:
        end = _block_end(lines, line_no, in_code)
        block = "\n".join(lines[line_no - 1 : end])
        det = DETAILS_OPEN_RE.search(block)
        pre = block[: det.start()] if det else block
        mref = None
        for ln_idx, ln in enumerate(lines[line_no - 1 : end]):
            mm = MATREF_RE.match(ln.strip())
            if mm:
                mref = mm.group(1)
                if ln_idx > 0 and lines[line_no - 1 + ln_idx - 1].strip() != "":
                    rep.findings.append(Finding("MT006", SEV_WARN, line_no + ln_idx, f"第 {num} 题「关联材料」前缺空行", "", True))
                break
        refs = [int(x) for x in MATREF_NUM_RE.findall(mref)] if mref else []
        if refs:
            bad = [r for r in refs if r not in mat_set]
            if bad:
                rep.findings.append(
                    Finding("MT003", SEV_ERROR, line_no, f"第 {num} 题关联了不存在的材料：{bad}", f"本卷材料 {sorted(mat_set)}", False)
                )
        else:
            mentioned: list[int] = []
            for mm in STEM_MAT_RE.finditer(pre):
                lo = int(mm.group(1))
                hi = int(mm.group(2)) if mm.group(2) else lo
                if 0 < hi - lo <= 30:
                    mentioned.extend(range(lo, hi + 1))
                else:
                    mentioned.append(lo)
            mentioned = sorted(set(mentioned))
            if mentioned and mat_set and paper_has_matref:
                rep.findings.append(
                    Finding(
                        "MT004",
                        SEV_WARN,
                        line_no,
                        f"第 {num} 题题干提到资料 {mentioned}，但没有「关联材料」行",
                        pre[:60].replace("\n", " "),
                        False,
                    )
                )
        if mref is not None and not re.fullmatch(r"[材料\d、,，\s]+", mref):
            rep.findings.append(Finding("MT005", SEV_WARN, line_no, f"第 {num} 题关联材料写法异常：{mref[:40]}", "", False))

    if mat_set and not paper_has_matref and rep.subject == "申论":
        rep.findings.append(
            Finding("MT004", SEV_REVIEW, 0, "全卷没有「关联材料」导航行（题干里有资料号时不便于跳转）", f"{len(mat_set)} 个材料", False)
        )

    # empty material body
    for level, num, line_no in mat_heads:
        end = _block_end(lines, line_no, in_code)
        body = [ln for ln in lines[line_no:end] if ln.strip()]
        if not body:
            rep.findings.append(Finding("MT008", SEV_WARN, line_no, f"材料 {num} 正文为空", "", False))

    # ---- lists / tables / escaping ---------------------------------------
    _check_lists(rep, lines, in_code, body_start)
    rep.tables = _check_tables(rep, lines, in_code, body_start)
    _check_escaping(rep, lines, in_code, body_start)

    # ---- lines ------------------------------------------------------------
    blank_run = 0
    for i in range(body_start, n):
        line = lines[i]
        if in_code[i]:
            continue
        if not line.strip():
            blank_run += 1
            if blank_run == 3:
                rep.findings.append(Finding("LX003", SEV_WARN, i + 1, "连续 3 个以上空行", "", True))
            continue
        blank_run = 0
        if len(line) > 2000:
            rep.findings.append(
                Finding("LX001", SEV_REVIEW, i + 1, f"超长行（{len(line)} 字符），手机上会横向溢出/折断", line[:60], False)
            )
        if line != line.rstrip(" \t"):
            rep.findings.append(Finding("LX002", SEV_WARN, i + 1, "行尾有多余空格", "", True))
        prev = lines[i - 1].strip() if i > 0 else ""
        meta_prev = prev.startswith("<!--") or prev.startswith("<a ") or prev.startswith("<a id")
        if line.startswith("#") and prev and not meta_prev:
            rep.findings.append(Finding("LX004", SEV_REVIEW, i + 1, "标题紧贴上一段（仍能渲染成标题，但风格不统一）", line[:40], True))
        if DETAILS_OPEN_RE.search(line) and prev and not DETAILS_OPEN_RE.search(lines[i - 1]) and not meta_prev:
            rep.findings.append(Finding("LX005", SEV_WARN, i + 1, "<details> 前缺少空行", line[:40], True))
        if DETAILS_CLOSE_RE.search(line) and i + 1 < n and lines[i + 1].strip():
            rep.findings.append(Finding("LX006", SEV_WARN, i + 1, "</details> 后缺少空行", line[:40], True))

    # ---- images -----------------------------------------------------------
    outside = []
    for line_no, line in enumerate(lines, start=1):
        if in_code[line_no - 1] and not (IMG_RE.search(line) or IMG_TAG_RE.search(line)):
            continue
        for m in IMG_RE.finditer(line):
            outside.append((line_no, m.group(1)))
        for m in IMG_TAG_RE.finditer(line):
            outside.append((line_no, m.group(1)))
    rep.images = len(outside)
    seen_img: dict[str, int] = {}
    reported_img: set[str] = set()
    for line_no, ref in outside:
        first = seen_img.get(ref)
        if first is not None and first != line_no and ref not in reported_img:
            rep.findings.append(Finding("IM004", SEV_REVIEW, line_no, f"同一图片重复引用（也在第 {first} 行）", ref[-40:], False))
            reported_img.add(ref)
        seen_img.setdefault(ref, line_no)
        if re.match(r"^[a-z]+://", ref):
            rep.findings.append(Finding("IM002", SEV_WARN, line_no, "图片使用远程 URL，离线/断网时不显示", ref[:80], False))
            continue
        if " " in ref or "\\" in ref:
            rep.findings.append(Finding("IM003", SEV_WARN, line_no, "图片路径含空格或反斜杠，Markdown 可能解析失败", ref[:80], False))
            continue
        norm = os.path.normpath(os.path.join(os.path.dirname(rel_path), ref))
        if tree_paths and norm not in tree_paths:
            rep.findings.append(Finding("IM001", SEV_ERROR, line_no, "图片引用的文件不在仓库里", norm[:120], False))

    # ---- navigation -------------------------------------------------------
    _check_navigation(rep, text, headings, q_heads, outside, lines)

    # ---- placeholders -----------------------------------------------------
    ph = len(PLACEHOLDER_RE.findall(text))
    rep.placeholders = ph
    if ph:
        rep.findings.append(Finding("PH001", SEV_INFO, 0, f"{ph} 处源征集占位（不是排版问题）", "", False))

    return rep


def _block_end(lines: list[str], start_line: int, in_code: list[bool]) -> int:
    """Index (exclusive) of the next heading at H1/H2/H3 after ``start_line``."""
    for i in range(start_line, len(lines)):
        if in_code[i]:
            continue
        m = HEADING_RE.match(lines[i])
        if m and len(m.group(1)) <= 3:
            return i
    return len(lines)


def _check_lists(rep: PaperReport, lines: list[str], in_code: list[bool], body_start: int) -> None:
    markers: set[str] = set()
    list_open = False
    pending_blank = False
    for i in range(body_start, len(lines)):
        if in_code[i]:
            continue
        line = lines[i]
        if not line.strip():
            pending_blank = True
            continue
        if "\t" in line:
            rep.findings.append(Finding("LS001", SEV_ERROR, i + 1, "使用制表符缩进，GitHub 会渲染成代码块", line[:50], True))
        is_item = bool(re.match(r"^(\s*)([-*+])\s", line))
        if is_item:
            markers.add(re.match(r"^(\s*)([-*+])", line).group(2))
            # CommonMark lets a bullet list interrupt a paragraph, so a missing
            # blank line before an item is not a rendering defect; not flagged.
            list_open = True
            pending_blank = False
            continue
        # not a list item
        # A leading "-"/"+" is usually maths or a quoted "互联网+" phrase, not a
        # list marker; measured on this corpus every hit was a false positive,
        # so LS002 is deliberately not emitted.
        if pending_blank:
            list_open = False
        pending_blank = False
    if len(markers) > 1:
        rep.findings.append(Finding("LS003", SEV_REVIEW, 0, f"同一卷内列表符号混用：{', '.join(sorted(markers))}", "", False))


def _check_tables(rep: PaperReport, lines: list[str], in_code: list[bool], body_start: int) -> int:
    tables = 0
    i = body_start
    n = len(lines)
    while i < n:
        if in_code[i] or not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        start = i
        while i < n and not in_code[i] and lines[i].lstrip().startswith("|"):
            i += 1
        block = lines[start:i]
        tables += 1
        if len(block) < 2:
            # a lone "|…|" line is usually maths (|甲-乙|=|丙-丁|), not a table
            pass
        else:
            sep = block[1].strip().strip("|")
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", sep)]
            if not cells or not all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c != ""):
                rep.findings.append(Finding("TB001", SEV_ERROR, start + 2, "表格第二行不是合法的 GFM 分隔行", block[1][:60], False))
            header_cells = [c for c in re.split(r"(?<!\\)\|", block[0].strip().strip("|"))]
            for k, row in enumerate(block[2:], start=2):
                rc = [c for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]
                if len(rc) != len(header_cells):
                    rep.findings.append(
                        Finding(
                            "TB003",
                            SEV_ERROR,
                            start + k + 1,
                            f"表格行列数不一致：表头 {len(header_cells)} 列，本行 {len(rc)} 列",
                            row[:60],
                            False,
                        )
                    )
                    break
            if len(cells) != len(header_cells):
                rep.findings.append(
                    Finding("TB002", SEV_ERROR, start + 2, f"分隔行列数 {len(cells)} ≠ 表头 {len(header_cells)}", block[1][:60], False)
                )
        if start > 0 and lines[start - 1].strip():
            rep.findings.append(Finding("TB004", SEV_WARN, start + 1, "表格前缺少空行", block[0][:40], True))
        if i < n and lines[i].strip():
            rep.findings.append(Finding("TB004", SEV_WARN, i + 1, "表格后缺少空行", lines[i][:40], True))
    return tables


def _check_escaping(rep: PaperReport, lines: list[str], in_code: list[bool], body_start: int) -> None:
    fences = sum(1 for i in range(body_start, len(lines)) if FENCE_RE.match(lines[i]))
    if fences % 2 == 1:
        rep.findings.append(Finding("ES004", SEV_ERROR, 0, "代码围栏 ``` 数量为奇数，后半篇会被当成代码块", f"{fences} 个", False))
    text = "\n".join(lines[body_start:])
    # tag balance for the tags that actually appear
    for tag in TAG_BALANCE:
        op = len(re.findall(r"<" + tag + r"(?=[\s/>])[^<>]*>", text, re.I))
        cl = len(re.findall(r"</" + tag + r"\s*>", text, re.I))
        if op != cl:
            rep.findings.append(
                Finding("ES001", SEV_ERROR, 0, f"<{tag}> 开合不匹配：{op} 开 / {cl} 闭", "", False)
            )
    # malformed tag: <b（ , <angle<![]  (ASCII letter then CJK punctuation, no >)
    for i in range(body_start, len(lines)):
        if in_code[i]:
            continue
        line = lines[i]
        for m in re.finditer(r"<([a-zA-Z]{1,8})([（，。、；：！？【】])", line):
            rep.findings.append(
                Finding(
                    "ES002",
                    SEV_REVIEW,
                    i + 1,
                    f"形如 <{m.group(1)}{m.group(2)}，按 CommonMark 不是标签（会原样显示）；确认是原文还是漏了转义",
                    line[max(0, m.start() - 20) : m.start() + 30],
                    False,
                )
            )
        # invalid entity
        for m in re.finditer(r"&([a-zA-Z]{2,10})(?![a-zA-Z;])", line):
            if m.group(1).lower() in ENTITY_NAMES:
                rep.findings.append(
                    Finding("ES003", SEV_WARN, i + 1, f"疑似残缺实体：&{m.group(1)}（缺分号）", line[max(0, m.start() - 15) : m.start() + 20], True)
                )
        if line.count("`") % 2 == 1:
            rep.findings.append(Finding("ES005", SEV_WARN, i + 1, "行内反引号数量为奇数", line[:50], False))


def _check_navigation(
    rep: PaperReport,
    text: str,
    headings: list[tuple[int, str, int]],
    q_heads: list[tuple[int, int, int, str]],
    images: list[tuple[int, str]],
    lines: list[str],
) -> None:
    start = text.find("<!-- gwy:overview:start -->")
    end = text.find("<!-- gwy:overview:end -->")
    if start == -1 or end == -1 or end < start:
        rep.findings.append(Finding("NV001", SEV_REVIEW, 0, "缺少 overview 摘要块（gwy:overview:start/end）", "", False))
        return
    block = text[start:end]

    slugs = {slugify(h[1]) for _, h, _ in [(0, x[1], x[2]) for x in headings]}
    # headings also include the H1 title
    for _, h, _ in headings:
        slugs.add(slugify(h))
    for m in re.finditer(r"\[[^\]]+\]\(#([^)]+)\)", block):
        target = m.group(1)
        if target not in slugs:
            rep.findings.append(Finding("NV003", SEV_WARN, 0, f"导航链接指向不存在的锚点：#{target}", "", False))

    mq = re.search(r"｜\s*(\d+)\s*题", block)
    if mq:
        declared = int(mq.group(1))
        actual = len({q[1] for q in q_heads})
        if actual and declared != actual:
            rep.findings.append(
                Finding("NV004", SEV_WARN, 0, f"摘要声称 {declared} 题，实际题目标题 {actual} 个", "", False)
            )
    mi = re.search(r"图片\s*(\d+)\s*处", block)
    if mi:
        declared = int(mi.group(1))
        if declared != len(images):
            rep.findings.append(
                Finding("NV005", SEV_WARN, 0, f"摘要声称图片 {declared} 处，实际引用 {len(images)} 处", "", False)
            )
