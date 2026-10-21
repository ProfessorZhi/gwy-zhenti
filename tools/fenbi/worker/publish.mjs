// 落地与发布：单卷转换 + 发布进集成工作树；按批提交、过完整闸门、推送集成分支，闸门通过且 AUTO_MERGE=1 时快进推送 main。
// 集成工作树必须在非 main 分支上（batch-promote 拒绝在 main 上发布）。
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { ingestFolder } from '../src/batch-ingest.mjs';
import { promoteAll } from '../src/promote-all.mjs';
import { fullGate } from './gate.mjs';

const pexec = promisify(execFile);
const CONTENT = ['国考', '省考', '图片', 'catalog/manifest.jsonl'];
const git = async (repo, ...args) => (await pexec('git', ['-C', repo, ...args], { maxBuffer: 64 * 1024 * 1024 })).stdout.trim();

export const candidateRootOf = repo => path.join(repo, 'work/fenbi/batch-ingest');

// 一卷：缓存目录 → 候选（A/C）→ 发布所有待发布的 A 候选（粉笔优先替换、题数更少不替换、同路径取最完整的来源）。
export async function landPaper({ papersDir, name, repo, rightsFile }) {
  const real = await fs.realpath(repo);
  const dest = candidateRootOf(real);
  const row = await ingestFolder({ source: await fs.realpath(papersDir), repo: real, dest, name, write: true });
  if (row.grade !== 'A') return { row, promote: null };
  const promote = await promoteAll({ candidateRoot: dest, repoRoot: repo, rightsFile, allowReplace: true, apply: true });
  return { row, promote };
}

// 补落地：已交卷的卷里，图片后来才补齐（或上次落地失败）的，重新转换；未变化的候选直接复用，开销很小。最后统一发布一次。
export async function landMany({ papersDir, names, repo, rightsFile }) {
  const real = await fs.realpath(repo), source = await fs.realpath(papersDir), dest = candidateRootOf(real);
  const out = { A: 0, C: 0, errors: 0, promote: null };
  for (const name of names) {
    try { (await ingestFolder({ source, repo: real, dest, name, write: true })).grade === 'A' ? out.A++ : out.C++; }
    catch { out.errors++; }
  }
  if (out.A) out.promote = await promoteAll({ candidateRoot: dest, repoRoot: repo, rightsFile, allowReplace: true, apply: true });
  return out;
}

export async function commitContent(repo, message) {
  if (!(await git(repo, 'status', '--porcelain', '--', ...CONTENT))) return null;
  // git add 对不存在的路径会报错（例如还没有任何省考卷），只传存在的。
  const present = [];
  for (const p of CONTENT) if (await fs.access(path.join(repo, p)).then(() => true, () => false)) present.push(p);
  await git(repo, 'add', '-A', '--', ...present);
  await git(repo, 'commit', '-q', '-m', message);
  return git(repo, 'rev-parse', '--short', 'HEAD');
}

/**
 * 提交 → 同步 main → 完整闸门 → 推送集成分支 →（闸门通过且 autoMerge）快进推送 main。
 * main 在此期间被别人推进时快进推送会被拒绝：不强推，留到下一批再同步重试。
 */
export async function publish({ repo, rightsFile, message, push = true, autoMerge = false, remote = 'origin', main = 'main' }) {
  const out = { committed: await commitContent(repo, message), pushedBranch: false, pushedMain: false, gate: null };
  if (!push) return out;
  const branch = await git(repo, 'branch', '--show-current');
  if (!branch || branch === main) throw Error('integration-worktree-branch-required');
  await git(repo, 'fetch', '-q', remote, main);
  try { await git(repo, 'merge', '-q', '--no-edit', `${remote}/${main}`); }
  catch (e) { await git(repo, 'merge', '--abort').catch(() => {}); out.error = 'merge-conflict-with-main'; return out; }
  await git(repo, 'push', '-q', remote, `HEAD:refs/heads/${branch}`);
  out.pushedBranch = true;
  out.gate = await fullGate({ repo, base: `${remote}/${main}`, candidateRoot: candidateRootOf(repo), rightsFile });
  if (autoMerge && out.gate.ok) {
    try { await git(repo, 'push', '-q', remote, `HEAD:refs/heads/${main}`); out.pushedMain = true; }
    catch (e) { out.error = 'main-push-rejected'; out.detail = String(e.stderr || e.message).slice(0, 200); }
  }
  return out;
}
