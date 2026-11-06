# 远端分支清理快照（2026-11-06）

清理前 GitHub 远端分支 76 个（不含 `main`）。逐个与 `main`（`dd4b3742a`）比较「该分支自分叉点以来改过的文件，当前内容是否与 main 相同」，分三组处理：

| 组 | 数量 | 判定 | 处理 |
| --- | ---: | --- | --- |
| A 已在 main | 21 | 改过的文件与 main 完全相同，或对应 PR 已合并（之后 main 又改过同一批文档） | 删除分支 |
| B 旧历史 | 44 | 与 main 无共同祖先（仓库历史重写前的分支） | 转为标签 `branch-archive/<名>` 后删除分支 |
| C 试验存档 | 10 | 与 main 同源，但有少量 main 中没有的改动（10-21～10-23 的落库试验） | 同 B |
| 保留 | 1 | `claude/funny-turing-p783lb`（加粗修复 PR 进行中） | 不动 |

标签名去掉了原名开头的 `archive/`，例如 `archive/sim-stack-integration` → `branch-archive/sim-stack-integration`。标签与分支指向同一提交，不增加仓库体积；需要时可还原为分支：

```bash
git push origin refs/tags/branch-archive/<名>:refs/heads/<原分支名>
```

执行脚本：[`tools/branch_cleanup_20261106.sh`](../../tools/branch_cleanup_20261106.sh)。默认只打印计划；`--apply` 才执行，且只处理远端 SHA 与下表一致的分支，期间被推送过的分支会跳过。

## A 已在 main（21 个，删除）

| 分支 | SHA | 最后提交 | PR |
| --- | --- | --- | --- |
| `audit/gap-content-20261030` | `e34ff031e7cc6884972ac247770360c3c9b59c67` | 2026-10-30 | #149:merged |
| `audit/quality-spotcheck-20261030` | `8809b4da19f001d57ed4c118c04cf3111ab5f692` | 2026-10-30 | #152:merged |
| `claude/bold-brahmagupta-lkou1e` | `f78be123042e2c2867329db7d91737b3c19cd274` | 2026-11-05 | #180:merged #179:merged #178:merged #177:merged #176:merged #175:merged #174:merged #173:merged #172:merged #171:merged #170:merged #169:merged #168:merged #167:merged #164:merged #154:merged #153:merged #118:merged #105:merged |
| `codex/fill-fujian-2017` | `d97cb5de9cbc7363c39b04ea5ee43ccb827b00bd` | 2026-11-05 | #182:merged |
| `codex/fill-guangdong-2019` | `224e6bf6796097cd0fde2a15598ee9452426baad` | 2026-11-05 | #183:merged |
| `codex/fill-guangxi-2017` | `2cb3fae917fd98c4795e7e23a35d87c3977dd9b4` | 2026-11-06 | #185:merged |
| `codex/fill-jiangsu-2024c-q110` | `55865a8600145217b289aeb0d65cbbec39aa04cc` | 2026-11-05 | #184:merged |
| `codex/fill-jiangsu-2026b-answers` | `4f33a75213a151aef811a74906a04270623bfe98` | 2026-11-06 | #186:merged |
| `codex/fill-shandong-2023-q42` | `69d43fd6e89003f2ee2d365414f1d97f9879a21a` | 2026-11-06 | #189:merged |
| `codex/guard-duplicate-anchors` | `b797bcf6985a0538813cd27796f2e799fd32ee33` | 2026-11-06 | #187:merged |
| `codex/huatu-reviewed-fill` | `67d2f9ac817f66c0f15c3e0f07ba2502bcce8cdb` | 2026-11-06 | #188:merged |
| `docs/all-exam-coverage-20261104` | `5ae14d74413b048a1ec6d0ae3d8806d8f64ccf45` | 2026-11-04 | #165:merged |
| `docs/coverage-image-count-sync-20261030` | `9dd679b3d22876baff2b346e0b99bb9b876e0013` | 2026-10-30 | #150:merged |
| `docs/gap-ledger-reconcile-20261030` | `c9c93552e2f4f299a8f524584458a48f0dfc9a2c` | 2026-10-30 | #147:merged |
| `docs/real-exams-and-source-union-20261104` | `24569e6f92ddc6c0d6b597f041260932a647afa1` | 2026-11-04 | #166:merged |
| `feat/reusable-source-archive` | `d1dae5a50f8fa6d447cff406827cc3bc3613bd9b` | 2026-11-05 | #181:merged |
| `fenbi-integ` | `af24084a900e31ae7f9d03b8e2cf84f796bcb80b` | 2026-10-22 | — |
| `fenbi-integ-l1-20261021` | `99c0d2f30c8f378b93258693c4b728b5951623b2` | 2026-10-21 | — |
| `fenbi/c1-batch2-zj-20261021` | `46f3d83c4400a39cbccd539caac36cd25d582dc6` | 2026-10-21 | — |
| `fenbi/c1-tech-c-20261021` | `e025471c9f200e0b6a75a9b32f0803b1bb9a1917` | 2026-10-21 | — |
| `fix/quality-summary-a1-count-20261030` | `4561ae473e34b2785be39d260ab38127a0a9567e` | 2026-10-30 | #151:merged |

## B / C 转标签（54 个）

| 分支 | 标签 | SHA | 最后提交 | 组 | 与 main 不同的文件数 |
| --- | --- | --- | --- | :---: | ---: |
| `archive/gwy-zhenti-s3-auto-main-draft-20261020` | `branch-archive/gwy-zhenti-s3-auto-main-draft-20261020` | `8d52a2e593c6d258c5b4928f0ae8193474b52792` | 2026-10-21 | B | 96,870 |
| `archive/gwy-zhenti-s3-dev-20261020` | `branch-archive/gwy-zhenti-s3-dev-20261020` | `057fab1dcefe32d5a122bf2772b0cc14bb730627` | 2026-10-20 | B | 96,248 |
| `archive/gwy-zhenti-s3-quality-repair-20261021` | `branch-archive/gwy-zhenti-s3-quality-repair-20261021` | `6660721fe71dc3ffc0c2ae54609ce6518fc04a21` | 2026-10-21 | B | 96,876 |
| `archive/gwy-zhenti-s3-shenlun-dev-20261020` | `branch-archive/gwy-zhenti-s3-shenlun-dev-20261020` | `423c96fe3daba097a58705c3fa3b8bb88c06edb8` | 2026-10-20 | B | 96,248 |
| `archive/gwy-zhenti-s3-shenlun-pr88-20261020` | `branch-archive/gwy-zhenti-s3-shenlun-pr88-20261020` | `62f876a3765a1355e35544ffa5c1656c8f529eae` | 2026-10-20 | B | 96,856 |
| `archive/gwy-zhenti-s3-shenlun-review-20261020` | `branch-archive/gwy-zhenti-s3-shenlun-review-20261020` | `1695b1b46e7453c69618e07fe376b243d49aad76` | 2026-10-20 | B | 96,859 |
| `archive/master-gwy-format-final` | `branch-archive/master-gwy-format-final` | `97590a84d377cb8ccd63a746812303bd0c00c390` | 2026-10-28 | B | 155 |
| `archive/master-gwy-zhenti-longrun` | `branch-archive/master-gwy-zhenti-longrun` | `a88124f5a071b6894e8e13facfc159a2d8bb5fdb` | 2026-10-27 | B | 14 |
| `archive/qa-batch-candidate-20261017-audit` | `branch-archive/qa-batch-candidate-20261017-audit` | `1da2019dab6d1110b9acad9d296664dbe9e1e957` | 2026-10-17 | B | 97,295 |
| `archive/qa-integration-candidate-20261018-audit` | `branch-archive/qa-integration-candidate-20261018-audit` | `c7b5f6fc6f85a852f7521d3b12ccf24e14e9f485` | 2026-10-18 | B | 97,290 |
| `archive/qa-integration-candidate-r2-20261018-audit` | `branch-archive/qa-integration-candidate-r2-20261018-audit` | `8275af75e0f6705aa447cc6165ddd18b0e572f53` | 2026-10-18 | B | 97,289 |
| `archive/qa-release-candidate-20261018-audit` | `branch-archive/qa-release-candidate-20261018-audit` | `6adeab2082ecba20e3d459be75e481d58b6cf28b` | 2026-10-18 | B | 97,291 |
| `archive/qa-stack-candidate-20261018-audit` | `branch-archive/qa-stack-candidate-20261018-audit` | `473b316434ab0a9b57b35c0b4443bd7677b9552f` | 2026-10-18 | B | 97,289 |
| `archive/qa-stack-candidate-with63-20261018-audit` | `branch-archive/qa-stack-candidate-with63-20261018-audit` | `1ca6231749e6119804b065798b0804550decb075` | 2026-10-18 | B | 97,291 |
| `archive/sim-comb-integration` | `branch-archive/sim-comb-integration` | `74fba5dfdc42d8c03f2b4aeca4c5a7a640761b7d` | 2026-10-17 | B | 97,281 |
| `archive/sim-conc-plus-22-integration` | `branch-archive/sim-conc-plus-22-integration` | `c7326e9aafaf1c77e1a063c085f58560326df069` | 2026-10-17 | B | 97,280 |
| `archive/sim-fix-plus-22-integration` | `branch-archive/sim-fix-plus-22-integration` | `1c7df64d818db4a9e1384bb1a17e8dcd9310bd23` | 2026-10-17 | B | 97,280 |
| `archive/sim-integration-21-22-integration` | `branch-archive/sim-integration-21-22-integration` | `9e1539115da3ef2d6249705b829fe5ba94727b77` | 2026-10-17 | B | 97,282 |
| `archive/sim-probe21-integration` | `branch-archive/sim-probe21-integration` | `6d3a471b329bf44afe684491137b7ab8ae6232f8` | 2026-10-17 | B | 97,282 |
| `archive/sim-stack-integration` | `branch-archive/sim-stack-integration` | `d46fd0cf97893d997278d2229c1e622efcf6150b` | 2026-10-17 | B | 97,280 |
| `archive/sim-triple-integration` | `branch-archive/sim-triple-integration` | `72caf36d690fed52d124f73d726b21ca897517a2` | 2026-10-17 | B | 97,282 |
| `audit/fenbi-batch-arithmetic-20261017` | `branch-archive/audit/fenbi-batch-arithmetic-20261017` | `25e1bcb3164cf24c01eeed0d4c6485032ed32179` | 2026-10-17 | B | 97,281 |
| `audit/fenbi-route-fidelity-gate-20261017-r4` | `branch-archive/audit/fenbi-route-fidelity-gate-20261017-r4` | `cae30c129e6122e24bd024db38e2145a11e37464` | 2026-10-17 | B | 97,294 |
| `complete/essay-r9-all-20261013` | `branch-archive/complete/essay-r9-all-20261013` | `33dfb422211963cc9faadce455f170e7944e764e` | 2026-10-13 | B | 96,282 |
| `essay/r11-complete-568` | `branch-archive/essay/r11-complete-568` | `0f806f4e8154e87c0c38c5d5bef0a4294f8a0caf` | 2026-10-13 | B | 96,464 |
| `feat/essay-all-738-reference-20261013` | `branch-archive/feat/essay-all-738-reference-20261013` | `8b97f5a3a887e833d21077be30a40ed1074beb1d` | 2026-10-12 | B | 96,159 |
| `feat/fenbi-batch-ingest-20261018` | `branch-archive/feat/fenbi-batch-ingest-20261018` | `1db61be643069c6f6d67f73c0ddbf5a388f1557b` | 2026-10-18 | B | 97,383 |
| `feat/m1-merge` | `branch-archive/feat/m1-merge` | `6dabfd7c53b7bf17e93ae5aa5aa9d359fc5c51d0` | 2026-10-11 | B | 96,135 |
| `fix/anhui2018A-references-r9-20261013` | `branch-archive/fix/anhui2018A-references-r9-20261013` | `8c23683610441d82836b907e20c586f2b4622646` | 2026-10-13 | B | 96,159 |
| `fix/essay-priority-references-r8-20261013` | `branch-archive/fix/essay-priority-references-r8-20261013` | `dcf92692b2791b9b61a39dbaed8408b58736d09b` | 2026-10-13 | B | 96,156 |
| `fix/essay-priority-refs-r8-rebased-20261013` | `branch-archive/fix/essay-priority-refs-r8-rebased-20261013` | `adac256127b1cd90086436ed91e4a47cb46150ce` | 2026-10-12 | B | 96,158 |
| `fix/essay-reference-r7-20261013` | `branch-archive/fix/essay-reference-r7-20261013` | `9cc7c0cca5b984b25ea9804ab7e474c1896b746e` | 2026-10-13 | B | 96,153 |
| `fix/f8-residual-caption-image-20261018` | `branch-archive/fix/f8-residual-caption-image-20261018` | `29250d2eea08969fe7fcc6ac5f911c8b8a2d6183` | 2026-10-18 | B | 97,281 |
| `fix/fenbi-observation-title-failclosed-20261017` | `branch-archive/fix/fenbi-observation-title-failclosed-20261017` | `4baf6aba3983a9a9295c814dee2e936b956fcade` | 2026-10-17 | B | 97,289 |
| `fix/priority-completion-20261012` | `branch-archive/fix/priority-completion-20261012` | `82b685931bc6f0eedb629e812b733624635f3b1c` | 2026-10-12 | B | 96,145 |
| `fix/priority-source-r3-20261012` | `branch-archive/fix/priority-source-r3-20261012` | `6889c9672c52db6359301c55135aefd3f7b18d84` | 2026-10-12 | B | 96,164 |
| `fix/r6-essay-references-20261013` | `branch-archive/fix/r6-essay-references-20261013` | `b6309f34636b0e3285e50fc01e8df1b750ecf280` | 2026-10-13 | B | 96,156 |
| `qa/shard-js-zj-20261018` | `branch-archive/qa/shard-js-zj-20261018` | `41a8d8cd9af3621e5529e4d9cdb66a7e96121551` | 2026-10-18 | B | 97,285 |
| `repair/20261012-r3-gap-layout` | `branch-archive/repair/20261012-r3-gap-layout` | `e66ce8e316d4ca7f883bba649dc7b56cd23f5872` | 2026-10-12 | B | 96,156 |
| `rescue/dell-gwy-zhenti-fenbi-combo` | `branch-archive/rescue/dell-gwy-zhenti-fenbi-combo` | `b4c5dc8797e76af917444c21b1072ad2f8495d3b` | 2026-10-19 | B | 561 |
| `rescue/dell-gwy-zhenti-fenbi-s2-batch-ingest` | `branch-archive/rescue/dell-gwy-zhenti-fenbi-s2-batch-ingest` | `ada9b4d132c587055caadd1cd38999759bbddf86` | 2026-10-19 | B | 2,073 |
| `rescue/dell-gwy-zhenti-integration-20261017` | `branch-archive/rescue/dell-gwy-zhenti-integration-20261017` | `ffb91d0a2811ba3273cc21cbc9436afdcb80fdc1` | 2026-10-19 | B | 614 |
| `rescue/dell-gwy-zhenti-throughput-gittrial` | `branch-archive/rescue/dell-gwy-zhenti-throughput-gittrial` | `3ee4eb417bcf564454e82525e074a937d8485c44` | 2026-10-18 | B | 96,189 |
| `rescue/windows-gwy-verify` | `branch-archive/rescue/windows-gwy-verify` | `6dabfd7c53b7bf17e93ae5aa5aa9d359fc5c51d0` | 2026-10-11 | B | 96,135 |
| `archive/c2-offline-decode-idx-20261021-c2-scratch` | `branch-archive/c2-offline-decode-idx-20261021-c2-scratch` | `156d2f8bc987a10b25f26f201a1d67bf1ab174f9` | 2026-10-22 | C | 4 |
| `archive/fenbi-ingest-20261023-s1-l1` | `branch-archive/fenbi-ingest-20261023-s1-l1` | `e047d7b5ce04f6cbff0ad71d5a063d7d16738d1e` | 2026-10-23 | C | 17 |
| `archive/fenbi-integ-l1-20261021-s1-l1` | `branch-archive/fenbi-integ-l1-20261021-s1-l1` | `252e77917dd0fd65b2d5875096fbdf5749c00380` | 2026-10-23 | C | 1,709 |
| `archive/fenbi-landing-trial-2-s1-trial-104` | `branch-archive/fenbi-landing-trial-2-s1-trial-104` | `c741fafc10de59504e04f1596de6069159e9c911` | 2026-10-21 | C | 854 |
| `archive/fenbi-landing-trial-s1-trial-104` | `branch-archive/fenbi-landing-trial-s1-trial-104` | `6f0d73a5bbedee1946f9d406e96a490cb370b080` | 2026-10-21 | C | 854 |
| `archive/fix-fenbi-b1-8papers-20261022-s8-shenlun-land` | `branch-archive/fix-fenbi-b1-8papers-20261022-s8-shenlun-land` | `5072446ac287ec8010d97176cda8fbe8533f03f1` | 2026-10-22 | C | 12 |
| `archive/fix-stale-regression-tests-s1-l1` | `branch-archive/fix-stale-regression-tests-s1-l1` | `11865b37818810aa0f06dc99428fff8ab803fd89` | 2026-10-23 | C | 2 |
| `archive/gwy-zhenti-consolidate-20261021` | `branch-archive/gwy-zhenti-consolidate-20261021` | `4757813b58bf757264a726938b0e1e0d632230d9` | 2026-10-21 | C | 5 |
| `archive/integrate-fenbi-both-20261022-af24084a9-s8-shenlun-land` | `branch-archive/integrate-fenbi-both-20261022-af24084a9-s8-shenlun-land` | `edfd56693cb59b06d947b1fce5e1aaa8d102b6a7` | 2026-10-22 | C | 15 |
| `archive/integrate-fenbi-both-b3-20261022-s8-shenlun-land` | `branch-archive/integrate-fenbi-both-b3-20261022-s8-shenlun-land` | `32fd799787a37fe946764a574232b24cd9d5ede4` | 2026-10-22 | C | 172 |
