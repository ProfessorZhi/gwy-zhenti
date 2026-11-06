#!/usr/bin/env bash
# 改写 main 的历史，去掉「当前版本里已不存在的文件」的全部旧版本，真正缩小 clone 体积。
#
# 会做的事（在一个新的临时目录里，不碰你现有的本地副本）：
#   1. git clone --mirror 远端，打成完整备份 backup-<日期>.bundle（所有分支、标签都在里面）
#   2. 另 clone 一份只含 main 的副本，用 git filter-repo 只保留 main 当前存在的路径
#   3. 打印改写前后的体积对比
#   4. 加 --push 时：强推改写后的 main，并删除远端除 main 外的全部分支
#      （旧分支和标签会让每次 clone 都把旧历史一起下载，所以不留在 GitHub 上，只留在备份 bundle 里）
#
# 后果（执行 --push 前务必确认）：
#   - main 的所有提交 SHA 都会变；任何人（包括 A6000 上的采集副本）都必须重新 clone，
#     旧副本不能再 pull / push，否则会把旧历史推回来
#   - 已合并 PR 页面里的提交链接会指向旧 SHA（GitHub 仍保留 refs/pull/*，页面不会消失）
#   - 远端旧分支删除后只能从备份 bundle 还原：git clone backup-<日期>.bundle
#
# 依赖：git ≥ 2.36、git-filter-repo（pip install git-filter-repo）
# 用法：
#   bash tools/slim_history_20261106.sh               # 只演练，打印体积对比，不推送
#   bash tools/slim_history_20261106.sh --push        # 演练通过后实际推送
set -euo pipefail

url=${REPO_URL:-https://github.com/ProfessorZhi/gwy-zhenti.git}
push=0; [ "${1:-}" = "--push" ] && push=1
stamp=$(date +%Y%m%d-%H%M%S)
work=${WORK_DIR:-$PWD/gwy-zhenti-slim-$stamp}
command -v git-filter-repo >/dev/null || { echo "缺少 git-filter-repo：pip install git-filter-repo"; exit 1; }
mkdir -p "$work"; cd "$work"

echo "== 1/4 完整备份"
git clone --quiet --mirror "$url" mirror.git
git -C mirror.git bundle create "$work/backup-$stamp.bundle" --all
git bundle verify "$work/backup-$stamp.bundle" >/dev/null
before=$(git -C mirror.git count-objects -vH | awk '/size-pack/{print $2,$3}')
echo "备份：$work/backup-$stamp.bundle（远端全部引用，pack $before）"

echo "== 2/4 改写 main"
git clone --quiet --no-local --single-branch --branch main mirror.git slim
cd slim
old_head=$(git rev-parse HEAD)
git ls-tree -r --name-only HEAD > ../keep-paths.txt
git filter-repo --force --quiet --paths-from-file ../keep-paths.txt
git reflog expire --expire=now --all && git gc --quiet --prune=now --aggressive
new_head=$(git rev-parse HEAD)

echo "== 3/4 校验"
# 改写只删旧路径，当前文件树必须逐字节不变
[ "$(git -C ../mirror.git rev-parse "$old_head^{tree}")" = "$(git rev-parse "$new_head^{tree}")" ] \
  || { echo "当前文件树与改写前不一致，停止"; exit 1; }
after=$(git count-objects -vH | awk '/size-pack/{print $2,$3}')
echo "main 提交数：$(git rev-list --count HEAD)；当前文件树一致"
echo "体积：改写前远端全部 $before → 改写后只含 main $after"

if [ "$push" != 1 ]; then
  echo "== 演练完成（未推送）。确认无误后加 --push 重新运行。"
  exit 0
fi

echo "== 4/4 推送"
git remote add origin "$url"
# 只有远端 main 仍是改写前那个提交时才覆盖，期间有人推送就失败退出
git push --force-with-lease="main:$old_head" origin main
mapfile -t others < <(git -C ../mirror.git for-each-ref --format='%(refname:strip=2)' refs/heads | grep -vx main || true)
mapfile -t tags < <(git -C ../mirror.git for-each-ref --format='%(refname:strip=2)' refs/tags || true)
del=()
for b in "${others[@]}"; do del+=(":refs/heads/$b"); done
for t in "${tags[@]}"; do del+=(":refs/tags/$t"); done
[ ${#del[@]} -eq 0 ] || git push origin "${del[@]}"
echo "完成。删除分支 ${#others[@]} 个、标签 ${#tags[@]} 个；备份在 $work/backup-$stamp.bundle"
echo "所有本地副本请重新 clone：git clone $url"
