# 覆盖率优先补卷 Implementation Plan（M-COV）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 2016–2026 国考 + 各省**真实存在**的行测、申论试卷**尽量收齐**，并先把「应有试卷清单」建成一份可审计的账。

**Architecture:** 沿用既有两段式（`catalog` 清单 → `export` 导出 → `gate` G1–G6）。新增 **`expect`**（应有清单）一层，以及新源 **`slb`**（申论全卷）与 **`shangantong`**（行测含图）。

**Tech Stack:** Python 3.12 纯标准库；既有 `tools/gwyzhenti/` 包。

**Spec:** 用户 2026-10-09「覆盖率优先」指令（见 `.superpowers/sdd/2026-10-09-gwy-zhenti-coverage/progress.md` 的逐条摘录）+ 既有 `docs/superpowers/specs/2026-10-09-gwy-zhenti-merge-design.md`。
**侦察证据:** `work/COVERAGE-RECON.md`。

## Global Constraints

- **不改 `work/mirror/`；不覆盖 `knowledge/`；不自动提交或推送。** 全部提交留在本地 `feat/m1-merge`。
- **禁止改写正文、改答案、猜 OCR 错字或补知识内容。**
- **不做跨卷题目去重**（用户明令：同题在不同省卷出现是正常的，各自保留完整原卷）。
- **不做 PDF 重转、不做 OCR**（spec §2）。PDF 仅作争议题**原件对照**。
- **不得把模考/模拟/改写材料/选调专项冒充真实国省考原卷。**
- **不得把同一数据家族的 Fork/镜像算作新增覆盖。**
- **抽样通过不得伪装成每份都已通读。**
- **「应有」须来自规则骨架 ∪ 多源证据并集；无证据的格标「尚未找到」，不得标「考试未举行」。**
- 交付下限 **2016**（`export.SCOPE_SINCE`）。
- **D 盘纪律**：不对 `D:` 跑 `find` / 递归 grep / `Glob`，不对 `D:` 跑 `du -sh`；Python 一律 `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -X utf8`。
- 提交信息结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 1: 应有试卷清单生成器（`expect`）

**Files:**
- Create: `tools/gwyzhenti/expect.py`
- Create: `tools/tests/test_expect.py`
- Produce: `work/EXPECTED.jsonl`、`work/EXPECTED.md`

**Interfaces:**
- Consumes: `export.load_catalog`、`export.repo_paths`、`model.PaperKey`；`work/slb_shenlun_manifest.json`；`_gwy-upstream/{xingcezhenti,gongkao-tiku,shangantong-papers-v2-c1,-c2,zzcc-nb-gongkao-tiku}`
- Produces: `expect.build(...) -> list[dict]`，每行字段固定：`level, region, year, session, subject, ptype, status, attested_by, delivered_md, note`；`status ∈ {已有, 源有未导入, 尚未找到, 待核实}`

- [ ] Step 1：写 `expect.py`（只读生成器，风格照 `report_accept.py`）：从**各源 TOC** 抽取 `(level, region, year, subject, ptype)` 证据并集；与交付树对账定 `status`；`多省联考` 伪地区**不作为 region 输出**（其内容另记 `note`）。
- [ ] Step 2：写 `test_expect.py`（覆盖：证据并集、`status` 判定、伪地区剔除、`ptype` 含序列词）。
- [ ] Step 3：跑全量单测（基线 **196**）。
- [ ] Step 4：真库生成，核对总数应 ≥ 用户口径 704 格展开后的卷型数。
- [ ] Step 5：提交。

### Task 1b: `SGHCN0762` 证据源 #6（卷型 TOC）

**Files:** Modify `tools/gwyzhenti/expect.py`、`tools/tests/test_expect.py`、`work/EXPECTED.{jsonl,md}`、`work/PTYPE-MAP.md`；Create `tools/gwyzhenti/data/sghcn_toc/*.txt`（4 份文件名清单拷贝，**入库**）。

- 裁定 **R-COV-11**：`SGHCN0762` 系列**不导入任何内容**（申论侧全 PDF；行测 JSON 无图，实测 `png/base64` 计数全 0）。
  仅作 **TOC 证据 + 原件对照**，以**证据源 #6** 并入 `expect`。
- 价值：其申论文件名**带精确卷型**（`2023年公务员多省联考《申论》真题及答案（安徽A卷）`）⇒ **Task 3 拆并卷的权威卷型地图**；
  国考申论 PDF 覆盖 2024/2025 三卷型 + 2026 行政执法 = 国考 **9 个卷型级缺卷中的 7 个**的原件对照。
- 关键解析：**省名优先于「多省联考」**（`region` 取省名，绝不产 `region="多省联考"`）；国考 `level="国考"`、`region=""`。
- md 须**新增「来源可导入性」节**，把 `sghcn` 标为「**否 —— 仅 TOC/原件对照**」，防止读者误当可补源。

### Task 2: SLB 申论源接入（`slb`）

**Files:** Create `tools/gwyzhenti/slb.py`、`tools/tests/test_slb.py`
- 拉取 `mkih76/SLB` 的 `data/shenlun_zhenti`（393 份，**排除 17 存根 + `国考_0_*` 素材**）到 `work/slb-mirror/`。
- 解析 frontmatter（`source/tid/board/province/year/exam_type/title`）→ 真题目录 md（材料全文 + 作答要求 + 分值）。
- **逐卷记来源**：`shenlunhome.com` + `tid` + `crawled_at`。
- 按 `exam_type`/`title` **重新归位**（不信文件名前缀）。
- 先落**候选区**，不直接覆盖交付树。

### Task 3: 并卷拆分（国考三卷型 + 浙江 A/B/C 等）

- **只在拿到真实分卷原件时拆**；无原件者保留 `统考` 并在账上标注。
- 国考申论三卷型原件：SLB 的 `data/fenbi_zhenti/guokao` PDF（**仅供对照**）+ SLB 已有分卷 md。
- 拆分后由 `gate` 复验；旧 `统考` 行按裁定退役。

### Task 4: 行测补缺（`shangantong`）

- 新增 `sources/shangantong.py`（解析 `paper_*/index_static.html` → 卷/题/图；`.bin` 按魔数转 `.png`）。
- 只补 26 个行测缺口；与 `xingcezhenti` 已交付**去重**。

### Task 5: 剩余 69 个申论空格的外部源搜索

- 候选：`zzcc-nb` 申论题库（3852 题，**须过滤模考**）、爱真题/考考公务员站点、新 GitHub 仓。
- 先判「一个新源能补多少套独立缺卷」，再决定是否接入。

---

## 自评（写计划后自查）

- **覆盖用户要求**：① 应有清单 → Task 1；② 先找现成优质来源 → Task 2/4/5；③ 按缺口补卷、不盲导整仓 → Task 2/5 的「先判增量再接入」；④ 第一阶段不做的事（去重/修 770 空要求/修 484 截断/逐卷精校）→ **本计划不含这些任务**。✅
- **占位符扫描**：Task 1/2 的接口与字段为**已定**值；Task 3/4/5 为**方向**（其细节待各自简报）。⚠️ 已知：Task 3/4/5 尚无逐步骤细分 —— **按 spec §191，各自出计划**时补齐。
- **类型一致**：`status` 取值、`ptype` 键体系、`SCOPE_SINCE` 与既有包一致。✅
