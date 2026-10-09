# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gwyzhenti import catalog, cli, export, gates      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

SICHUAN_MD = "省考/四川/2016/行测-统考.md"
JIANGSU_MD = "省考/江苏/2020/行测-A类.md"


class TestGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwygate-")
        self.cat = os.path.join(self.tmp, "catalog")
        self.repo = os.path.join(self.tmp, "repo")
        up = {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}
        catalog.build({**up, "linfukai186": os.path.join(FIX, "linfukai186")}, self.cat)
        export.run(self.cat, up, self.repo)
        self.rep = gates.run_all(self.cat, up, self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _up(self):
        return {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}

    def test_all_six_gates_reported(self):
        names = [n for n, _, _ in self.rep.results]
        for g in ("G1", "G2", "G3", "G4", "G5", "G6"):
            self.assertTrue(any(x.startswith(g) for x in names), names)

    def test_all_pass_on_fixture(self):
        self.assertTrue(self.rep.ok, [(n, d) for n, ok, d in self.rep.results if not ok])

    def test_g2_detects_dangling_image(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("154428b1a538147.png", "missing-zzz.png")
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        rep = gates.run_all(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G2") and not ok for n, ok, _ in rep.results))

    def test_g2_known_source_gap_is_named_not_silent(self):
        """清单内的已知缺图 ⇒ G2 **不判负**，但必须**点名**（区别于清单外的缺失 = 缺陷）。"""
        os.remove(os.path.join(
            self.repo, "图片/省考-四川-2016-行测-统考/题目图/154428b1a538147.png"))
        with mock.patch.object(gates, "KNOWN_SOURCE_GAPS",
                               frozenset({"154428b1a538147.png"})):
            rep = gates.run_all(self.cat, self._up(), self.repo)
        name, ok, detail = [r for r in rep.results if r[0].startswith("G2")][0]
        self.assertTrue(ok, detail)
        self.assertIn("154428b1a538147.png", detail)

    def test_g6_detects_missing_paper(self):
        """G6 是 catalog→落盘的反向对账：整卷丢失必须红（G5 只从 md 出发，看不见这一面）。"""
        os.remove(os.path.join(self.repo, "省考/江苏/2020/行测-A类.md"))
        rep = gates.run_all(self.cat, self._up(), self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G6") and not ok for n, ok, _ in rep.results))

    def test_g5_detects_content_change(self):
        md = os.path.join(self.repo, "省考/四川/2016/行测-统考.md")
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        perturbed = re.sub(r"(?m)^(- \*\*A\*\*\. )(\d+)", r"\g<1>999999", text, count=1)
        self.assertNotEqual(perturbed, text, "fixture 里没有可扰动的 A 选项行")
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(perturbed)
        rep = gates.run_all(self.cat, {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}, self.repo)
        self.assertFalse(rep.ok)
        self.assertTrue(any(n.startswith("G5") and not ok for n, ok, _ in rep.results))


class TestGatesCanTurnRed(unittest.TestCase):
    """整改 F2·A / 评审 I2·裁定 R-T10-R3：**闸门「能红」回归**。

    此前只覆盖 G2 正向 / G2 已知缺图 / G6 缺卷 / G5 内容改动；**下面这些分支被删掉也不会红**。
    每条只破坏一处，断言**该闸**判负且理由串对得上。全程用 `tests/fixtures` 的临时仓，不碰真上游。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwygate-red-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cat = os.path.join(self.tmp, "catalog")
        self.repo = os.path.join(self.tmp, "repo")
        up = {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}
        catalog.build({**up, "linfukai186": os.path.join(FIX, "linfukai186")}, self.cat)
        export.run(self.cat, up, self.repo)

    def _up(self):
        return {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}

    def _md(self, rel):
        return os.path.join(self.repo, rel.replace("/", os.sep))

    def _read(self, path):
        with io.open(path, encoding="utf-8") as fh:
            return fh.read()

    def _write(self, path, text):
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def _resync_manifest(self):
        """同 `TestGates._resync_manifest`：把 manifest 的 sha 对齐，免得 G4 连带判负干扰断言。"""
        man = os.path.join(self.repo, "work", "manifest.jsonl")
        entries = [json.loads(ln) for ln in self._read(man).splitlines() if ln.strip()]
        with io.open(man, "w", encoding="utf-8", newline="\n") as fh:
            for e in entries:
                p = os.path.join(self.repo, e["path"].replace("/", os.sep))
                with open(p, "rb") as fh2:
                    e["sha256"] = hashlib.sha256(fh2.read()).hexdigest()
                fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")

    def _assert_gate_red(self, prefix, contains, up=None):
        rep = gates.run_all(self.cat, up or self._up(), self.repo)
        self.assertFalse(rep.ok, [(n, d) for n, ok, d in rep.results])
        hit = [(n, d) for n, ok, d in rep.results if n.startswith(prefix) and not ok]
        self.assertTrue(hit, "该闸未判负：%s" % [(n, ok, d) for n, ok, d in rep.results])
        self.assertIn(contains, hit[0][1])
        return rep

    # ---- A1–A3：G1 卷完整 ----

    def test_a1_broken_question_numbering_reds_g1(self):
        # 把第 1 题的题号改成第 8 题 ⇒ 题号序列 [8,2,3] 不连续
        p = self._md(SICHUAN_MD)
        self._write(p, self._read(p).replace("## 第 1 题", "## 第 8 题", 1))
        self._resync_manifest()
        self._assert_gate_red("G1", "题号不连续")

    def test_a2_missing_frontmatter_key_reds_g1(self):
        # 删掉 `地区:` 这一行 ⇒ frontmatter 契约缺键
        p = self._md(SICHUAN_MD)
        lines = [l for l in self._read(p).split("\n") if not l.startswith("地区: ")]
        self._write(p, "\n".join(lines))
        self._resync_manifest()
        self._assert_gate_red("G1", "frontmatter 缺键")

    def test_a3_wrong_declared_count_reds_g1(self):
        # 卷首引言声明的题数改错（3 → 4）⇒ 与实得题号数不符
        p = self._md(SICHUAN_MD)
        t = self._read(p)
        t2 = t.replace("> 行测 · 3 题 ·", "> 行测 · 4 题 ·", 1)
        self.assertNotEqual(t2, t, "fixture 的卷首引言行变了，本测试的破坏点失效")
        self._write(p, t2)
        self._resync_manifest()
        self._assert_gate_red("G1", "题数声明")

    # ---- A4–A6：G3 答案不泄露 ----

    def test_a4_leftover_checkmark_reds_g3(self):
        # 往正文一个选项行尾插入 ✅（题号口径下这是「答案泄露」）
        p = self._md(SICHUAN_MD)
        t = self._read(p)
        t2 = t.replace("- **D**. 393.2\n", "- **D**. 393.2 ✅\n", 1)
        self.assertNotEqual(t2, t, "fixture 里没有可插入 ✅ 的选项行")
        self._write(p, t2)
        self._resync_manifest()
        self._assert_gate_red("G3", "残留 ✅")

    def test_a5_missing_answer_section_reds_g3(self):
        # 删掉 `## 答案与解析` 行 ⇒ 无独立答案板块
        p = self._md(SICHUAN_MD)
        t = self._read(p)
        t2 = t.replace("## 答案与解析\n", "", 1)
        self.assertNotEqual(t2, t, "fixture 里没有 `## 答案与解析` 行")
        self._write(p, t2)
        self._resync_manifest()
        self._assert_gate_red("G3", "无独立答案板块")

    def test_a6_unfolded_answer_reds_g3(self):
        # `<details>` → `<detail>` ⇒ 答案未折叠。
        # **实测校正**：只改**一处**抓不到 —— `_g3` 的判据是**存在性**
        # （`"<details>" not in text or "</details>" not in text`），卷内有 3 个答案块，
        # 改一个还剩两个 ⇒ 闸仍绿。故这里把该卷**全部** `<details>` 都换掉，
        # 才真的走到「无折叠容器」那一支（这是**破坏方式**的修正，不是改闸）。
        # 注：G5 也会连带判负（`<detail>` 不是**声明过的**结构性容器 ⇒ 成了「导出有源无」的行）；
        # 本断言只钉 G3 那条分支。
        p = self._md(SICHUAN_MD)
        t = self._read(p)
        t2 = t.replace("<details>", "<detail>")
        self.assertNotEqual(t2, t, "fixture 里没有 `<details>`")
        self._write(p, t2)
        self._resync_manifest()
        self._assert_gate_red("G3", "答案未折叠")

    # ---- A7：G2 图片双向闭合（导出侧） ----

    def test_a7_unreferenced_png_on_disk_reds_g2(self):
        # 往某卷图片目录放一张**无人引用**的 png（1 字节）
        img_dir = os.path.join(self.repo, "图片", "省考-四川-2016-行测-统考", "题目图")
        with open(os.path.join(img_dir, "orphan-zzz.png"), "wb") as fh:
            fh.write(b"\x00")
        self._assert_gate_red("G2", "落盘但未被引用")

    # ---- A8–A10：G4 幂等 + 上游缺图账 ----

    def test_a8_untracked_byte_change_reds_g4(self):
        # 改 md 的一个字节（改一级标题里的年份），**不动** manifest ⇒ G4 的 sha 对不上。
        # 选一级标题是因为 G5 会剔除 `# ` 开头的行 ⇒ 破坏点**只**落在 G4。
        p = self._md(JIANGSU_MD)
        t = self._read(p)
        t2 = t.replace("# 2020 江苏省", "# 2021 江苏省", 1)
        self.assertNotEqual(t2, t, "fixture 的一级标题变了，本测试的破坏点失效")
        self._write(p, t2)          # 故意**不**同步 manifest
        self._assert_gate_red("G4", "sha 不符")

    def test_a9_missing_manifest_reds_g4(self):
        # 删掉 work/manifest.jsonl ⇒ 「没账本」不得静默通过
        os.remove(os.path.join(self.repo, "work", "manifest.jsonl"))
        self._assert_gate_red("G4", "缺 work/manifest.jsonl")

    def test_a10_missing_upstream_source_image_reds_g4(self):
        # 删上游 `90-图片/<图类>/` 里**被引用**的那张源图。
        # **用临时复制的上游**，不动 `tests/fixtures/` 里的源（其余测试共用）。
        up_tmp = os.path.join(self.tmp, "upstream-mod")
        shutil.copytree(os.path.join(FIX, "xingcezhenti"), up_tmp)
        src = os.path.join(up_tmp, "90-图片", "公式图", "formula-717ebaedf48c8509.png")
        self.assertTrue(os.path.exists(src), "夹具源图不在预期路径")
        os.remove(src)
        self._assert_gate_red("G4", "上游无源", up={"xingcezhenti": up_tmp})

    # ---- A11：G6 覆盖账（catalog→落盘反向对账的「多出来的 md」那一面） ----

    def test_a11_stray_md_without_catalog_row_reds_g6(self):
        # 已有 `test_g6_detects_missing_paper`（**少**了一卷）；本条是**反向的另一面**（**多**出来的 md）。
        stray = os.path.join(self.repo, "省考", "游离", "2016", "行测-统考.md")
        os.makedirs(os.path.dirname(stray), exist_ok=True)
        self._write(stray, "---\n考试: \"省考\"\n---\n\n# 游离卷\n")
        self._assert_gate_red("G6", "落盘 md 数")


class TestEmptyTreeNeverGreen(unittest.TestCase):
    """整改 F2·B / 评审 I5：导出树为空时**六闸不得全绿**（`limit` 亦然）。

    真实事故形态 = `export --limit N` 切到的前 N 行全是**无正文**的 linfukai186 卷 ⇒
    落盘 0 md、`work/manifest.jsonl` 是**空文件**（`export.run` 无条件写它）⇒
    旧实现下 G1–G5「真空通过 0 卷」、G6 因 `limit` 跳过「数相等」⇒ **六闸全绿**（假的安心）。
    故本类**故意**建那本**空 manifest**：否则 G4 会先因「缺 manifest」判负，
    断言就证明不了「把空树顶红的是 G6」。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gwyempty-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cat = os.path.join(self.tmp, "catalog")
        catalog.build({"xingcezhenti": os.path.join(FIX, "xingcezhenti"),
                       "linfukai186": os.path.join(FIX, "linfukai186")}, self.cat)
        self.up = {"xingcezhenti": os.path.join(FIX, "xingcezhenti")}
        self.repo = os.path.join(self.tmp, "repo")

    def _empty_repo_with_empty_manifest(self):
        os.makedirs(os.path.join(self.repo, "work"))
        io.open(os.path.join(self.repo, "work", "manifest.jsonl"), "w",
                encoding="utf-8").close()

    def test_empty_dir_repo_is_not_green(self):
        os.makedirs(self.repo)
        self.assertFalse(gates.run_all(self.cat, self.up, self.repo).ok)

    def test_empty_tree_with_limit_is_not_green_and_g6_is_the_reason(self):
        self._empty_repo_with_empty_manifest()
        rep = gates.run_all(self.cat, self.up, self.repo, limit=20)
        self.assertFalse(rep.ok, [(n, d) for n, ok, d in rep.results])
        hit = [(n, d) for n, ok, d in rep.results if n.startswith("G6") and not ok]
        self.assertTrue(hit, "空树未被 G6 判负：%s" % [(n, ok, d) for n, ok, d in rep.results])
        self.assertIn("导出树为空", hit[0][1])

    def test_empty_tree_without_limit_is_also_not_green(self):
        self._empty_repo_with_empty_manifest()
        self.assertFalse(gates.run_all(self.cat, self.up, self.repo).ok)

    # ---- 真实事故形态：`--limit N` 切到的**全是无正文的 linfukai186 卷** ----

    def _catalog_with_zero_exportable_rows(self):
        """一本**可导出 0 卷**的 catalog。

        `export._parts_for` 只认 xingcezhenti 源自己的卷名（`_xingce_titles`），
        纯 linfukai186 卷（`titles` 里只有 `linfukai186`）**取不到正文** ⇒ `parts == []`。
        这正是真实事故：`export --limit N` 切到的前 N 行恰好都没有正文。
        **旧实现**下这种树六闸全绿（G1–G5 对 0 个 md 真空通过、G6 因 `limit` 跳过「数相等」且
        `absent` 为空 ⇒ 假绿），故本条的 `assertFalse(rep.ok)` 在旧实现上是**红的**。
        """
        d = os.path.join(self.tmp, "catalog-noexport")
        os.makedirs(d, exist_ok=True)
        rows = [
            {"slug": "国考-2016-申论-统考",
             "level": "国考", "region": "", "year": "2016", "subject": "申论", "ptype": "统考",
             "modules": {"公文写作题": 1}, "sources": ["linfukai186"],
             "titles": {"linfukai186": ["2016·国家公务员考试"]},
             "nature": "正式真题", "form": "单独命题", "dubious": []},
            {"slug": "国考-2017-申论-统考",
             "level": "国考", "region": "", "year": "2017", "subject": "申论", "ptype": "统考",
             "modules": {"归纳概括题": 1}, "sources": ["linfukai186"],
             "titles": {"linfukai186": ["2017·国家公务员考试"]},
             "nature": "正式真题", "form": "单独命题", "dubious": []},
        ]
        with io.open(os.path.join(d, "catalog.jsonl"), "w", encoding="utf-8",
                     newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return d

    def test_zero_exportable_rows_is_not_green_with_or_without_limit(self):
        cat = self._catalog_with_zero_exportable_rows()
        self._empty_repo_with_empty_manifest()
        for limit in (None, 20):
            rep = gates.run_all(cat, self.up, self.repo, limit=limit)
            self.assertFalse(
                rep.ok, "limit=%s 时零可导出卷的空树被判绿：%s"
                        % (limit, [(n, ok, d) for n, ok, d in rep.results]))
            hit = [(n, d) for n, ok, d in rep.results if n.startswith("G6") and not ok]
            self.assertTrue(hit, "limit=%s 时 G6 未判负：%s"
                                 % (limit, [(n, ok, d) for n, ok, d in rep.results]))
            self.assertIn("导出树为空", hit[0][1])


class TestG5ShenlunBranch(unittest.TestCase):
    """申论保真：源 JSON 的 s/q/a/e 行必须逐行出现在导出里（多重集相等）。"""

    def _pair(self):
        from gwyzhenti import shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲\n材料乙", "q": "请概括", "a": "", "e": "范文一",
               "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        return qs, shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                        sources=["linfukai186"]).body

    def test_clean_render_has_no_diff(self):
        from gwyzhenti import shenlun
        qs, body = self._pair()
        self.assertEqual(shenlun.strip_structure(body), shenlun.source_lines(qs))

    def test_dropped_source_line_is_caught(self):
        from gwyzhenti import shenlun
        qs, body = self._pair()
        broken = body.replace("材料乙", "")
        self.assertNotEqual(sorted(shenlun.strip_structure(broken)),
                            sorted(shenlun.source_lines(qs)))

    def test_injected_line_is_caught(self):
        from gwyzhenti import shenlun
        qs, body = self._pair()
        broken = body.replace("范文一", "范文一\n凭空多出来的一行")
        self.assertNotEqual(shenlun.strip_structure(broken), shenlun.source_lines(qs))

    def test_blank_line_asymmetry_is_not_a_diff(self):
        """R-M3-7 扩容回归：源里带空白行 / 渲染器折叠空行，都不得判成差异。

        实测背景：控制器全量扫 468 卷，现状下 460/468 卷报差异，差异行全是空白行。
        这条测试把它钉死 —— 谓词必须两侧共用（含剔空白行）。
        """
        from gwyzhenti import shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲\n\n\n材料乙", "q": "请概括", "a": "",
               "e": "范文一\n", "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        body = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                    sources=["linfukai186"]).body
        self.assertEqual(sorted(shenlun.strip_structure(body)),
                         sorted(shenlun.source_lines(qs)))

    def test_gate_reads_the_delivered_file_verbatim(self):
        """R-M3-11 回归：源侧是**内存字符串**（不经 I/O 翻译），导出侧读盘也必须**原样**。

        源行尾带 `\r\r`（上游硬换行残留，实测真库 56,776 行）时，闸门若用默认读法读盘，
        `X\r\r\n` 被折成 `X\n\n` ⇒ 两侧不对称 ⇒ 真库 **372/468 卷**假红。
        这条**能红**：把 `_g5_shenlun` 的 `newline=""` 去掉，它立刻失败。
        """
        from gwyzhenti import gates, shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲\r\r\n材料乙", "q": "请概括", "a": "",
               "e": "范文一\r\r", "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        body = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                    sources=["linfukai186"]).body
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "wb") as fh:
                fh.write(body.encode("utf-8"))
            good, detail = gates._g5_shenlun(p, {"titles": {"linfukai186": ["卷T"]}},
                                             {"卷T": qs}, d)
        self.assertTrue(good, detail)


class TestShenlunDispatchIsPinned(unittest.TestCase):
    """F1/F2：申论的**分派**与 **G6 计数**必须能红（评审实测：删掉分支后 174 仍全绿）。"""

    def _fixture(self, d):
        """最小真库：1 份申论 md + 对应 catalog 行 + 申论源。"""
        from gwyzhenti import shenlun
        from gwyzhenti.model import PaperKey
        qs = [{"t": "单一题", "s": "材料甲", "q": "请概括", "a": "", "e": "范文一", "source": "x"}]
        key = PaperKey("省考", "山东", "2019", "申论", "统考")
        body = shenlun.render_paper(qs, key, nature="正式真题", form="单独命题",
                                    sources=["linfukai186"]).body
        repo = os.path.join(d, "repo")
        md_rel, _ = export.repo_paths(key, "省考-山东-2019-申论-统考")
        p = os.path.join(repo, md_rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(body.encode("utf-8"))
        cat = os.path.join(d, "cat")
        os.makedirs(cat, exist_ok=True)
        row = {"level": "省考", "region": "山东", "year": "2019", "subject": "申论",
               "ptype": "统考", "slug": "省考-山东-2019-申论-统考", "sources": ["linfukai186"],
               "nature": "正式真题", "form": "单独命题", "n_questions": 1, "modules": [],
               "titles": {"linfukai186": ["卷T"]}}
        with io.open(os.path.join(cat, "catalog.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        up = os.path.join(d, "up")
        sd = os.path.join(up, "gongkao-tiku", "data", "shengkao-shenlun")
        os.makedirs(sd, exist_ok=True)
        with io.open(os.path.join(sd, "y2019.json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"卷T": qs}, ensure_ascii=False))
        os.makedirs(os.path.join(up, "xingcezhenti"), exist_ok=True)
        return cat, {"xingcezhenti": os.path.join(up, "xingcezhenti"),
                     "linfukai186": os.path.join(up, "gongkao-tiku")}, repo

    def _row(self, rep, prefix):
        for name, ok, detail in rep.results:
            if name.startswith(prefix):
                return ok, detail
        self.fail("结果里没有 %s 这一条" % prefix)

    def test_shenlun_goes_through_the_shenlun_branch(self):
        """删掉 `run_all` 的申论分派 ⇒ 这份 md 落到 `_g5`（行测路径，无 xingcezhenti 卷名）
        ⇒ G5 报「源文件缺失」而变红。"""
        from gwyzhenti import gates
        with tempfile.TemporaryDirectory() as d:
            cat, uproots, repo = self._fixture(d)
            rep = gates.run_all(cat, uproots, repo, since="2016")
            ok, detail = self._row(rep, "G5")
        self.assertTrue(ok, detail)

    def test_g6_counts_shenlun_as_exportable(self):
        """把申论从 `exportable_map` 摘掉 ⇒ 可导出 0 vs 落盘 1 ⇒ G6 变红。"""
        from gwyzhenti import gates
        with tempfile.TemporaryDirectory() as d:
            cat, uproots, repo = self._fixture(d)
            rep = gates.run_all(cat, uproots, repo, since="2016")
            ok, detail = self._row(rep, "G6")
        self.assertTrue(ok, detail)
        self.assertIn("可导出 1", detail)


class TestCliGateForwardsSince(unittest.TestCase):
    """F3：`cli` 的 `gate` 子命令必须把 `--since` 接到 `gates.run_all(since=...)`。

    评审实测：删掉 `cmd_gate` 里的 `since=(args.since or None)` ⇒ 原有 174 条仍全绿
    ⇒ 这条接线此前**没有网**。此处用 `mock.patch.object(gates, "run_all")` 截住调用，
    直接断言 `since` 真的传到了：`--since 2016` ⇒ `"2016"`；不传 `--since` ⇒ **默认值来自
    `export.SCOPE_SINCE`**（= `"2016"`，本项目交付下限，**不再**折成 `None`）；
    显式 `--since ""` ⇒ `None`（不过滤的逃生门，原意保留）。
    """

    class _Rep:
        ok = True
        results = []

    def _call(self, *extra):
        s = io.StringIO()
        with mock.patch.object(gates, "run_all", return_value=self._Rep()) as m:
            with redirect_stdout(s):
                code = cli.main(["gate", "--catalog", "cat", "--upstream", "up", "--repo", "repo"]
                                + list(extra))
        self.assertEqual(code, 0, s.getvalue())
        return m

    def test_cli_gate_forwards_since(self):
        m = self._call("--since", "2016")   # 显式传值照旧
        self.assertEqual(m.call_args.kwargs.get("since"), "2016")
        m = self._call()                    # **新默认 = 交付下限**（回归网）
        self.assertEqual(m.call_args.kwargs.get("since"), "2016",
                         "`--since` 缺省时必须落到交付下限 2016，否则裸 gate 会误红 G6")
        m = self._call("--since", "")       # 显式空串 = 不过滤（原意保留）
        self.assertIsNone(m.call_args.kwargs.get("since"),
                          "显式 `--since \"\"` 须被折成 None（不过滤）")
