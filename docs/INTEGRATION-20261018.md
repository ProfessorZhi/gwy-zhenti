# 集成候选 2026-10-18：64 个开放 PR 合成一棵树

- 基础：#20 `codex/shenlun-full-repair-20261015`（e1feb518）
- 方法：64 个 PR 中有 24 个是别的 PR 的基础分支，只需按顺序 `--no-ff` 合入其余 40 个"栈顶"PR；合完逐一用 `git merge-base --is-ancestor` 复核，**64/64 的 head 都已包含**。
- 本分支**不是** main，也没有关闭或改动任何原 PR。原 PR 是否关闭由仓库所有者决定。

## 冲突与处理（共 6 处，其余 34 个无冲突）

| PR | 文件 | 处理 |
|---|---|---|
| #42 | `tools/fenbi/src/align.mjs` | 保留 HEAD 的 `targetBySource.set`；`matched.add` 按 #42 移到"可比内容"判定之后 |
| #45 | `align.mjs` / `validate.mjs` / 两个测试 | 两边新增内容并存；`compareText` 中先判征集占位，再判图片型内容 |
| #76 | `pipeline/src/identity.mjs`、`observation.mjs` | 采用 #76 栈（#55→#58→#61→#65→#76）。它的 `urlMatchesObserved` 已涵盖 #59 的"路由参数丢失即拒收" |
| #71 / #62 / #83 | `.github/workflows/fenbi-framework.yml` | 测试清单改为运行除 `browser-smoke` 外的全部 `test/*.test.mjs` |

另：`pipeline/test/collector.test.mjs` 的 429 退避用例在 #76 原分支上就失败（测试退避只有 10ms，比运行时间短，断言 `> Date.now()` 必败）。已改为与运行开始时间比较，被测代码未改。

## 本地测试（本树）

| 套件 | 结果 |
|---|---|
| `tools/fenbi` 离线测试（除 browser-smoke） | 208/208 通过 |
| `tools/fenbi/pipeline` | 72/72 通过 |
| `tools/tests`（Python） | 427 个，5 个失败/错误，**与 #20 基础分支完全相同**（round10 深圳 3 项、source_continuation 1 项、sourced_supplement 1 项）；新增的 58 个全部通过 |
| 其余新增 Python 测试（assetsqa / audit / qa / answer_*） | 全部通过 |

browser-smoke 需要真实浏览器和粉笔账号，本环境未运行；GitHub Actions 未验证。
