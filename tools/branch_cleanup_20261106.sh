#!/usr/bin/env bash
# 远端分支清理（2026-11-06），清单与判定见 docs/archive/BRANCH-CLEANUP-20261106.md。
# 默认只打印计划；加 --apply 才执行。只处理远端 SHA 与清单一致的分支。
set -euo pipefail

apply=0; [ "${1:-}" = "--apply" ] && apply=1
remote=${REMOTE:-origin}
git fetch --quiet "$remote" --prune

# 动作 分支 SHA
plan=(
  "delete audit/gap-content-20261030 e34ff031e7cc6884972ac247770360c3c9b59c67"
  "delete audit/quality-spotcheck-20261030 8809b4da19f001d57ed4c118c04cf3111ab5f692"
  "delete claude/bold-brahmagupta-lkou1e f78be123042e2c2867329db7d91737b3c19cd274"
  "delete codex/fill-fujian-2017 d97cb5de9cbc7363c39b04ea5ee43ccb827b00bd"
  "delete codex/fill-guangdong-2019 224e6bf6796097cd0fde2a15598ee9452426baad"
  "delete codex/fill-guangxi-2017 2cb3fae917fd98c4795e7e23a35d87c3977dd9b4"
  "delete codex/fill-jiangsu-2024c-q110 55865a8600145217b289aeb0d65cbbec39aa04cc"
  "delete codex/fill-jiangsu-2026b-answers 4f33a75213a151aef811a74906a04270623bfe98"
  "delete codex/fill-shandong-2023-q42 69d43fd6e89003f2ee2d365414f1d97f9879a21a"
  "delete codex/guard-duplicate-anchors b797bcf6985a0538813cd27796f2e799fd32ee33"
  "delete codex/huatu-reviewed-fill 67d2f9ac817f66c0f15c3e0f07ba2502bcce8cdb"
  "delete docs/all-exam-coverage-20261104 5ae14d74413b048a1ec6d0ae3d8806d8f64ccf45"
  "delete docs/coverage-image-count-sync-20261030 9dd679b3d22876baff2b346e0b99bb9b876e0013"
  "delete docs/gap-ledger-reconcile-20261030 c9c93552e2f4f299a8f524584458a48f0dfc9a2c"
  "delete docs/real-exams-and-source-union-20261104 24569e6f92ddc6c0d6b597f041260932a647afa1"
  "delete feat/reusable-source-archive d1dae5a50f8fa6d447cff406827cc3bc3613bd9b"
  "delete fenbi-integ af24084a900e31ae7f9d03b8e2cf84f796bcb80b"
  "delete fenbi-integ-l1-20261021 99c0d2f30c8f378b93258693c4b728b5951623b2"
  "delete fenbi/c1-batch2-zj-20261021 46f3d83c4400a39cbccd539caac36cd25d582dc6"
  "delete fenbi/c1-tech-c-20261021 e025471c9f200e0b6a75a9b32f0803b1bb9a1917"
  "delete fix/quality-summary-a1-count-20261030 4561ae473e34b2785be39d260ab38127a0a9567e"
  "archive archive/c2-offline-decode-idx-20261021-c2-scratch 156d2f8bc987a10b25f26f201a1d67bf1ab174f9"
  "archive archive/fenbi-ingest-20261023-s1-l1 e047d7b5ce04f6cbff0ad71d5a063d7d16738d1e"
  "archive archive/fenbi-integ-l1-20261021-s1-l1 252e77917dd0fd65b2d5875096fbdf5749c00380"
  "archive archive/fenbi-landing-trial-2-s1-trial-104 c741fafc10de59504e04f1596de6069159e9c911"
  "archive archive/fenbi-landing-trial-s1-trial-104 6f0d73a5bbedee1946f9d406e96a490cb370b080"
  "archive archive/fix-fenbi-b1-8papers-20261022-s8-shenlun-land 5072446ac287ec8010d97176cda8fbe8533f03f1"
  "archive archive/fix-stale-regression-tests-s1-l1 11865b37818810aa0f06dc99428fff8ab803fd89"
  "archive archive/gwy-zhenti-consolidate-20261021 4757813b58bf757264a726938b0e1e0d632230d9"
  "archive archive/gwy-zhenti-s3-auto-main-draft-20261020 8d52a2e593c6d258c5b4928f0ae8193474b52792"
  "archive archive/gwy-zhenti-s3-dev-20261020 057fab1dcefe32d5a122bf2772b0cc14bb730627"
  "archive archive/gwy-zhenti-s3-quality-repair-20261021 6660721fe71dc3ffc0c2ae54609ce6518fc04a21"
  "archive archive/gwy-zhenti-s3-shenlun-dev-20261020 423c96fe3daba097a58705c3fa3b8bb88c06edb8"
  "archive archive/gwy-zhenti-s3-shenlun-pr88-20261020 62f876a3765a1355e35544ffa5c1656c8f529eae"
  "archive archive/gwy-zhenti-s3-shenlun-review-20261020 1695b1b46e7453c69618e07fe376b243d49aad76"
  "archive archive/integrate-fenbi-both-20261022-af24084a9-s8-shenlun-land edfd56693cb59b06d947b1fce5e1aaa8d102b6a7"
  "archive archive/integrate-fenbi-both-b3-20261022-s8-shenlun-land 32fd799787a37fe946764a574232b24cd9d5ede4"
  "archive archive/master-gwy-format-final 97590a84d377cb8ccd63a746812303bd0c00c390"
  "archive archive/master-gwy-zhenti-longrun a88124f5a071b6894e8e13facfc159a2d8bb5fdb"
  "archive archive/qa-batch-candidate-20261017-audit 1da2019dab6d1110b9acad9d296664dbe9e1e957"
  "archive archive/qa-integration-candidate-20261018-audit c7b5f6fc6f85a852f7521d3b12ccf24e14e9f485"
  "archive archive/qa-integration-candidate-r2-20261018-audit 8275af75e0f6705aa447cc6165ddd18b0e572f53"
  "archive archive/qa-release-candidate-20261018-audit 6adeab2082ecba20e3d459be75e481d58b6cf28b"
  "archive archive/qa-stack-candidate-20261018-audit 473b316434ab0a9b57b35c0b4443bd7677b9552f"
  "archive archive/qa-stack-candidate-with63-20261018-audit 1ca6231749e6119804b065798b0804550decb075"
  "archive archive/sim-comb-integration 74fba5dfdc42d8c03f2b4aeca4c5a7a640761b7d"
  "archive archive/sim-conc-plus-22-integration c7326e9aafaf1c77e1a063c085f58560326df069"
  "archive archive/sim-fix-plus-22-integration 1c7df64d818db4a9e1384bb1a17e8dcd9310bd23"
  "archive archive/sim-integration-21-22-integration 9e1539115da3ef2d6249705b829fe5ba94727b77"
  "archive archive/sim-probe21-integration 6d3a471b329bf44afe684491137b7ab8ae6232f8"
  "archive archive/sim-stack-integration d46fd0cf97893d997278d2229c1e622efcf6150b"
  "archive archive/sim-triple-integration 72caf36d690fed52d124f73d726b21ca897517a2"
  "archive audit/fenbi-batch-arithmetic-20261017 25e1bcb3164cf24c01eeed0d4c6485032ed32179"
  "archive audit/fenbi-route-fidelity-gate-20261017-r4 cae30c129e6122e24bd024db38e2145a11e37464"
  "archive complete/essay-r9-all-20261013 33dfb422211963cc9faadce455f170e7944e764e"
  "archive essay/r11-complete-568 0f806f4e8154e87c0c38c5d5bef0a4294f8a0caf"
  "archive feat/essay-all-738-reference-20261013 8b97f5a3a887e833d21077be30a40ed1074beb1d"
  "archive feat/fenbi-batch-ingest-20261018 1db61be643069c6f6d67f73c0ddbf5a388f1557b"
  "archive feat/m1-merge 6dabfd7c53b7bf17e93ae5aa5aa9d359fc5c51d0"
  "archive fix/anhui2018A-references-r9-20261013 8c23683610441d82836b907e20c586f2b4622646"
  "archive fix/essay-priority-references-r8-20261013 dcf92692b2791b9b61a39dbaed8408b58736d09b"
  "archive fix/essay-priority-refs-r8-rebased-20261013 adac256127b1cd90086436ed91e4a47cb46150ce"
  "archive fix/essay-reference-r7-20261013 9cc7c0cca5b984b25ea9804ab7e474c1896b746e"
  "archive fix/f8-residual-caption-image-20261018 29250d2eea08969fe7fcc6ac5f911c8b8a2d6183"
  "archive fix/fenbi-observation-title-failclosed-20261017 4baf6aba3983a9a9295c814dee2e936b956fcade"
  "archive fix/priority-completion-20261012 82b685931bc6f0eedb629e812b733624635f3b1c"
  "archive fix/priority-source-r3-20261012 6889c9672c52db6359301c55135aefd3f7b18d84"
  "archive fix/r6-essay-references-20261013 b6309f34636b0e3285e50fc01e8df1b750ecf280"
  "archive qa/shard-js-zj-20261018 41a8d8cd9af3621e5529e4d9cdb66a7e96121551"
  "archive repair/20261012-r3-gap-layout e66ce8e316d4ca7f883bba649dc7b56cd23f5872"
  "archive rescue/dell-gwy-zhenti-fenbi-combo b4c5dc8797e76af917444c21b1072ad2f8495d3b"
  "archive rescue/dell-gwy-zhenti-fenbi-s2-batch-ingest ada9b4d132c587055caadd1cd38999759bbddf86"
  "archive rescue/dell-gwy-zhenti-integration-20261017 ffb91d0a2811ba3273cc21cbc9436afdcb80fdc1"
  "archive rescue/dell-gwy-zhenti-throughput-gittrial 3ee4eb417bcf564454e82525e074a937d8485c44"
  "archive rescue/windows-gwy-verify 6dabfd7c53b7bf17e93ae5aa5aa9d359fc5c51d0"
)

tags=(); deletes=(); skipped=0
for row in "${plan[@]}"; do
  read -r action branch sha <<<"$row"
  current=$(git rev-parse --verify --quiet "refs/remotes/$remote/$branch" || true)
  if [ "$current" != "$sha" ]; then
    echo "skip  $branch（远端 ${current:-已不存在}，清单 $sha）"; skipped=$((skipped+1)); continue
  fi
  if [ "$action" = archive ]; then
    tags+=("$sha:refs/tags/branch-archive/${branch#archive/}")
  fi
  deletes+=(":refs/heads/$branch")
  echo "$action $branch"
done

echo "计划：标签 ${#tags[@]} 个，删除分支 ${#deletes[@]} 个，跳过 $skipped 个"
[ "$apply" = 1 ] || { echo "（dry-run，加 --apply 执行）"; exit 0; }

# 先建标签并确认全部到位，再删分支
[ ${#tags[@]} -eq 0 ] || git push "$remote" "${tags[@]}"
for t in "${tags[@]}"; do
  ref=${t#*:}
  git ls-remote --exit-code "$remote" "$ref" >/dev/null || { echo "标签未建成：$ref，停止，不删分支"; exit 1; }
done
[ ${#deletes[@]} -eq 0 ] || git push "$remote" "${deletes[@]}"
echo "完成"
