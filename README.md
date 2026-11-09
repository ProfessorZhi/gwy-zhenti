<p align="center">
  <img src="docs/assets/banner.svg" alt="全国公务员考试真题库：国考 · 省考，行测 · 申论" width="100%">
</p>

<!-- gwy:badges:start -->
<p align="center">
  <a href="catalog/INDEX.md"><img alt="行测 736 份" src="https://img.shields.io/badge/%E8%A1%8C%E6%B5%8B-736%20%E4%BB%BD-2563eb?style=for-the-badge"></a>
  <a href="catalog/INDEX.md"><img alt="申论 934 份" src="https://img.shields.io/badge/%E7%94%B3%E8%AE%BA-934%20%E4%BB%BD-d97706?style=for-the-badge"></a>
  <a href="docs/SCHEMA.md"><img alt="格式 Markdown" src="https://img.shields.io/badge/%E6%A0%BC%E5%BC%8F-Markdown-0f766e?style=for-the-badge"></a>
  <a href="docs/SCHEMA.md"><img alt="题图 本地存储" src="https://img.shields.io/badge/%E9%A2%98%E5%9B%BE-%E6%9C%AC%E5%9C%B0%E5%AD%98%E5%82%A8-475569?style=for-the-badge"></a>
  <a href="https://github.com/ProfessorZhi/gwy-zhenti/issues/new?template=erratum.yml"><img alt="勘误 欢迎提交" src="https://img.shields.io/badge/%E5%8B%98%E8%AF%AF-%E6%AC%A2%E8%BF%8E%E6%8F%90%E4%BA%A4-7c3aed?style=for-the-badge"></a>
</p>
<!-- gwy:badges:end -->

<p align="center">
  国家公务员考试与各省公务员考试<b>行测</b>、<b>申论</b>真题的 Markdown 整理本。<br>
  每份试卷一个文件，收录题干、选项、给定材料、题图、参考答案与解析，支持在线阅读、离线使用与程序处理。
</p>

<p align="center">
  <a href="国考/README.md"><b>国考</b></a> &nbsp;·&nbsp;
  <a href="省考/README.md"><b>省考</b></a> &nbsp;·&nbsp;
  <a href="catalog/INDEX.md">试卷索引</a> &nbsp;·&nbsp;
  <a href="docs/COVERAGE.md">收录统计</a> &nbsp;·&nbsp;
  <a href="https://github.com/ProfessorZhi/gwy-zhenti/issues/148">缺口跟踪</a> &nbsp;·&nbsp;
  <a href="#勘误与反馈">勘误</a> &nbsp;·&nbsp;
  <a href="docs/README.md">文档</a>
</p>

<br>

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>📄 整卷收录</h3>
      题干、选项、给定材料、题图、参考答案与解析收录于同一文件，按地区、年份、卷型归档。
    </td>
    <td width="33%" valign="top">
      <h3>🧩 答案随题折叠</h3>
      每道题后附折叠的参考答案与解析，作答后展开；资料分析、申论材料置于对应题目之前。
    </td>
    <td width="33%" valign="top">
      <h3>🔎 来源可追溯</h3>
      文件头标注来源链接、源试卷编号与采集时间；缺失内容保留题位并明确标注。
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>🖼️ 离线可用</h3>
      题图与试卷存放于同一目录，以相对路径引用，克隆后无需联网即可完整显示。
    </td>
    <td valign="top">
      <h3>🗂️ 结构化清单</h3>
      <a href="catalog/manifest.jsonl"><code>manifest.jsonl</code></a> 逐卷记录题量、图片数与 SHA-256，便于检索、统计与校验。
    </td>
    <td valign="top">
      <h3>🤝 开放勘误</h3>
      欢迎任何读者指出错误或补充来源，勘误经核对后更新，处理结果公开记录。
    </td>
  </tr>
</table>

## 目录

- [浏览试卷](#浏览试卷)
- [试卷格式](#试卷格式)
- [收录情况](#收录情况)
- [缺口](#缺口)
- [勘误与反馈](#勘误与反馈)
- [仓库结构](#仓库结构)
- [版权与免责声明](#版权与免责声明)

## 浏览试卷

选择地区后进入该地区的逐年卷表。标有 <sup>缺N</sup> 的试卷含 N 个来源未收录的题位。

<!-- gwy:regions:start -->
**[国考](国考/README.md)** 77 份 ｜ **[省考总览](省考/README.md)** ｜ [全部试卷索引](catalog/INDEX.md)

| 区域 | 地区（试卷份数） |
| --- | --- |
| **华东** | [浙江](省考/浙江/) 83 · [江苏](省考/江苏/) 94 · [上海](省考/上海/) 69 · [安徽](省考/安徽/) 66 · [福建](省考/福建/) 50 · [江西](省考/江西/) 57 · [山东](省考/山东/) 61 |
| **华北** | [北京](省考/北京/) 45 · [天津](省考/天津/) 52 · [河北](省考/河北/) 53 · [山西](省考/山西/) 38 · [内蒙古](省考/内蒙古/) 32 |
| **华中 · 华南** | [河南](省考/河南/) 49 · [湖北](省考/湖北/) 50 · [湖南](省考/湖南/) 43 · [广东](省考/广东/) 70 · [广州](省考/广州/) 16 · [深圳](省考/深圳/) 39 · [广西](省考/广西/) 40 · [海南](省考/海南/) 32 |
| **西南** | [重庆](省考/重庆/) 70 · [四川](省考/四川/) 70 · [贵州](省考/贵州/) 36 · [云南](省考/云南/) 35 · [西藏](省考/西藏/) 3 |
| **西北** | [陕西](省考/陕西/) 38 · [甘肃](省考/甘肃/) 30 · [青海](省考/青海/) 32 · [宁夏](省考/宁夏/) 34 · [新疆](省考/新疆/) 28 · [新疆兵团](省考/新疆兵团/) 18 |
| **东北** | [辽宁](省考/辽宁/) 35 · [吉林](省考/吉林/) 57 · [黑龙江](省考/黑龙江/) 59 |
| **其他** | [公安招警和公检法](省考/公安招警和公检法/) 9 |
<!-- gwy:regions:end -->

## 试卷格式

以 [国考 2025 行测地市级](国考/2025/行测-地市级.md) 第 22 题为例（解析有删节）：

> ### 第 22 题
>
> 下列情形不在申请行政复议范围之内的是：
>
> A. 餐馆甲因食品卫生不达标，被吊销餐饮服务许可证，甲不服
>
> B. 建设单位乙在申请建筑工程施工许可证时，因申请材料不全被拒绝，乙不服
>
> C. 公务员丙不能胜任工作，其所属行政机关作出降职处理决定，丙不服
>
> D. 工人丁提出工伤认定申请，当地人力资源和社会保障局作出不予受理决定，丁不服
>
> <details><summary>第 22 题 · 答案与解析</summary>
>
> **参考答案（粉笔题库参考内容）**
>
> C
>
> **解析**
>
> 本题考查法律常识。……根据《中华人民共和国行政复议法》第十二条第三项规定：“下列事项不属于行政复议范围：（三）行政机关对行政机关工作人员的奖惩、任免等决定。”针对公务员丙作出的降职处理决定，不在行政复议范围之内。……本题为选非题，故正确答案为C。
>
> </details>

文件结构与字段说明见 [文档格式](docs/SCHEMA.md)。

## 收录情况

<p align="center">
  <img src="docs/assets/dashboard.svg" alt="收录概览：2016 年以来的收录率、科目构成与缺题" width="100%">
</p>

<!-- gwy:coverage:start -->
共收录 **1,670** 份试卷（行测 736 份、申论 934 份），覆盖 2008–2026 年的国考和 34 个省考地区（含广州、深圳、新疆兵团）。

试卷以粉笔为主要来源，华图和公开网页补充：2016 年以来的试卷中，用到粉笔的 1,232 份、华图 16 份、公开网页 32 份（一份试卷可同时用到多个来源）。每份试卷在文件开头列出实际用到的全部来源。
<!-- gwy:coverage:end -->

<p align="center">
  <img src="docs/assets/papers-by-year.svg" alt="逐年收录的行测、申论试卷数" width="100%">
</p>

分地区、分年份的收录明细见 [收录统计](docs/COVERAGE.md)。

## 缺口

<!-- gwy:gaps:start -->
缺口分两种：**缺卷**指考试举行过、但库里没有这份试卷；**缺题**指试卷已收录、但个别题目的题干、选项或答案不全。

### 重点地区 2016 年以来

国考和九个重点省市 2016 年以来应有 **425** 份试卷，已收录 **412** 份；缺卷 **13** 份，缺题 **94** 道。其中浙江缺卷 **4** 份、缺题 **2** 道。这部分最先补录。

<p align="center"><img src="docs/assets/focus.svg" alt="重点地区 2016–2026 年每份试卷的状态" width="100%"></p>

### 全部地区、全部年份（分四个层次）

| 层次 | 范围 | 应有试卷 | 已收录 | 缺卷 | 缺题 |
| :---: | --- | ---: | ---: | ---: | ---: |
| 一 | 重点地区 2016 年以来 | 425 | 412 | 13 | 94 道（16 份） |
|  | ↳ 其中 ★ 浙江 | 65 | 61 | 4 | 2 道（1 份） |
| 二 | 重点地区 2015 年及以前 | 未统计 | 172 | 未统计 | 未统计 |
|  | ↳ 其中 ★ 浙江 | 未统计 | 22 | 未统计 | 未统计 |
| 三 | 其他地区 2016 年以来 | 889 | 835 | 54 | 164 道（41 份） |
| 四 | 其他地区 2015 年及以前 | 未统计 | 220 | 未统计 | 未统计 |
| **合计** | | 未统计 | **1,639** | 未统计 | 未统计 |

层次即补录顺序，第一层最先，浙江在重点地区中最优先。重点地区为国考、浙江、江苏、上海、北京、天津、广东、广州、深圳、福建。

2016 年以来每份应有试卷都依据当年招录公告登记，数字准确。2015 年及以前每年应有哪些试卷、每份原卷多少题，还没有逐份核对，所以缺卷和缺题暂不统计；目前已发现 22 份早年试卷题量明显偏少，列在缺口总账。

<table><tr><td><sub>←⁠&nbsp;⁠左⁠右⁠滑⁠动⁠查⁠看⁠全⁠部⁠年⁠份⁠&nbsp;⁠·⁠&nbsp;⁠点⁠击⁠图⁠片⁠查⁠看⁠原⁠图⁠&nbsp;⁠→&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</sub><br><a href="docs/assets/health.svg"><img src="docs/assets/health.svg" alt="全部地区 2008–2026 年每份试卷的状态" width="2054"></a></td></tr></table>

以上按不同试卷计数，同一份试卷有多个版本时只算一次；公安招警和公检法等专项收录不计入。另有北京 2025 年行测 18 道题的参考答案可能与题号错位，未计入缺题。逐份清单见 [缺口总账](docs/GAP-STATUS.md)，进展在 [#148](https://github.com/ProfessorZhi/gwy-zhenti/issues/148) 跟踪。
<!-- gwy:gaps:end -->

## 勘误与反馈

本仓库欢迎所有读者提出勘误。错字、错题、参考答案或解析有误、题图缺失、卷别标注错误、排版问题，均可提交。

| 方式 | 说明 |
| --- | --- |
| [提交勘误](https://github.com/ProfessorZhi/gwy-zhenti/issues/new?template=erratum.yml) | 按模板填写试卷、题号、问题类型与依据 |
| 补充来源 | 持有缺失题目、答案或整卷的可靠来源，可在对应的缺口 issue 下提供 |
| 提交修改 | 直接修改试卷 Markdown 并发起 Pull Request |

勘误经核对后更新，处理结果在原 issue 中回复。提交流程与提交说明格式见 [参与贡献](CONTRIBUTING.md)。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `国考/<年份>/<科目>-<卷型>.md` | 国考试卷：副省级、地市级、行政执法 |
| `省考/<地区>/<年份>/<科目>-<卷型>.md` | 省考试卷：A类、B类、统考、县乡卷、选调生等 |
| `…/assets-fenbi-<试卷编号>/` | 该卷题图 |
| [`图片/`](图片/) | 早期整理试卷的题图 |
| [`catalog/`](catalog/) | [试卷索引](catalog/INDEX.md)、逐卷清单 `manifest.jsonl`、槽位台账 `exam-slots.jsonl`（含未收录 `uncollected-slots.jsonl`） |
| [`docs/`](docs/README.md) | 收录统计、缺口总账、文档格式、数据来源、质量标准 |
| [`reports/`](reports/README.md) | 审计、修复与查源记录 |
| [`资料缺失/`](资料缺失/README.md) | 旧版未收录占位索引（已由槽位台账 `catalog/uncollected-slots.jsonl` 取代，仅存档） |
| [`tools/`](tools/README.md) | 统计、导航生成、质量检查与采集脚本 |

广州市考、深圳市考为独立考试序列，与广东省考分列。

<details>
<summary><b>维护命令</b></summary>

```bash
python3 -I tools/refresh_manifest.py --write                # 刷新清单的字节数与 sha256
python3 -I tools/catalog_index.py --out catalog/INDEX.md     # 试卷索引
python3 -I tools/coverage_stats.py --svg docs/assets        # 逐年柱状图、覆盖热力图
python3 -I tools/repo_readmes.py                            # 横幅、徽章、地区入口与各目录导航页
python3 -I tools/gap_report.py                              # 缺口总账与首页缺口表
python3 tools/cloud_quality.py --check --verify-images      # 结构与图片引用检查
python3 tools/source_provenance.py --check                   # 逐卷来源字段核查
python3 tools/source_provenance.py --export /tmp/paper-sources.jsonl # 导出逐卷来源并集
```

采集与入库流程见 [tools/fenbi/README.md](tools/fenbi/README.md)，入库标准见 [归档与质量标准](docs/QUALITY-STANDARD.md)。

</details>

## 版权与免责声明

- 试卷以粉笔整理版本为主要来源，华图与网络检索为补充来源，每份试卷记录实际采用的全部来源；回忆版不代表官方发布原卷，参考答案与解析来自第三方题库，不代表官方答案。
- 本仓库仅供学习与研究使用，不得用于商业用途。
- 试题、答案、解析及图片的著作权归原权利人所有。权利人如认为相关内容侵犯其合法权益，请通过 [issue](https://github.com/ProfessorZhi/gwy-zhenti/issues/new) 联系，核实后将及时处理。
- 来源说明见 [数据来源与许可](docs/SOURCES.md)。
