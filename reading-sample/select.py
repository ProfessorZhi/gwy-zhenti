#!/usr/bin/env python3
"""Fixed-seed stratified selection: 92 papers, risk over-sampled."""
import json, random, sys, collections

SEED = 20261028
TARGET = 92
FRAME = sys.argv[1] if len(sys.argv) > 1 else "frame.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "sample.jsonl"

MANDATORY = [
    ("国考/2016/申论-副省级.md", "named:2016国考申论副省"),
    ("省考/江苏/2025/申论-C卷.md", "named:江苏2025C材料1-4"),
    ("省考/浙江/2023/申论-A类.md", "named:浙江2023A文章分析"),
    ("省考/北京/2023/行测-统考.md", "named:北京2023行测缺题占位"),
    ("省考/上海/2017/行测-统考.md", "named:上海2017行测解析算式"),
    ("省考/北京/2026/申论-选调生.md", "named:R1唯一额外</u>"),
    ("省考/青海/2014/行测-统考.md", "named:青海2014绝对值竖线"),
    ("省考/河南/2018/申论-统考.md", "named:历史R7无折叠"),
    ("省考/黑龙江/2019/行测-边境县-shangantong.md", "risk:qid-h2模板"),
    ("省考/江苏/2024/行测-C类.md", "risk:mixed-level130题"),
    ("省考/广东/2016/行测-广州市考.md", "risk:mixed-level"),
    ("国考/2008/行测-统考.md", "risk:选项在表格行/OP005"),
    ("省考/江苏/2012/申论-统考.md", "risk:SOURCE_MISSING"),
    ("省考/西藏/2016/行测-统考.md", "risk:SOURCE_CONFLICT"),
    ("省考/云南/2026/行测-统考.md", "risk:占位卷PH001"),
    ("省考/江苏/2012/行测-B类.md", "risk:同行选项OP001"),
]

rows = [json.loads(l) for l in open(FRAME, encoding="utf-8")]
by_path = {r["path"]: r for r in rows}

def vb(r):
    v = r["validation"]
    return "candidate" if v.startswith("候选") else ("machine" if v.startswith("机器校验") else "other")

def risk_w(r):
    c = r.get("risk", {}).get("counts", {})
    return c.get("error", 0) * 10 + c.get("warn", 0) * 3 + c.get("review", 0)

chosen = []
seen = set()
for path, why in MANDATORY:
    if path in by_path and path not in seen:
        chosen.append((path, "mandatory", why))
        seen.add(path)

remaining = TARGET - len(chosen)
pool = [r for r in rows if r["path"] not in seen]
strata = collections.defaultdict(list)
for r in pool:
    strata[(r["area"], r["subject"])].append(r)

keys = sorted(strata)
alloc = {k: 1 for k in keys}
left = remaining - len(keys)
# largest remainder on stratum size
if left > 0:
    total = sum(len(v) for v in strata.values())
    rem = []
    for k in keys:
        share = len(strata[k]) / total * remaining
        base = max(1, int(share))
        alloc[k] = base
        rem.append((share - base, k))
    left = remaining - sum(alloc.values())
    for _share, k in sorted(rem, reverse=True):
        if left <= 0:
            break
        alloc[k] += 1
        left -= 1
elif left < 0:
    # too many strata for the target: keep the largest strata at 1
    order = sorted(keys, key=lambda k: -len(strata[k]))
    for k in order[::-1][: -left]:
        if alloc[k] > 0:
            alloc[k] = 0

rng = random.Random(SEED)
for k in keys:
    cand = sorted(strata[k], key=lambda r: r["path"])
    want = alloc.get(k, 0)
    if want <= 0:
        continue
    # Split the stratum by source_validation so the machine-checked share is
    # not inflated by the risk-first pick.
    buckets = collections.defaultdict(list)
    for r in cand:
        buckets[vb(r)].append(r)
    quota = {}
    left_k = want
    for b in sorted(buckets, key=lambda b: -len(buckets[b])):
        share = len(buckets[b]) / len(cand) * want
        quota[b] = int(share)
    left_k = want - sum(quota.values())
    rem = sorted(buckets, key=lambda b: -(len(buckets[b]) / len(cand) * want - quota[b]))
    for b in rem:
        if left_k <= 0:
            break
        quota[b] += 1
        left_k -= 1
    picked = []
    for b, q in quota.items():
        if q <= 0:
            continue
        group = sorted(buckets[b], key=lambda r: r["path"])
        sub = []
        # risk over-sampling inside the bucket
        risky = sorted(group, key=lambda r: (-risk_w(r), r["path"]))
        if risky and risk_w(risky[0]) > 0 and q > 0:
            sub.append(risky[0])
        rest = [r for r in group if r not in sub]
        rest.sort(key=lambda r: (r["year"], r["path"]))
        need = q - len(sub)
        if need > 0 and rest:
            if need >= len(rest):
                sub.extend(rest)
            else:
                step = len(rest) / need
                for i in range(need):
                    sub.append(rest[min(len(rest) - 1, int(i * step))])
        picked.extend(sub[:q])
    for r in picked[:want]:
        chosen.append((r["path"], "stratum", f"{k[0]}/{k[1]} risk={risk_w(r)}"))

assert len(chosen) == TARGET, f"got {len(chosen)}"
out = []
for i, (path, role, why) in enumerate(sorted(chosen, key=lambda x: x[0]), start=1):
    r = dict(by_path[path])
    r.update({"rank": i, "role": role, "why": why, "stratum": f"{r['area']}/{r['subject']}"})
    out.append(r)

with open(OUT, "w", encoding="utf-8") as fh:
    for r in out:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")

summ = {
    "seed": SEED,
    "target": TARGET,
    "selected": len(out),
    "mandatory": sum(1 for r in out if r["role"] == "mandatory"),
    "strata": len({r["stratum"] for r in out}),
    "areas": len({r["area"] for r in out}),
    "years": sorted({r["year"] for r in out}),
    "subjects": dict(collections.Counter(r["subject"] for r in out)),
    "validation": dict(collections.Counter(vb(r) for r in out)),
    "source_class": dict(collections.Counter(r["source_class"] or "(none)" for r in out)),
    "risk": {
        "error": sum(1 for r in out if r["risk"].get("counts", {}).get("error")),
        "with_review": sum(1 for r in out if r["risk"].get("counts", {}).get("review")),
        "placeholder": sum(1 for r in out if "PH001" in r["risk"].get("codes", [])),
        "total_review": sum(r["risk"].get("counts", {}).get("review", 0) for r in out),
    },
}
json.dump(summ, open("sample-summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(summ, ensure_ascii=False, indent=1))
