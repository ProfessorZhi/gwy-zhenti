# 国考2026副省级 Q31 差异待判矩阵 + 逐题校验器（第 4 轮）

**日期**：2026-10-17 · **lane**：gwy-zhenti 视觉/结构独立 QA（非登录）
**基线**：PR #47 HEAD `ae0372815c7eb71c29ba6965f55f8bd7bee77156`
**对照**：PR #51 HEAD `74bbc09c287c21d5b7aec2723784d0901ef95256`
**工作区**：`/home/fjd/workspaces/gwy-zhenti-assetsqa-20261017/repo`（本 lane 独立分支）
**资源**：load 1.61，**available RAM 10 GiB**，disk 280 GB，20 CPU；无 408 重任务在跑 → 6 卷轻量离线检查，未降载

---

## 0. 必须先说清楚的一件事：本批**没有**拿到新数据

PR #51 声称新增采集 `国考2026副省级`（sourceId `5823069`，135 题 / 6 材料 / 39 图引用 / 38 唯一 SHA / Q31 同号差异），并把产物放在：

```
work/fenbi/papers/gk-2026-xingce-fushengji-5823069/        ← fenbi lane 的私有 work 目录
work/fenbi/discovery-20261017/source-catalog-handoff.json  ← 另一个 handoff
```

**你授权给我、且我一直在用的无凭据 handoff 是：**

```
/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/handoff-20261017/papers/
  gd-2020-xingce-county-96785   js-2024-xingce-a-4162243
  js-2025-xingce-c-4189916      zj-2026-xingce-c-8399763
```

**这 4 卷里没有 `5823069`。** 按你的规则「绝不能打开/读取/复制他人 raw 受限数据私有目录」，我**没有**进入上述 `work/fenbi/papers/…` 或 `discovery-20261017/`。

**因此本批的诚实结论是：**
- Q31 只能出**待判证据矩阵**，`capture` 一列为 `unknown`；
- 「39 下载图 / 38 唯一 SHA 自验」「Q31 同号差异」这两条**我无法独立复核**，只能记为**单源文书主张**；
- **不冒称完成 5 卷 QA**。本批实际做的是：**1 份 Q31 证据矩阵 + 1 个逐题校验器 + 6 卷本地结构量化**（其中 **capture 侧仅 4 卷有授权证据**）。

> 若要我真正验真 `5823069`，需要：把该卷以**既有 `handoff-20261017` 同规格式**（metadata + 图片 SHA，无凭据、无正文上传）放进**授权目录**，或明确授权我读 `discovery-20261017/source-catalog-handoff.json`。

---

## 1. Q31 待判证据矩阵

原题号 **31**。三列各自标注证据等级，**互不替代**。

| 列 | 证据等级 | 内容 |
| --- | --- | --- |
| **A. 仓库侧**（`国考/2026/行测-副省级.md`） | `repo-read`，完全可复现 | 32 字题干；4 个选项（15/12/15/13 字）；选项 A/B/D 各含 1 张公式图，C 为纯文本；**3 张公式图 SHA 已算**；答案/解析 `unknown` |
| **B. 采集侧**（粉笔 `5823069`） | **`unknown`** | **无授权 handoff** → 不可读、不可验 |
| **C. PR #51 文书主张** | `single-source-documentation`，**未独立核实** | 「Q31 实测为真题正文（32 字题干 + 4 选项），非占位存根，属同号内容差异」；整卷 135 题 matched 134；39 图引用 / 38 唯一 SHA |

**仓库侧实测（A 列）**

| 字段 | 值 |
| --- | --- |
| 题干字数（去标签、去图后） | **32** |
| 选项数 | 4（A/B/C/D 齐全） |
| 选项字数 | A 15 · B 12 · C 13 · D 15 → 按 A-D 顺序 **15/12/15/13** |
| 选项图片数 | A 1 · B 1 · C 0 · D 1 |
| 公式图 SHA256 | A `76be05101bb6644bef91c0b11629d04c5b7df1898ad412f55ce66612cc2e7b3c`<br>B `0319f6ce1cf3baba46cb06864d2334afb47cdb344de3902d4c30bab0c139ffd6`<br>D `d74b3663be10632fed1040c4b78a28b9af3a1dab0aee8f61e4a57101f8a57ef9` |
| 本卷题号连续性 | 135 题，1–135 无缺口，与 `缺失原题号: []` 一致 |
| 答案 / 解析 | `unknown`（仓库侧不可观察，且不得从答案逆推题干） |

**一个可核对的收敛点**：PR #51 说采集侧 Q31 是「**32 字题干 + 4 选项**」，仓库侧实测也是 **32 字 + 4 选项**。
→ 「同号差异」**不是长度差异**；若真要判，差异只可能在**措辞/图形**。而这需要 B 列数据，目前无。

**判定：`needs_review`（不得判 same，也不得判 different）。**

---

## 2. 逐题校验器（本批主交付物）

`tools/fenbi/assetsqa/paper_question_validator.py` —— 离线、无网络、无浏览器、无账号，逐题跑。

### 2.1 每题检查项（对应你的清单）

| # | 检查 | 实现 |
| --- | --- | --- |
| 1 | `sourceID` | 有授权 handoff 才取 `identity.sourceId`；否则 `unknown-no-authorized-handoff` |
| 2 | 地区 / 年份 / 卷型 | 解析 frontmatter，与注册表期望三元组比对（`identity.matches`） |
| 3 | 原题号 | 题头解析；范围、缺口、**重复号**（在 dict 折叠前统计） |
| 4 | 材料 / 章节 | 材料块与 `（第X—Y题共用）` 区间解析；材料图引用单独计数 |
| 5 | 字面题干 vs 图片字节 | 题干去标签后字数 + 题干图片数 + **每张图的 sha256** |
| 6 | 选项 A–D 必须实际有内容 | 每项「非空非标签文本」**或**「可解析图片」才算有内容 |
| 7 | 图片引用与 SHA | 每张 `<img>` 必须能在盘上解析并解码；失败即 `invalid` |
| 8 | 空题 / 征集占位绝非有效题 | 哨兵 `{缺失,暂缺}` 或题干含「征集」+「上传」→ `invalid` |
| 9 | 答案 / 解析不可观察 | 一律 `unknown`，**不从答案逆推题干** |

### 2.2 词表（刻意收窄，避免过度声称）

| 判定 | 含义 |
| --- | --- |
| `structurally_valid` | **本地结构检查全过**。**不**代表官方原卷、**不**代表采集侧一致 |
| `incomplete` | 选项无独立内容对象（图形题合成图，已知有界情形） |
| `invalid` | 硬失败（占位 / 空题干 / 选项缺失 / 图片不可解析 / 不在采集内） |
| `capture_verified` | **只有当授权 handoff 覆盖该卷时**才可能设定 |

`answer` / `explanation` 恒为 `unknown`。

### 2.3 六卷实跑结果

| 卷 | sourceId | 题数 | `structurally_valid` | `incomplete` | `invalid` | 题块图引用/唯一SHA | 材料图 | 缺口==声明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 江苏2025C | `4189916` | 130 | **121** | 9 | **0** | 48 / 48 | 6 | ✅ |
| 江苏2024A | `4162243` | 131 | **117** | 14 | **0** | 57 / 57 | 4 | ✅ |
| 广东2020县级 | `96785` | 93 | **80** | 13 | **0** | 74 / 58 | 25 | ✅（69–75） |
| 浙江2026C | `8399763` | 110 | **103** | 7 | **0** | 34 / 23 | 3 | ✅ |
| 国考2026副省级 | **`unknown`** | 135 | **128** | 7 | **0** | 38 / 33 | 6 | ✅ |
| 国考2026地市级 | **`unknown`** | 130 | **123** | 7 | **0** | 28 / 27 | 5 | ✅ |
| **合计** | — | **729** | **672** | **57** | **0** | — | — | 6/6 |

**读数要点**

- **`invalid` = 0**：6 卷 729 题中，**没有**空题干、没有不可解析图片引用、没有选项缺失、没有占位混入。这是本轮唯一的硬通过结果。
- **`incomplete` = 57**：全部是第 3 轮已定性的「图形题合成图 + 标签字母选项」——**不是缺陷，是缺独立对象**。
- **`sourceId` 只有 4 卷有值**：另外 2 卷（国考）标 `unknown-no-authorized-handoff`。**不填 PR #51 文书的 `5823069`**，因为那是单源主张、未经我复核。
- **缺口全部等于声明**：`gapsMatchDeclaredMissing = true` × 6。

---

## 3. 本批**没有**做的事（避免误读）

| 没做 | 原因 |
| --- | --- |
| 读了 `5823069` 的 image SHA / 结构化证据 | **无授权 handoff** |
| 判 Q31 是 same 还是 different | capture 列 `unknown` |
| 复核「39 下载 / 38 唯一 SHA」 | 同上 |
| 声称完成「新增 5 份试卷」QA | **没有拿到那 5 卷的授权数据**；只做了 4 卷采集侧 + 6 卷本地结构 |
| 把 `structurally_valid` 说成 verified | 词表已明确禁止 |

---

## 4. 工具 / 测试 / 可逆性

新增 `tools/fenbi/assetsqa/paper_question_validator.py`（约 330 行）+ `test_paper_question_validator.py`（**29 条**）。

**过程中修掉自己两个 bug（均有回归测试）**

1. **题干字数虚高**：`split_options` 没先剥掉 `## 第 N 题 <sub>qid…</sub>` 题头，导致国考 Q31 被读成 **63 字**，实际 **32 字**。
2. **重复题号被吞**：重复号在 dict 折叠后才统计，永远为空；改为在**题头原始序列**上统计。

**测试**：`python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa` → **90 passed，exit 0**（此前 61 + 新增 29）。

**可逆性**：本批**不产生任何图片/切块产物**；只新增 3 个源码/报告文件，`git revert` 即完全回滚。未改任何试卷 MD。

**安全**：未访问粉笔账号/profile/Cookie；未开浏览器；未新建练习；未联网搜原文；未碰 main、PR #38/#41/#47 head、PR #51 head。

---

## 5. 复现

```bash
cd <repo>
python3 -I tools/fenbi/assetsqa/paper_question_validator.py \
  --repo . --handoff <authorized-handoff> --focus 31 \
  --out reports/ASSETSQA-R4-PER-QUESTION-VALIDATION-20261017.json

ASSETSQA_REPO=$PWD ASSETSQA_HANDOFF=<authorized-handoff> \
  python3 -m unittest discover -s tools/fenbi/assetsqa -t tools/fenbi/assetsqa -v
```

---

## 6. 需要协调的事（阻塞项）

1. **`5823069` 的授权 handoff**：按 `handoff-20261017` 同规格式落到授权目录（或明确授权读 `discovery-20261017/source-catalog-handoff.json`），我才能把 Q31 的 B 列填上。
2. 若要覆盖「新增 5 卷」，同样需要这 5 卷各自的授权 handoff。
3. 在此之前，Q31 维持 **`needs_review`**，不得被任何下游当作 same 或 different。
