#!/usr/bin/env python3
"""Emit 11-case.jsonl from collected evidence + adjudication table."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
col = {c["rank"]: c for c in json.load(open(os.path.join(HERE, "collected.json"), encoding="utf-8"))}
ver = {v["path"]: v for v in json.load(open(os.path.join(HERE, "patch-verification.json"), encoding="utf-8"))}

V = {
 6: dict(
   verdict="VERIFIED_FORMAT_ERROR",
   secondary=[],
   strength="strong",
   summary="每个答案块结尾 `</details>` 前都有一条 `---`（136/136），且「**官方解析**」正文又以「解析 第…/解析 解法一…」开头（136/136），展开后先看到重复的「解析」，再看到底部一条分隔线。",
   evidence=[
     {"kind":"pattern-count","detail":"`---` 紧邻 `</details>`：136 处；`**官方解析**` 后紧跟 `解析`：136 处（131「解析 第」/3「解析 解法」/2「解析第」）","path":"省考/上海/2017/行测-统考.md","line":50},
     {"kind":"provenance","detail":"frontmatter 来源为 linfukai186 + 题干/答案 PDF 重建（非粉笔快照），无 Q1 source 记录；因此不能判断是 PDF 自带标签还是重建时合并，只按可见文本认定为排版冗余。","path":"省考/上海/2017/行测-统考.md","line":12},
   ],
   fix="patch 0001（同一文件两处）：删除 136 条紧邻 </details> 的 `---`；删除 136 处 `**官方解析**` 后重复的「解析 」前缀。补丁验证：`<details>` 外文本全等、答案段全等、解析段仅少该前缀、`---` 计数不变。",
   fix_status="proposed",
   patch="patches/0001-shanghai2017-hr-and-dup-jiexi.patch",
   human=["38 张位图（35 题图 + 3 资料分析材料图）未看","3 题（72/75/81）用 `$…$` 内联公式，渲染依赖数学支持"],
  ),
 18: dict(
   verdict="ALREADY_FIXED_IN_PR140",
   secondary=[],
   strength="strong",
   summary="`给定<u>资料</u>4</u>中` 多一个 `</u>`（136 开 / 137 闭）。PR#140 head c5e11c44 已删除该标签。",
   evidence=[
     {"kind":"diff","detail":"PR#140 与 main 的差异只有这一行：删一个 `</u>`，去掉标签后可见文字完全相同（−4 字节）。","path":"省考/北京/2026/申论-选调生.md","line":121},
     {"kind":"source-dom","detail":"源快照 7662646 的 prompt.html 里是 `<u><u><u>资料</u>4</u></u>`（u 开合各 175，平衡）；渲染成 Markdown 时嵌套同名标签被压平，才留下多余闭合标签。","path":"/home/fjd/tmp/shenlun-verify-20261027-round3/7662646/document.json","line":0},
   ],
   fix="已在 PR#140；本地镜像补丁 0004 与 PR 逐字节相同；静态检查器 ES001 由 1 error 降为 0。",
   fix_status="already_in_pr140",
   patch="patches/0004-beijing2026-stray-u-close.patch",
   human=["4 张参考答案位图未看"],
  ),
 19: dict(
   verdict="NEEDS_ORIGINAL_IMAGE",
   secondary=["SOURCE_EXCEPTION"],
   strength="strong",
   summary="第 1 题选项 C/D 显示为「714」「716」。源侧原始 DOM 与 normalized document 也都是 714/716（所以不是仓库抄错），但同一份源快照的题干预告已丢失 √2（「2，，4，，」）而 MD 里却有「2√2、4√2」——说明上游在某个环节丢过根号，选项真值只能看原卷图才能确定。",
   evidence=[
     {"kind":"raw-dom","detail":"harvest/x-吉林-2008-103/stem.html：`<p class=\"input-text\">714</p>`；选项内无 `<sup>`、无 `<img>`。","path":"/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/harvest/x-吉林-2008-103/stem.html","line":0},
     {"kind":"normalized-source","detail":"repair-stage document.json 第 1 题 options = ['6','8','714','716']，与 MD 完全一致；同源题干预告为「2，，4，，」（√2 在源侧就已丢失）。","path":"/home/fjd/workspaces/gwy-zhenti-fenbi/repo/work/fenbi/repair-stage/x-吉林-2008-103/document.json","line":0},
   ],
   fix="不做修复（任何补字都会变成猜测）。建议 owner 调原卷/PDF 图像确认 C/D 的真值；在此之前把该题选项标为 source-unverified。",
   fix_status="needs_original_image",
   patch="",
   human=["需要源侧/原卷确认 C/D 究竟是 7√14/7√16 还是别的写法"],
  ),
 22: dict(
   verdict="VERIFIED_FORMAT_ERROR",
   secondary=["SOURCE_EXCEPTION"],
   strength="medium",
   summary="第 1 题题干点名「给定资料1」，但全卷没有「关联材料」行（基线 MT004）；读者无法从题目跳到材料。",
   evidence=[
     {"kind":"stem-vs-nav","detail":"Q1 题干「请根据给定资料1…」；Q2「根据给定资料，概括…」不带编号；8 则材料但 0 条关联材料。","path":"省考/四川/2017/申论-下半年.md","line":375},
     {"kind":"source-faithful-repeat","detail":"Q1 的答案折叠块在答文之后又把原题连同分值/要求重列了一遍（来源答案文档自带），属源侧形态，不是错配；只作为可读性备注。","path":"省考/四川/2017/申论-下半年.md","line":415},
   ],
   fix="不改：Q2 的「给定资料」没有编号，补导航等于猜映射。建议由生成器在有明确编号时补 `关联材料：材料 N`。",
   fix_status="owner_decision",
   patch="",
   human=[],
  ),
 36: dict(
    verdict="FALSE_POSITIVE",
    secondary=[],
    strength="medium",
    summary="单题作文卷，题干只说「参考给定材料」、没有任何「资料N」编号；不写关联材料行是合理的。",
    evidence=[
      {"kind":"stem","detail":"全卷 1 题：「请以“公共舆论中的公共理性”为主题写一篇议论文…参考“给定材料”，可不拘泥于材料」；无编号引用。","path":"省考/广东/2016/申论-广州市考.md","line":97},
      {"kind":"materials","detail":"3 则材料，题面不指向具体某一则，导航行没有可指的确定目标。","path":"省考/广东/2016/申论-广州市考.md","line":39},
    ],
    fix="无需修复；基线 MT004 在本卷应降级为 info（无编号引用）。",
    fix_status="not_applicable", patch="", human=[],
  ),
 37: dict(
    verdict="VERIFIED_FORMAT_ERROR",
    secondary=["FALSE_POSITIVE"],
    strength="strong",
    summary="100 个折叠块结尾都有 `---`（真实排版冗余，可修）；而「H2/H3 混用」是资料分析题按材料分组的有意层级，不是缺陷。",
    evidence=[
      {"kind":"pattern-count","detail":"`---` 紧邻 `</details>`：100/100。","path":"省考/广东/2016/行测-广州市考.md","line":43},
      {"kind":"hierarchy","detail":"`## 材料 1` 后紧跟 `### 第 85 题` … `### 第 89 题`，其余题用 `## 第 N 题`——H3 明确表示“该材料下的题组”，语义一致。","path":"省考/广东/2016/行测-广州市考.md","line":2220},
    ],
    fix="patch 0002：删除 100 条紧邻 </details> 的 `---`；不动标题层级。",
    fix_status="proposed", patch="patches/0002-guangzhou2016xingce-drop-hr.patch",
    human=["23 张题图未看"],
  ),
 51: dict(
    verdict="VERIFIED_CONTENT_IDENTITY_ISSUE",
    secondary=[],
    strength="strong",
    summary="答案正文 397 个字符用了康熙部首码位（⻛ U+2EDB、⺠、⻓、⻔…共 13 种），字形与「风/民/长/门」相近但不是同一字符；搜索、复制、NFKC 规范化都会失败。",
    evidence=[
      {"kind":"char-inventory","detail":"⻛×272、⺠×55、⻓×18、⻜×12、⻔×10、⻘×10、⻅×5、⻬×4、⻋×4、⻄×3、⻆×2、⻝×1、⻣×1 = 397","path":"省考/江苏/2016/申论-统考.md","line":0},
      {"kind":"corpus-scale","detail":"全库 89 卷共 17,587 个此类码位（仅作规模参考，不在本 lane 处理）。","path":"repo-main（全量扫描）","line":0},
    ],
    fix="未打补丁：批量替换康熙部首属于内容改写，需逐字证明 1:1 对应且不误伤真正的部首用法。建议 owner 做单卷 NFKC 归一 + 前后字形对照表 + 抽样人工确认。",
    fix_status="owner_decision", patch="",
    human=["需确认该卷是否有意使用部首字形"],
  ),
 52: dict(
    verdict="VERIFIED_FORMAT_ERROR",
    secondary=["FALSE_POSITIVE"],
    strength="strong",
    summary="129 个折叠块结尾有 `---`（可修）；「H2/H3 混用」是因为 `## 材料 1（第41—45题共用）` 明确声明了题组归属，层级差是有语义的。",
    evidence=[
      {"kind":"pattern-count","detail":"`---` 紧邻 `</details>`：129 处（另有 1 处 `---` + 空行 + `</details>`）。","path":"省考/江苏/2024/行测-C类.md","line":43},
      {"kind":"hierarchy","detail":"材料标题自带范围：`## 材料 1（第41—45题共用）`，其下 5 个题用 H3；其余 103 题用 H2。","path":"省考/江苏/2024/行测-C类.md","line":1132},
    ],
    fix="patch 0003：删除 129 条紧邻 </details> 的 `---`；不动标题层级。",
    fix_status="proposed", patch="patches/0003-jiangsu2024c-drop-hr.patch",
    human=["59 张题干/材料位图未看"],
  ),
 60: dict(
    verdict="VERIFIED_CONTENT_IDENTITY_ISSUE",
    secondary=["SOURCE_EXCEPTION"],
    strength="strong",
    summary="这份「河南 2018 统考」实为河南 2017 主卷（粉笔 82930）的一个更短、无答案的重复版本：材料标题与正文资料号错位（材料4→资料5、材料5→资料6，且没有「资料4」标题），不是单纯的排版错。",
    evidence=[
      {"kind":"content-overlap","detail":"2018 版 8-gram 有 91.2% 出现在 2017 版里，而 2017 只有 59.8% 出现在 2018——2018 是 2017 的子集。","path":"省考/河南/2018/申论-统考.md","line":0},
      {"kind":"volume-identity","detail":"2017 版有粉笔源 82930（https://www.fenbi.com/ti/view/paper/6_2_2gvi）、6 则材料、4 个答案折叠块；2018 版无源 ID、5 个材料标题、0 个折叠块。mergeprep 审计把 2017/82930 作为独立发布卷列出，浏览器 Owner 索引也有 `ha-2017-shenlun-unknown-82930`。","path":"省考/河南/2017/申论-统考.md","line":1},
      {"kind":"label-mismatch","detail":"2018 版 `### 材料 4` 正文首行「资料5」、`### 材料 5` 正文首行「资料6」；6 个「资料N」标记 vs 5 个标题；无独立「资料4」。","path":"省考/河南/2018/申论-统考.md","line":77},
    ],
    fix="不做排版补丁（重编号会掩盖身份问题）。建议 owner 把 2018 版按重复卷处理：退役或并入 2017/82930 主卷；若保留，需先把材料标题与正文资料号对齐并补答案。",
    fix_status="owner_decision", patch="",
    human=["需要 owner 决定重复卷的归属（2017 主卷 vs 2018 别名）"],
  ),
 63: dict(
    verdict="VERIFIED_CONTENT_IDENTITY_ISSUE",
    secondary=["FALSE_POSITIVE"],
    strength="strong",
    summary="「文章分析在答案区」被误报：源快照里文章分析本来就在 referenceAnswer 内、MD 只是照搬。真正的问题是源侧有「考点/来源」而 MD 完全没有这两行。",
    evidence=[
      {"kind":"source-structure","detail":"209063 q3 的 prompt.html 含「文章分析」，referenceAnswer html 5384 字符，与 MD 的答案块结构一致。","path":"/home/fjd/tmp/shenlun-verify-20261027-round3/209063/document.json","line":0},
      {"kind":"metadata-gap","detail":"源 q1/q3 的 otherSections 有 考点（textLen 6/8, nonEmpty）与 来源（22）；MD 全文没有 `**考点**` / `**来源**` 行。","path":"省考/浙江/2023/申论-A类.md","line":0},
    ],
    fix="不改：补 `**考点**`/`**来源**` 是新增内容，应由生成器按源字段回填；文章分析位置保持与源一致。",
    fix_status="owner_decision", patch="",
    human=["3 张图未看"],
  ),
 88: dict(
    verdict="ALREADY_FIXED_IN_PR140",
    secondary=[],
    strength="strong",
    summary="`|甲-乙|=|丙-丁|` 在 main 里是裸露的竖线文本（易被误读成表格）；PR#140 已改为反引号代码 `` `|甲-乙| = |丙-丁|` ``。",
    evidence=[
      {"kind":"diff","detail":"PR#140 与 main 的唯一差异：这一行加反引号并在 = 两侧加空格；静态检查器前后均 0 error。","path":"省考/青海/2014/行测-统考.md","line":2168},
      {"kind":"render-check","detail":"该行前后均为空行、无分隔行，GFM 不会把它当表格，只是纯文本竖线易读错——属可读性，不是结构损坏。","path":"省考/青海/2014/行测-统考.md","line":2167},
    ],
    fix="已在 PR#140；本地镜像补丁 0005 与 PR 逐字节相同（代码跨度内多 2 个空格，语义不变）。",
    fix_status="already_in_pr140", patch="patches/0005-qinghai2014-pipe-math.patch",
    human=["15 张图未看"],
  ),
}

rows = []
for rank in sorted(V):
    c = col[rank]; v = V[rank]
    path = c["path"]
    pv = ver.get(path, {})
    rows.append({
        "case": rank,
        "path": path,
        "md_sha256": c["main_sha"],
        "pr140_sha256": c["pr140_sha"],
        "pr140_same": c["pr140_same"],
        "patched_sha256": pv.get("after_sha", ""),
        "area": c["area"], "year": c["year"], "subject": c["subject"], "variant": c["variant"],
        "nature": c["nature"], "validation": c["validation"],
        "source_key": c["source"]["key"], "source_class": c["source"]["class"],
        "source_snapshot_sha256": c["source"]["doc_sha"],
        "source_document": c["source"]["doc_path"],
        "flagged_issues": [i["code"] for i in c["receipt_issues"]],
        "verdict": v["verdict"],
        "secondary_verdicts": v["secondary"],
        "evidence_strength": v["strength"],
        "summary": v["summary"],
        "evidence": v["evidence"],
        "minimum_risk_fix": {"action": v["fix"], "status": v["fix_status"], "patch": v["patch"],
                             "verified": bool(pv.get("pass")) if v["patch"] else None},
        "still_needs_human": v["human"],
        "lane_note": "AI-assisted adjudication, not human L3 acceptance",
    })

with open(os.path.join(HERE, "11-case.jsonl"), "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print(json.dumps({"cases": len(rows),
                  "verdicts": {k: sum(1 for r in rows if r["verdict"] == k) for k in
                               ("VERIFIED_FORMAT_ERROR", "VERIFIED_CONTENT_IDENTITY_ISSUE",
                                "ALREADY_FIXED_IN_PR140", "SOURCE_EXCEPTION", "FALSE_POSITIVE", "NEEDS_ORIGINAL_IMAGE")}},
                 ensure_ascii=False, indent=1))
