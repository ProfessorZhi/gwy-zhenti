"""CLI: check every paper in a checked-out repo and write receipts."""

from __future__ import annotations

import argparse
import collections
import json
import os
import resource
import subprocess
import sys
import time

from .checker import PaperReport, SEV_ERROR, SEV_INFO, SEV_REVIEW, SEV_WARN, check_paper

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
PAPER_PREFIX = ("行测-", "申论-")

GATE_MEM_KIB = 12 * 1024 * 1024


def mem_available_kib() -> int:
    with open("/proc/meminfo", encoding="ascii") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    return 0


def psi_some_avg10() -> float:
    import re

    try:
        with open("/proc/pressure/memory", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("some"):
                    m = re.search(r"avg10=([\d.]+)", line)
                    if m:
                        return float(m.group(1))
    except OSError:
        pass
    return 0.0


def load_tree(repo: str) -> set[str]:
    """All image paths in HEAD, so a sparse checkout does not look like a loss."""
    try:
        res = subprocess.run(
            ["git", "-C", repo, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception:
        return set()
    if res.returncode != 0:
        return set()
    return {line for line in res.stdout.splitlines() if line.lower().endswith(IMAGE_EXT)}


def iter_papers(repo: str):
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "图片")]
        for name in sorted(filenames):
            if name.endswith(".md") and name.startswith(PAPER_PREFIX):
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, repo), full


def run(
    repo: str,
    out_dir: str,
    *,
    limit: int | None = None,
    only: str | None = None,
    skip_gate: bool = False,
) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    mem = mem_available_kib()
    psi = psi_some_avg10()
    gate = {"memAvailableKib": mem, "psiSomeAvg10": psi}
    if not skip_gate and (mem < GATE_MEM_KIB or psi >= 1.0):
        report = {"BLOCKED": "resource-gate", **gate}
        with open(os.path.join(out_dir, "blocked.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        return report

    tree = load_tree(repo)
    started = time.time()
    totals = collections.Counter()
    by_code = collections.Counter()
    by_code_sev: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    by_template = collections.Counter()
    subjects = collections.Counter()
    papers = 0
    q_total = 0
    img_total = 0
    tb_total = 0
    ph_total = 0
    worst: list[tuple[int, dict]] = []

    jsonl_path = os.path.join(out_dir, "receipts.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for rel, full in iter_papers(repo):
            if only and only not in rel:
                continue
            with open(full, "rb") as pf:
                blob = pf.read()
            rep: PaperReport = check_paper(rel, blob, tree)
            row = rep.to_dict()
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            papers += 1
            q_total += rep.questions
            img_total += rep.images
            tb_total += rep.tables
            ph_total += rep.placeholders
            by_template[rep.template] += 1
            subjects[rep.subject or "?"] += 1
            c = row["counts"]
            for sev in (SEV_ERROR, SEV_WARN, SEV_REVIEW, SEV_INFO):
                totals[sev] += c.get(sev, 0)
            for issue in rep.findings:
                by_code[issue.code] += 1
                by_code_sev[issue.code][issue.severity] += 1
            weight = c.get(SEV_ERROR, 0) * 10 + c.get(SEV_WARN, 0) * 3 + c.get(SEV_REVIEW, 0)
            if weight:
                worst.append((weight, row))
            if limit and papers >= limit:
                break

    elapsed = time.time() - started
    worst.sort(key=lambda x: -x[0])
    summary = {
        "repo": repo,
        "papers": papers,
        "questions": q_total,
        "images": img_total,
        "tables": tb_total,
        "placeholders": ph_total,
        "elapsed_s": round(elapsed, 2),
        "papers_per_s": round(papers / elapsed, 2) if elapsed else 0,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "gate": gate,
        "severity_totals": dict(totals),
        "by_template": dict(by_template),
        "by_subject": dict(subjects),
        "by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
        "by_code_severity": {k: dict(v) for k, v in sorted(by_code_sev.items(), key=lambda kv: -sum(kv[1].values()))},
        "receipts": jsonl_path,
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    write_summary_md(summary, out_dir)
    write_highrisk(worst, out_dir, top=40)
    return summary


def write_summary_md(summary: dict, out_dir: str) -> None:
    lines = [
        "# 全量排版检查 — 运行摘要",
        "",
        f"- 仓库：`{summary['repo']}`",
        f"- 卷数：**{summary['papers']}**，题目标题 {summary['questions']} 个，表格 {summary['tables']} 个，图片引用 {summary['images']} 处",
        f"- 耗时 {summary['elapsed_s']} s（{summary['papers_per_s']} 卷/秒），峰值 RSS {summary['max_rss_kib']} KiB",
        f"- 资源门：MemAvailable {summary['gate']['memAvailableKib']} KiB，PSI some avg10 {summary['gate']['psiSomeAvg10']}",
        "",
        "## 严重度合计",
        "",
        "| 级别 | 条数 |",
        "| --- | ---: |",
    ]
    for sev in (SEV_ERROR, SEV_WARN, SEV_REVIEW, SEV_INFO):
        lines.append(f"| {sev} | {summary['severity_totals'].get(sev, 0)} |")
    lines += ["", "## 模板分布", "", "| 模板 | 卷数 |", "| --- | ---: |"]
    for k, v in sorted(summary["by_template"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 问题码（按次数）", "", "| 码 | 级别 | 次数 |", "| --- | --- | ---: |"]
    for code, n in summary["by_code"].items():
        sev = "/".join(sorted(summary["by_code_severity"][code]))
        lines.append(f"| `{code}` | {sev} | {n} |")
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_highrisk(worst: list[tuple[int, dict]], out_dir: str, top: int = 40) -> None:
    lines = ["# 高风险卷逐卷证据（自动排序）", "", "排序权重 = error×10 + warn×3 + review；info（占位）不计权重。", ""]
    for rank, (weight, row) in enumerate(worst[:top], start=1):
        lines.append(f"## {rank}. {row['path']}")
        lines.append("")
        st = row["stats"]
        lines.append(
            f"- 模板 `{row['template']}` · {st['questions']} 题 · 材料 {st['materials']} · 折叠块 {st['details']} · 表格 {st['tables']} · 图片 {st['images']}"
        )
        c = row["counts"]
        lines.append(f"- error {c['error']} / warn {c['warn']} / review {c['review']} / info {c['info']} · sha256 `{row['sha256'][:16]}…`")
        for issue in row["issues"][:12]:
            ev = f" · 证据：`{issue['evidence']}`" if issue["evidence"] else ""
            lines.append(f"- **{issue['severity']}** `{issue['code']}` L{issue['line']} — {issue['message']}{ev}")
        if len(row["issues"]) > 12:
            lines.append(f"- …另有 {len(row['issues']) - 12} 条，见 receipts.jsonl")
        lines.append("")
    with open(os.path.join(out_dir, "highrisk.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全量 Markdown 版式检查（只读）")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="只检查路径包含该子串的卷")
    ap.add_argument("--skip-gate", action="store_true")
    args = ap.parse_args(argv)
    summary = run(args.repo, args.out, limit=args.limit, only=args.only, skip_gate=args.skip_gate)
    if "BLOCKED" in summary:
        print(json.dumps(summary, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "papers": summary["papers"],
                "severity_totals": summary["severity_totals"],
                "elapsed_s": summary["elapsed_s"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
