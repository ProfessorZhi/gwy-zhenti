# 92 卷分层抽样计划（AI 辅助阅读，不是人工 L3 验收）

## 口径

- 抽样框：GitHub `main` = `efea30030300e7bebcff6fbc05802a2ba3893a43` 的 1850 份正式试卷 Markdown。
- 固定种子 **20261028**，脚本 `select.py`（可复跑，结果 `sample.jsonl` 逐字节稳定）。
- 分层：地区 × 科目为主层（70 层），层内按 **source_validation bucket** 配额、再按年份均匀取；每层优先取 1 份高风险卷（error×10 + warn×3 + review）。
- 16 份为强制入样：8 份任务点名案例 + 8 份高风险模板/来源状态案例（下表 `mand`）。
- 规模：**92 份**，等于目标 92（±10% 区间 83–101 内）。

## 覆盖率（样本 vs 全库）

| 维度 | 全库 | 样本 |
|---|---:|---:|
| 卷数 | 1850 | 92 |
| 地区 | 36 | 36 |
| 年份 | 19 | 16 |
| 地区×科目 层 | 70 | 70 |
| 科目 行测 | 742 | 45 |
| 科目 申论 | 1108 | 47 |
| 校验 candidate | 1644 | 82 |
| 校验 machine | 200 | 8 |
| 校验 other | 6 | 2 |
| 来源 SOURCE_COMPLETE | 1474 | 63 |
| 来源 PARTIAL | 153 | 15 |
| 来源 MISSING | 14 | 3 |
| 来源 CONFLICT | 11 | 1 |
| 来源 (none) | 198 | 10 |
| 有 review 的卷 | 259 | 38 |
| 含占位(PH001)的卷 | 84 | 6 |

年份覆盖：2008、2009、2010、2012、2013、2014、2015、2016、2017、2018、2019、2020、2023、2024、2025、2026

未进入样本的年份：2011、2021、2022（92 份配额下按层内年份均匀取，未覆盖属配额限制，不代表这些年份不审）。

## 强制入样（16）

| # | 卷 | 理由 |
|---:|---|---|
| 1 | `国考/2008/行测-统考.md` | risk:选项在表格行/OP005 |
| 3 | `国考/2016/申论-副省级.md` | named:2016国考申论副省 |
| 6 | `省考/上海/2017/行测-统考.md` | named:上海2017行测解析算式 |
| 11 | `省考/云南/2026/行测-统考.md` | risk:占位卷PH001 |
| 17 | `省考/北京/2023/行测-统考.md` | named:北京2023行测缺题占位 |
| 18 | `省考/北京/2026/申论-选调生.md` | named:R1唯一额外</u> |
| 37 | `省考/广东/2016/行测-广州市考.md` | risk:mixed-level |
| 49 | `省考/江苏/2012/申论-统考.md` | risk:SOURCE_MISSING |
| 50 | `省考/江苏/2012/行测-B类.md` | risk:同行选项OP001 |
| 52 | `省考/江苏/2024/行测-C类.md` | risk:mixed-level130题 |
| 53 | `省考/江苏/2025/申论-C卷.md` | named:江苏2025C材料1-4 |
| 60 | `省考/河南/2018/申论-统考.md` | named:历史R7无折叠 |
| 63 | `省考/浙江/2023/申论-A类.md` | named:浙江2023A文章分析 |
| 76 | `省考/西藏/2016/行测-统考.md` | risk:SOURCE_CONFLICT |
| 88 | `省考/青海/2014/行测-统考.md` | named:青海2014绝对值竖线 |
| 92 | `省考/黑龙江/2019/行测-边境县-shangantong.md` | risk:qid-h2模板 |

## 全部 92 份（按路径排序）

| # | 角色 | 地区 | 年份 | 科目 | 卷型 | 来源状态 | 路径 |
|---:|---|---|---|---|---|---|---|
| 1 | mandatory | 国考 | 2008 | 行测 | 统考 | SOURCE_COMPLETE | `国考/2008/行测-统考.md` |
| 2 | stratum | 国考 | 2009 | 申论 | 副省级 | MISSING | `国考/2009/申论-副省级.md` |
| 3 | mandatory | 国考 | 2016 | 申论 | 副省级 | SOURCE_COMPLETE | `国考/2016/申论-副省级.md` |
| 4 | stratum | 国考 | 2024 | 行测 | 地市级 | SOURCE_COMPLETE | `国考/2024/行测-地市级.md` |
| 5 | stratum | 上海 | 2008 | 申论 | 统考 | SOURCE_COMPLETE | `省考/上海/2008/申论-统考.md` |
| 6 | mandatory | 上海 | 2017 | 行测 | 统考 | 无源ID | `省考/上海/2017/行测-统考.md` |
| 7 | stratum | 上海 | 2020 | 申论 | 行政执法卷 | 无源ID | `省考/上海/2020/申论-行政执法卷.md` |
| 8 | stratum | 上海 | 2023 | 行测 | A类 | SOURCE_COMPLETE | `省考/上海/2023/行测-A类.md` |
| 9 | stratum | 云南 | 2009 | 行测 | 统考 | SOURCE_COMPLETE | `省考/云南/2009/行测-统考.md` |
| 10 | stratum | 云南 | 2013 | 申论 | 统考 | PARTIAL | `省考/云南/2013/申论-统考.md` |
| 11 | mandatory | 云南 | 2026 | 行测 | 统考 | SOURCE_COMPLETE | `省考/云南/2026/行测-统考.md` |
| 12 | stratum | 公安招警和公检法 | 2016 | 申论 | 政法干警（专科类） | SOURCE_COMPLETE | `省考/公安招警和公检法/2016/申论-政法干警（专科类）.md` |
| 13 | stratum | 内蒙古 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/内蒙古/2012/申论-统考.md` |
| 14 | stratum | 内蒙古 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/内蒙古/2016/行测-统考.md` |
| 15 | stratum | 北京 | 2008 | 申论 | 应届 | SOURCE_COMPLETE | `省考/北京/2008/申论-应届.md` |
| 16 | stratum | 北京 | 2012 | 行测 | 统考 | SOURCE_COMPLETE | `省考/北京/2012/行测-统考.md` |
| 17 | mandatory | 北京 | 2023 | 行测 | 统考 | PARTIAL | `省考/北京/2023/行测-统考.md` |
| 18 | mandatory | 北京 | 2026 | 申论 | 选调生 | PARTIAL | `省考/北京/2026/申论-选调生.md` |
| 19 | stratum | 吉林 | 2008 | 行测 | 乙级 | SOURCE_COMPLETE | `省考/吉林/2008/行测-乙级.md` |
| 20 | stratum | 吉林 | 2010 | 申论 | 甲级 | PARTIAL | `省考/吉林/2010/申论-甲级.md` |
| 21 | stratum | 四川 | 2012 | 申论 | 上半年 | SOURCE_COMPLETE | `省考/四川/2012/申论-上半年.md` |
| 22 | stratum | 四川 | 2017 | 申论 | 下半年 | 无源ID | `省考/四川/2017/申论-下半年.md` |
| 23 | stratum | 四川 | 2017 | 行测 | 下半年 | SOURCE_COMPLETE | `省考/四川/2017/行测-下半年.md` |
| 24 | stratum | 天津 | 2009 | 行测 | 统考 | SOURCE_COMPLETE | `省考/天津/2009/行测-统考.md` |
| 25 | stratum | 天津 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/天津/2012/申论-统考.md` |
| 26 | stratum | 宁夏 | 2013 | 申论 | 统考 | PARTIAL | `省考/宁夏/2013/申论-统考.md` |
| 27 | stratum | 宁夏 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/宁夏/2016/行测-统考.md` |
| 28 | stratum | 安徽 | 2008 | 申论 | 统考 | SOURCE_COMPLETE | `省考/安徽/2008/申论-统考.md` |
| 29 | stratum | 安徽 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/安徽/2016/行测-统考.md` |
| 30 | stratum | 山东 | 2009 | 申论 | 统考 | SOURCE_COMPLETE | `省考/山东/2009/申论-统考.md` |
| 31 | stratum | 山东 | 2018 | 申论 | B类 | SOURCE_COMPLETE | `省考/山东/2018/申论-B类.md` |
| 32 | stratum | 山东 | 2024 | 行测 | 统考 | SOURCE_COMPLETE | `省考/山东/2024/行测-统考.md` |
| 33 | stratum | 山西 | 2015 | 申论 | 统考 | PARTIAL | `省考/山西/2015/申论-统考.md` |
| 34 | stratum | 山西 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/山西/2016/行测-统考.md` |
| 35 | stratum | 广东 | 2008 | 申论 | 上半年 | SOURCE_COMPLETE | `省考/广东/2008/申论-上半年.md` |
| 36 | stratum | 广东 | 2016 | 申论 | 单卷 | 无源ID | `省考/广东/2016/申论-广州市考.md` |
| 37 | mandatory | 广东 | 2016 | 行测 | 统考 | 无源ID | `省考/广东/2016/行测-广州市考.md` |
| 38 | stratum | 广东 | 2018 | 行测 | 县级、乡镇统一卷 | SOURCE_COMPLETE | `省考/广东/2018/行测-县级、乡镇统一卷.md` |
| 39 | stratum | 广州 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/广州/2012/申论-统考.md` |
| 40 | stratum | 广州 | 2012 | 行测 | 统考 | SOURCE_COMPLETE | `省考/广州/2012/行测-统考.md` |
| 41 | stratum | 广西 | 2008 | 行测 | 统考 | SOURCE_COMPLETE | `省考/广西/2008/行测-统考.md` |
| 42 | stratum | 广西 | 2013 | 申论 | 统考 | SOURCE_COMPLETE | `省考/广西/2013/申论-统考.md` |
| 43 | stratum | 新疆 | 2015 | 申论 | 统考 | SOURCE_COMPLETE | `省考/新疆/2015/申论-统考.md` |
| 44 | stratum | 新疆 | 2016 | 行测 | 兵团 | SOURCE_COMPLETE | `省考/新疆/2016/行测-兵团.md` |
| 45 | stratum | 新疆兵团 | 2015 | 申论 | 统考 | PARTIAL | `省考/新疆兵团/2015/申论-统考.md` |
| 46 | stratum | 江苏 | 2008 | 申论 | 统考 | SOURCE_COMPLETE | `省考/江苏/2008/申论-统考.md` |
| 47 | stratum | 江苏 | 2008 | 行测 | A类 | SOURCE_COMPLETE | `省考/江苏/2008/行测-A类.md` |
| 48 | stratum | 江苏 | 2009 | 行测 | B类 | SOURCE_COMPLETE | `省考/江苏/2009/行测-B类.md` |
| 49 | mandatory | 江苏 | 2012 | 申论 | 统考 | MISSING | `省考/江苏/2012/申论-统考.md` |
| 50 | mandatory | 江苏 | 2012 | 行测 | B类 | SOURCE_COMPLETE | `省考/江苏/2012/行测-B类.md` |
| 51 | stratum | 江苏 | 2016 | 申论 | 统考 | 无源ID | `省考/江苏/2016/申论-统考.md` |
| 52 | mandatory | 江苏 | 2024 | 行测 | C类 | 无源ID | `省考/江苏/2024/行测-C类.md` |
| 53 | mandatory | 江苏 | 2025 | 申论 | C卷 | SOURCE_COMPLETE | `省考/江苏/2025/申论-C卷.md` |
| 54 | stratum | 江西 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/江西/2012/申论-统考.md` |
| 55 | stratum | 江西 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/江西/2016/行测-统考.md` |
| 56 | stratum | 河北 | 2008 | 申论 | 统考 | SOURCE_COMPLETE | `省考/河北/2008/申论-统考.md` |
| 57 | stratum | 河北 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/河北/2016/行测-统考.md` |
| 58 | stratum | 河南 | 2012 | 申论 | 下半年 | SOURCE_COMPLETE | `省考/河南/2012/申论-下半年.md` |
| 59 | stratum | 河南 | 2016 | 行测 | 选调生 | SOURCE_COMPLETE | `省考/河南/2016/行测-选调生.md` |
| 60 | mandatory | 河南 | 2018 | 申论 | 统考 | 无源ID | `省考/河南/2018/申论-统考.md` |
| 61 | stratum | 浙江 | 2008 | 申论 | 统考 | SOURCE_COMPLETE | `省考/浙江/2008/申论-统考.md` |
| 62 | stratum | 浙江 | 2012 | 行测 | 统考 | SOURCE_COMPLETE | `省考/浙江/2012/行测-统考.md` |
| 63 | mandatory | 浙江 | 2023 | 申论 | A类 | PARTIAL | `省考/浙江/2023/申论-A类.md` |
| 64 | stratum | 海南 | 2014 | 申论 | 统考 | PARTIAL | `省考/海南/2014/申论-统考.md` |
| 65 | stratum | 海南 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/海南/2016/行测-统考.md` |
| 66 | stratum | 深圳 | 2008 | 行测 | 统考 | SOURCE_COMPLETE | `省考/深圳/2008/行测-上半年.md` |
| 67 | stratum | 深圳 | 2014 | 申论 | 统考 | PARTIAL | `省考/深圳/2014/申论-统考.md` |
| 68 | stratum | 湖北 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/湖北/2012/申论-统考.md` |
| 69 | stratum | 湖北 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/湖北/2016/行测-统考.md` |
| 70 | stratum | 湖南 | 2012 | 申论 | 统考 | MISSING | `省考/湖南/2012/申论-统考.md` |
| 71 | stratum | 湖南 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/湖南/2016/行测-统考.md` |
| 72 | stratum | 甘肃 | 2009 | 行测 | 统考 | SOURCE_COMPLETE | `省考/甘肃/2009/行测-统考.md` |
| 73 | stratum | 甘肃 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/甘肃/2012/申论-统考.md` |
| 74 | stratum | 福建 | 2012 | 申论 | 上半年 | SOURCE_COMPLETE | `省考/福建/2012/申论-上半年.md` |
| 75 | stratum | 福建 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/福建/2016/行测-统考.md` |
| 76 | mandatory | 西藏 | 2016 | 行测 | 统考 | CONFLICT | `省考/西藏/2016/行测-统考.md` |
| 77 | stratum | 西藏 | 2019 | 申论 | 统考 | 无源ID | `省考/西藏/2019/申论-统考.md` |
| 78 | stratum | 西藏 | 2019 | 行测 | 统考 | SOURCE_COMPLETE | `省考/西藏/2019/行测-统考.md` |
| 79 | stratum | 贵州 | 2008 | 行测 | 统考 | SOURCE_COMPLETE | `省考/贵州/2008/行测-统考.md` |
| 80 | stratum | 贵州 | 2014 | 申论 | 统考 | PARTIAL | `省考/贵州/2014/申论-统考.md` |
| 81 | stratum | 辽宁 | 2013 | 申论 | 统考 | PARTIAL | `省考/辽宁/2013/申论-统考.md` |
| 82 | stratum | 辽宁 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/辽宁/2016/行测-统考.md` |
| 83 | stratum | 重庆 | 2014 | 申论 | 上半年 | PARTIAL | `省考/重庆/2014/申论-上半年.md` |
| 84 | stratum | 重庆 | 2017 | 行测 | 下半年 | SOURCE_COMPLETE | `省考/重庆/2017/行测-下半年.md` |
| 85 | stratum | 陕西 | 2012 | 申论 | 统考 | SOURCE_COMPLETE | `省考/陕西/2012/申论-统考.md` |
| 86 | stratum | 陕西 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/陕西/2016/行测-统考.md` |
| 87 | stratum | 青海 | 2014 | 申论 | 统考 | PARTIAL | `省考/青海/2014/申论-统考.md` |
| 88 | mandatory | 青海 | 2014 | 行测 | 统考 | SOURCE_COMPLETE | `省考/青海/2014/行测-统考.md` |
| 89 | stratum | 青海 | 2016 | 行测 | 统考 | SOURCE_COMPLETE | `省考/青海/2016/行测-统考.md` |
| 90 | stratum | 黑龙江 | 2014 | 申论 | 统考 | PARTIAL | `省考/黑龙江/2014/申论-统考.md` |
| 91 | stratum | 黑龙江 | 2016 | 行测 | 公检法 | SOURCE_COMPLETE | `省考/黑龙江/2016/行测-公检法.md` |
| 92 | mandatory | 黑龙江 | 2019 | 行测 | 边境县 | 无源ID | `省考/黑龙江/2019/行测-边境县-shangantong.md` |

## 阅读强度分配

- **完整 AI 辅助阅读评析**：40 份（16 份强制 + 24 份按层抽取），逐题读题干/选项/答案开头/解析开头、材料每节、表格、图片引用与折叠逻辑。
- **结构 + 高风险节点深核**：其余 52 份，逐卷核结构、导航、答案折叠与基线标记行，抽 3 题读全文。
- 无论哪种强度，**公式/图片内容一律标 NEEDS_VISUAL_IMAGE**，不臆测未载入的原图。

