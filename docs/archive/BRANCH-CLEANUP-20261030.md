# 远端与本地分支清理快照（2026-10-30）

清理前 GitHub 远端分支 181 个（不含 `main`），删除 **121 个**：PR 已 MERGED 39 个、已 CLOSED 82 个；
保留无关联 PR 的 59 个 `archive/*`、`audit/*` 等历史分支，以及当时唯一有 open PR 的分支。
本地同时删除 4 个 PR 已合并的遗留分支。

GitHub 删除的分支在仓库 GC 之前仍可按 SHA 取回；分支对象被回收后，只能靠下面的名↔SHA 对照表还原：

```bash
git push origin <SHA>:refs/heads/<分支名>
```

## 远端（121 个）

| 分支 | SHA |
| --- | --- |
| `assetsqa/metadata-provenance-r7-20261018` | `70a06f91c70a385a9baf161b325bcad297879dff` |
| `assetsqa/pr62-pr63-crosscheck-r5-20261018` | `0fe6128bb49043cc636aeaab9bb9a468f2c594e1` |
| `assetsqa/q31-matrix-validator-r4-20261017` | `f2958eb4e7d471a976fdcb32c78a0e45ab9347c6` |
| `assetsqa/r8-pr63-72-74-qa` | `105c9ec4cf85232f9a5b04f0cf90e25aabc9e4a8` |
| `assetsqa/retest-pr62-63-65-r6-20261018` | `1f141ee0b209fd77d706743e48b44dd10fe6053c` |
| `assetsqa/tile-pilot-r3-20261017` | `ae0372815c7eb71c29ba6965f55f8bd7bee77156` |
| `assetsqa/visual-consistency-20261017` | `44eb61d217d78684cf2f49e60d4a5987c90b79b2` |
| `assetsqa/visual-consistency-r2-20261017` | `2117cc44ec39682b32c4fe688f185fa3c721a953` |
| `audit/answer-provenance-coverage-20261017` | `25ca5c9e93817c845197a0c0dd5506ce7008dd15` |
| `audit/answer-provenance-markers-20261017` | `372d54133ea4e6a9acfa07bb97eefa3a26e308f7` |
| `audit/answer-source-index-20261018` | `cd161dd1ac4c69a996e2f328e479c6f85ba0f6a2` |
| `audit/coverage-matrix-qa-20261017` | `a90e2684b2d4c6139c8d3713530db7bb54bc4a93` |
| `audit/fenbi-first5-metadata-accounting-20261018` | `4b97412e7635af2d721a180a93729ae0826c9dbd` |
| `audit/fenbi-target-inventory-20261017` | `fd4f2e399300eae8b8f298a2ab2e09be6357a005` |
| `audit/fix-spurious-crlf-receipt-20261017` | `d859faf76478ce9d1dcc056eb9eed9c4a6e17f2f` |
| `audit/gap-traceability-20261018` | `31ca946d192a24229591d30ca11e7e7dce85ed52` |
| `audit/js2026a-missing42-source-20261017` | `a3cfdd4092612c7561c4d3366e78dad92dab5f7e` |
| `audit/missing11-evidence-pack-20261017` | `45042ddca443cf8376f1294ae2e6ec8808ae39fd` |
| `audit/missing25-evidence-20261017` | `c0401ff567a122434b796c95d89999b6e34410df` |
| `audit/partitioned-gap-table-20261018` | `3678c81e13108313271f7fe32bcbe8240c112b50` |
| `audit/release-readiness-20261017` | `ed4f42b20ea498a4d96e23fb45744387bf315e07` |
| `audit/three-paper-matrix-20261017` | `12be252b5b58d617d215f8c7a5125a9adec8c2fb` |
| `beijing2026-crosscheck-20261018` | `32e9deeadd5f6fc00edcdd660bca33123ebc30a1` |
| `beijing2026-source-20261017` | `41feb72c74a81e08e2348c363fe2fea16ff36595` |
| `c2/partial-js2024-20261022` | `93742ee2aba390b454ef2d16cfc6848e76efb0f8` |
| `claude/bold-brahmagupta-lkou1e` | `2d967f6f4f2ed61397b01deb9053a98f1d30a2c6` |
| `claude/happy-cori-vazc9x` | `d5bb287010c4c0da8ed8608233f3c8b1767258a3` |
| `cleanup/remove-legacy-ai-20261022` | `4a099902009247f4f3b6d2ab13193841a7a1a8ba` |
| `cleanup/remove-llm-answers-20261022` | `c2c57ffc289d41722ec161b446cf30ca274088f0` |
| `codex/shenlun-full-repair-20261015` | `e1feb5187ec3544cde62a1a128a6269a8d63011b` |
| `consolidate/quality-pipeline-20261021` | `4757813b58bf757264a726938b0e1e0d632230d9` |
| `content/e4-seven-provinces-20261022` | `134b3b457a14ee8ec18dc59e50d6b11f78db49c3` |
| `docs/progress-20261011` | `35bbb01ce69e6bba7fd611c36db59c503e2a711b` |
| `docs/r5-audit-clarity-20261013` | `9b8c343c4f2d122a630c0264a535073682d9af4e` |
| `docs/unified-archive-quality-20261027` | `81c1e1facbd16a519d9683733c8b1723ef60ce8b` |
| `e5/nw-shenlun-original-answers-20261022` | `0a61eb157e57a7bcef65b31948d331e794dc50b3` |
| `essay/r10-shenzhen-2025` | `482ec364b5a2664f352503c11bf69bb8790a57c6` |
| `essay/source-search-all-20261013` | `f9c7c37b1b1d8afd87ef724424a97fe2c4fad4ab` |
| `essay/sourced-supplement-20261013` | `84d987bea6eae63a749a069c9bf8e4f306fea888` |
| `evidence/shenlun-completeness-20261017` | `b62ad54afd67263622db5869f9f28e9a051ec117` |
| `evidence/shenlun-label-triage-20261018` | `472ccf3db5d89f1b5cb49ef100021803416bcaff` |
| `evidence/shenlun-source-recovery-20261017` | `1559eb268f66050bc1bf514dc51835e89ecb7557` |
| `feat/essay-r8-original-examples-20261013` | `defced90cc96e15a123648f10510d57bf3c72e62` |
| `feat/essay-r9-more-complete-20261013` | `18393b2f4dc89df2ee4f666a6bc9e3710190e64f` |
| `feat/fenbi-answer-evidence-qa-20261017` | `74ad18a1916a2e3b2f253cbfb546c9b12392736a` |
| `feat/fenbi-bounded-concurrency-20261017` | `a019daad0a7c08eb83bbef9b71cb288b0ed13426` |
| `feat/formula-transcription-wave1` | `cdadb01626ed0a3784bb914ee4cda4ca9dccfb12` |
| `feat/incremental-mapping-validator-20261018` | `3f733da44a265a7615df8f053065b4b7d2912f1c` |
| `feat/offline-qa-handoff-20261018` | `30318fb88600a182d4d0c65a6a1dd3e34ced96b1` |
| `feat/question-mapping-verifier-20261018` | `29250d2eea08969fe7fcc6ac5f911c8b8a2d6183` |
| `feat/s2-shenlun-parser-20261021` | `2229ba59e92b79388b99d833b2d5a8a85e340a72` |
| `feat/shenlun-archive-preflight-20261022` | `87ed79b4ecdb0c2e94cc7803bc97b81b56606cef` |
| `feat/shenlun-catalog-discovery-20261021` | `9c74d06691b466734eec1004bed71a6f4e24d3d8` |
| `fenbi-merge-20261023` | `b749c688e50bc4581be52966b5ac09359b2d0863` |
| `fenbi/audit-correction-20261017` | `f19ff2fadb6ee765a2f5c842f1827029460ca623` |
| `fenbi/batch-init-20261017` | `25e1bcb3164cf24c01eeed0d4c6485032ed32179` |
| `fenbi/batch-shards-20261018` | `c9b143d19439471e5ec5ae24fa2825922dcf8eb6` |
| `fenbi/c1-c-papers-20261021` | `62fc07b013d1233daf70d099e5a8980b0212e83c` |
| `fenbi/concurrency-2page-20261017` | `aae37140f22e86370a887cf7fa15242c6b94dc01` |
| `fenbi/image-residual-qa-20261018` | `dab4c5f26e63a2fb3a24b5751b4e6616b11fc4c9` |
| `fenbi/live-first-batch-report-20261017` | `5f48f56820535a50ec579bb1412a6aaf9668fdee` |
| `fenbi/live-second-batch-report-20261017` | `5c68955b065efedc5894b0d8e600c0e4b8aee7eb` |
| `fenbi/live-third-batch-report-20261017` | `a23c5bd275bbf6088995e27872574ef1562e6f3f` |
| `fenbi/owner-verification-20261018` | `abf5f6bab572728ce18ee3370c2c8e65006105ec` |
| `fenbi/reorder-audit-20261018` | `be45c9afb38d37f2bb74867d9eaa5261cdb42140` |
| `fenbi/s3-shenlun-material-panes-20261021` | `31f833908f9ad153244d21e52e6733928c810b05` |
| `fenbi/s5-shenlun-row-index-20261021` | `97775963f0d303118b6319e0500a527aff5506df` |
| `fenbi/shenlun-metadata-inventory-20261022` | `78f60bf75914452d9d6fcbe3d83a70f625690c25` |
| `fenbi/source-discovery-20261017` | `74bbc09c287c21d5b7aec2723784d0901ef95256` |
| `fenbi/spotcheck-figure-20261018` | `3c83c3292511d67e86804911601fd4c0f52590ac` |
| `fenbi/test-browser-executable-override` | `17db96063cc808a1f59b0f0f5afe42dfab2e0cb7` |
| `fix/absorb-open-prs` | `c328edcded1030af43b8dc4d8c85d412deb3d353` |
| `fix/asset-ref-scheme-20261018` | `4a8e98f616db3cb60a100f259b01c3b79f44e811` |
| `fix/bulk-gap-r5-20261012` | `53c4646b3b63b1661e2dca41bc6437d46bc7254a` |
| `fix/dom-capture-question-key-20261017` | `7e1b958da8073ddaa03b27e06e1c255c91233c30` |
| `fix/fenbi-board-first-capture-time-20261020` | `bf73f6e7eb3329f68de9b47aed42d764ac5d2862` |
| `fix/fenbi-collector-runtime-paths-20261021` | `618b50e65dcf1a16873fb6c6aa565d92bd7a5b10` |
| `fix/fenbi-duplicate-route-guard-20261018` | `eb3d68ad53ffc5269bf4ed8e56bf8cb998bd6af0` |
| `fix/fenbi-escape-stray-lt-20261022` | `a548b9cc0118b3a5c5e6100a52d1b3222bcb5beb` |
| `fix/fenbi-rendered-stub-gate-20261020` | `77383189a3a4f355c31f46ba4c96dcf415e7eb53` |
| `fix/full-gap-repair-r4-20261012` | `207aa9bdd56fd1f727ada25ebc97bdea21807320` |
| `fix/manifest-legacy-note-20261022` | `aba06684bf987a23fe4fd7aa11c63cbee49a9f34` |
| `fix/matcher-image-evidence-20261017` | `876466703af85db006d898840bb815a7048ed1a3` |
| `fix/paper-integrity-20261011` | `7eb640e8fc4457fb9eb46f2abf56050e50e1ac8d` |
| `fix/pipeline-route-param-loss-20261017` | `7229f6e6dfb9ce970097bfe49f9736519103301b` |
| `fix/priority-source-repair-r3-20261012` | `1435a6cef4e2ca4711a8b3e67e39de6ae869c09e` |
| `fix/pure-format-batch2-20261028` | `9379e18453bb3a938c998c2e9be94c8f23b66961` |
| `fix/r5-verified-answers-20261013` | `d52e9540bc27d230e5c743a549a339f8b635f96d` |
| `fix/route-param-preservation-20261017` | `73d72e450a35797eceb42698a5bfb84001e5cd8c` |
| `fix/shenlun-all-r7-20261013` | `c2e2a84ccffb4b0c27bd09e925ca5a43ff2f75c8` |
| `fix/shenlun-authored-exemplars-r8-20261013` | `c99311742384af8174e58471e242819b8eadd57a` |
| `fix/shenlun-explanation-unknown-20261027` | `7afdccd15fde8c37e8fd6fa2b5b0069e75a48b40` |
| `fix/shenlun-observed-prompt-boundary-gate-20261020` | `f7bcdd50e05099c5127f03d98bda7563eae54d35` |
| `fix/source-owned-r6-20261013` | `c6297afa958f8720e0a80200b4aa41b519bf7b01` |
| `fix/stub-gate-real-strings-20261017` | `b306916794f3ff0e554411473de1bc30b859c455` |
| `fix/verified-answer-gaps-r5-20261013` | `ae43c8666c7b5e28e38274553d2538ff1a53f9d2` |
| `format/pure-typography-20261028` | `c5e11c4414fbb9f2c74388d26612719160504825` |
| `integ/2026-10-19` | `4314051570841cdd88c0ea3f1877b6aef51bc535` |
| `integ/candidate-20261017` | `6e38f30cc1b05ed4c3f84d987d267497b6c4a821` |
| `ops/fenbi-throughput-20261018` | `65e7bfa516eb569236c44d82bcf913919049bc03` |
| `pipeline/observation-import-20261017` | `cae30c129e6122e24bd024db38e2145a11e37464` |
| `pipeline/offline-queue-20261017` | `df8acce6e8cbee23b9bc5f9ed37b94c4fac8e439` |
| `pipeline/routeparams-batch-metrics-20261017` | `4baf6aba3983a9a9295c814dee2e936b956fcade` |
| `polish/overview-nav` | `51372ed69ead7adabd7e4907ba4f3277c962e06b` |
| `pr137-mergeprep-20261028` | `b3df3145bdf4e58d89f8c9b0a96d0631131b48e1` |
| `qa/collection-placeholder-gate-20261017` | `4372e8af81b2e9ff55cf0cad5929b324df4c29ca` |
| `qa/fast10-shard-runner-20261018` | `e4b2d8b820544e6ef43777996e0e3e0a663d8cce` |
| `qa/gd-shard-20261018` | `55cc1fc90f372fd09faee28d266508247c4d0425` |
| `qa/shard-guokao-2026-20261018` | `a6e220d2f9a8f07528543073110adb4926ee523e` |
| `release/fenbi-batch-code-20261018` | `4e18e1ef8c28911b22eb77b5692e905264212bb2` |
| `repair/20261012-priority-completeness` | `62780572576150f6922586aa8dcf52e3fe596cc0` |
| `repair/20261012-round2-completeness` | `6cde7bde996d9b68391d619cbe546cbe95254083` |
| `s1/collector-source` | `3de758bc4958520e1defbabcd30868ee2f12e69c` |
| `s1/source-backed-qa-code-20261021` | `e482fc540e56846150bb967fd566d847ef8eb4d2` |
| `s3/auto-main-content-gate-20261020` | `8d52a2e593c6d258c5b4928f0ae8193474b52792` |
| `s3/quality-repair-20261021` | `6660721fe71dc3ffc0c2ae54609ce6518fc04a21` |
| `s5/shenlun-original-answers-20261021` | `38c122b34ac7a875eee30d3036dbb4cb691bbef1` |
| `s5/shenlun-original-answers-r2-20261021` | `25be7b6b78a874cbb0e4909a0d121310f74d46f9` |
| `s5/shenlun-original-answers-r3-20261021` | `bfdc2d54a41210604e6f1e317919b880ea3a0812` |
| `shard-qa-sh-tj-20261018` | `20b36556565a746ca3187fb6f9ea60c65e7a360a` |
| `shenlun/missing46-zj-sh-tj-20261018` | `6ed6fc80ed7e0ed60846c47586671eae7c83aa81` |

## 本地（4 个）

| 分支 | SHA |
| --- | --- |
| `ci/repair-gwy-zhenti-20261023` | `884c8d1f0f077611004a5480a7bb5ef4dca84559` |
| `fix/fenbi-b1-8papers-20261022` | `ed2f562334ebe962f61b861550b35dfc10621b0f` |
| `fix/restore-downgraded-shenlun-20261022` | `15f07f3a6534a709080437d94341f4fd012a0089` |
| `merge/pr133-formula` | `2278b7e3f04cdd1d63a920b719e74b49e4553465` |

> 该表原存于仓库外的清理日志目录，2026-10-30 按「公考工作内容只留在本仓库」的要求移入仓库；
> 表内 SHA 与删除时的 `git ls-remote` 输出逐行一致。
