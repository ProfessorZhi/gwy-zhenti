"""Publish the independent index-boundary review and focused regression evidence."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[2]
files=['tools/verify_index_image_pixels_20261015.py','tools/test_verify_index_image_pixels_20261015.py']
out={
 'status':'fixed_and_focused_tests_passed','date':'2026-10-15',
 'findings':[{'severity':'high','issue':'Pre-change reference inventory read worktree Markdown, while image bytes came from the index. Staged broken-image references could be hidden by removing the reference only in the worktree.','fix':'Read every stage-zero exam Markdown blob via cat-file and validate its Git object hash before collecting references.'},{'severity':'high','issue':'Pre-change final guard compared only initially selected images; new/deleted indexed images and changed/new/deleted indexed papers were not comprehensively guarded.','fix':'Compare complete scoped image and exam-Markdown index maps before/after; additions, removals and changed blobs fail.'}],
 'verification':{'command':'python tools/test_verify_index_image_pixels_20261015.py','tests':12,'passed':12,'duration_seconds':16.861,'test_isolation':'Real temporary Git repositories under D:/artifacts/gwy-quality-audit-20261015; shared repair index was never staged or mutated by these tests.','cases':['staged bad image remains detected after worktree Markdown removes its reference','corrupt worktree image does not override staged good blob','deleted worktree Markdown remains in staged reference inventory','three GIF frames decode','a truncated later GIF frame fails with strict truncation policy even when caller policy was permissive','caller Pillow truncation policy restored','missing staged image fails','new staged exam Markdown fails final guard','changed staged exam Markdown fails final guard','new staged image fails final guard','deleted unreferenced staged image fails final guard','real loose Git object corruption fails recomputed hash','truncated Git batch stream fails']},
 'files':[{'path':p,'sha256':hashlib.sha256((R/p).read_bytes()).hexdigest()} for p in files],
 'scope_boundaries':['Pixel decoding covers images referenced by staged exam Markdown. Counts separately disclose all indexed images and unreferenced indexed images; unreferenced images are included in the concurrency guard but not falsely claimed as pixel-decoded.','Both Markdown and image Git blob IDs are recomputed, supporting SHA-1 and SHA-256 repositories.','Every image frame is loaded with Pillow truncation tolerance explicitly disabled.','No per-image worktree file open is performed. Git index enumeration and two batch object streams replace Windows individual image file reads.','The final guard certifies equality at the final snapshot. It cannot hold the index immutable after process exit or prevent an ABA change reverted to the exact same final blob maps; final staging/commit orchestration must freeze publication inputs.','Full corpus pixel validation remains a separate final run after all parallel document changes are frozen and staged. This focused test result does not claim the 95,904-image production run passed.']}
(R/'reports/INDEX-IMAGE-PIXEL-VERIFIER-REVIEW-20261015.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
md='''# 暂存索引图片像素校验器修复复核

修复两项实质漏检：工作树MD曾能隐藏实际已暂存的坏图引用；原末检只比较初始引用子集，漏掉新增/删除图片及试卷MD变更。

现在从stage0试卷MD blob取得引用，MD和图片都通过Git批流读入并重算对象hash；Pillow逐帧load，显式禁用宽容截断。终态比较全部图片及全部试卷MD索引映射，包含新增、删除和内容变化。

12个独立真实临时Git仓库测试通过，耗时16.861秒；包括已暂存坏图与工作树去引用、三帧GIF、后帧截断、直接损坏loose Git对象、batch截断及索引新增/删除/变化。没有修改共享工作树的Git索引。

范围明确：解码实际暂存试卷所引用图片，未引用图片数量单独列出，不谎称已解码。完整索引映射守卫只保证终态快照一致；校验进程退出后仍需冻结待提交内容。整库95,904图片实际解码应在并行修改全部冻结、stage之后由最终验收单独运行，本报告不预称整库通过。
'''
(R/'reports/INDEX-IMAGE-PIXEL-VERIFIER-REVIEW-20261015.md').write_text(md,encoding='utf8')
print(json.dumps({'status':out['status'],'tests':12},ensure_ascii=False))
