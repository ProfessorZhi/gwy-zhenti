# 数据来源与覆盖核验

此处只登记**经查看仓库实际目录、README、部分真实数据文件**的候选来源。候选不等于允许全文转载，也不等于已核验、已入库。新增来源先确认是不是现有仓库的 fork、再检查真实数据和版权。

## 一、优先研究的独立数据源

| 来源 | 真正的数据形式 | 可验证的范围与价值 | 风险与取舍 |
| --- | --- | --- | --- |
| [ERRRC/xingcezhenti](https://github.com/ERRRC/xingcezhenti) | **Markdown + 本地 PNG**，按模块和试卷组织，含题干/答案/解析 | README 自报 **2016—2026、515 卷、58,890 题次、39,463 张图**；已抽查 2016 浙江 A 卷正文，图片相对路径、题号和答案存在 | 无明确标准 LICENSE；图片缺失清单含两张公式图片；“官方解析”是源站标签，不能当官方权威认证 |
| [linfukai186-arch/gongkao-tiku](https://github.com/linfukai186-arch/gongkao-tiku) | 按年分片的结构化 **JSON** | 国考行测索引覆盖 **2000—2026**、省考行测索引覆盖 **2004—2025**；尤其用于老年份补缺与卷型对照 | 数据源与二次分发权限待核查；*国考申论索引中的 470 条全部属于名称含模考的卷组*；省考申论也混有真题/模考，不得直接按总数导入 |
| [zzcc-nb/gongkao-tiku](https://github.com/zzcc-nb/gongkao-tiku) | **逐题 Markdown**，包含部分完整材料、参考答案、答题演示 | README 自报 **3,852 道申论题**；实际抽样含完整给定资料、参考答案和讲解，可用于补充申论题型与材料 | **包含 2027 模考**，须严格按考试真实年份、地区、卷别过滤；单题不等于完整试卷；来源说明为粉笔题库，版权限制需要核查 |
| [shiwuooo/shangantong-papers-v2-c1](https://github.com/shiwuooo/shangantong-papers-v2-c1)、[c2](https://github.com/shiwuooo/shangantong-papers-v2-c2) | 每卷 **HTML + assets** | 自述包含国省考历年试卷，可转为可读 Markdown 和图文校验材料 | 同一系列的两个分片，只算**一个独立来源家族**；真实年份及版权、题图完整率尚未统计 |
| [Yaoyuan-Zhang319/AdministrativeAptitudeTest](https://github.com/Yaoyuan-Zhang319/AdministrativeAptitudeTest) | **PDF**（国考、省考、选调分目录） | 已见国考 **2000—** 的历史 PDF，覆盖多个省份，可用于缺卷或争议题原件对照 | **不是 Markdown 源**；只能按缺口定向使用，不执行整库 PDF 重转 |
| [tswcbyy7268/kaogong-10years-exam](https://github.com/tswcbyy7268/kaogong-10years-exam) | **JS 结构化题目 + 原卷图片** | README 自述 2016—2026、27 套国考卷，涵盖资料分析/判断推理，适合关键模块交叉验证 | 只含两个行测模块；作者注明部分为回忆版、无附带 LICENSE |

## 二、派生库 / 辅助库

以下**不应重复计为彼此独立的交叉证据**：

- [ERRRC/kaogongzhentizhengliu](https://github.com/ERRRC/kaogongzhentizhengliu)：两大模块的深度标注知识库（判断推理、资料分析），适合核查解法，不是申论全卷库；原创标注 CC BY-NC 4.0，第三方试题和图片不等于获同样授权。
- [jangviktor-web/GongkaoNaoku](https://github.com/jangviktor-web/GongkaoNaoku)：README 明确称其 27,506 道去重行测源于 ERRRC，**不算第二独立题源**；代码 Apache-2.0 不授予题库内容转载权。
- [ERRRC/kaogong-shuati](https://github.com/ERRRC/kaogong-shuati)：题库 APP，包含行测、申论和 SQLite 数据；README 表明内容仅限个人学习、不允许二次分发。可参考组织形式，不能直接整库并入。
- [HuaXiLF/shenlun-trainer](https://github.com/HuaXiLF/shenlun-trainer)：小规模申论训练语料和方法体系，不是全国申论完整原卷。
- [yshhsy/shenlunxuexi](https://github.com/yshhsy/shenlunxuexi)：国考申论训练 JS，明确采用**浓缩、改写后的给定材料**，不能用来替代原卷全文。
- [shiwuooo/qiushi-shenlun](https://github.com/shiwuooo/qiushi-shenlun)：申论训练站点，含静态前端；真题整卷及材料完整率尚待核实。
- 任何与 [ERRRC/xingcezhenti](https://github.com/ERRRC/xingcezhenti) 同内容的 fork（例如 `r1172464137/xingcezhenti`），仅计版本镜像，不计独立来源。

## 三、覆盖统计的正确口径

首先按 **考试层级 × 地区 × 年份 × 科目 × 卷型** 建立所有“应有试卷”的清单，再判断该格是否有可验证资料。实际年份和卷型根据当年公告确定，不虚构不存在的卷。

每一格记录：

- 找到的不同来源家族数量、原卷是否可核对；
- 题干与选项、申论全部给定资料、图片、答案、解析是否完整；
- 真实考试 / 联考 / 网友回忆 / 模考 / 改写材料的区别；
- 逐卷内容一致性、答案分歧及缺图；
- 版权授权与能否随本仓分发。

**并集决定覆盖率；来源独立性与一致性决定校验信心。** 同题跨省联考共享一道内容记录，同时保留多个地区对应的卷型、原始题号和来源信息。

## 四、当前事实边界

已找到具有潜力的行测正文、申论逐题材料和历史试卷来源，**但没有核实出一个同时覆盖全部省份、全部年份、行测与申论的完整 Markdown 仓库**。尤其申论逐卷完整性仍是最大缺口。

因此当前阶段先审计、筛选、抽样渲染与对照，不宣称“全省全科已经齐全”，也不为制造数量而直接批量复制来源项目。
