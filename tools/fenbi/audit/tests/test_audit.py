#!/usr/bin/env python3
"""Regression tests for the three-paper offline audit toolkit.

Run from the repository root:

    python3 -m unittest discover -s tools/fenbi/audit/tests -t .

Fixtures are generated at run time from this repository's own markdown, so no
question text is committed here. The synthetic cases only ever mutate metadata.
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.dirname(HERE)
sys.path.insert(0, AUDIT)

from _common import (  # noqa: E402
    compare_images, compare_options, compare_text, image_refs,
    normalize_comparison_text, parse_frontmatter, parse_paper,
    resolve_image_ref,
)
import handoff_reconcile  # noqa: E402
import paper_matrix  # noqa: E402


def repo_root():
    return os.path.abspath(os.path.join(AUDIT, os.pardir, os.pardir, os.pardir))


class NormalizationTests(unittest.TestCase):
    """compare_text/normalize must mirror tools/fenbi/src/align.mjs."""

    def test_whitespace_only_difference_is_same(self):
        result = compare_text("甲  乙\n丙", "甲乙 丙")
        self.assertEqual(result["status"], "same")
        self.assertEqual(result["reason"], "whitespace-only-difference")

    def test_fullwidth_ascii_is_folded(self):
        # U+FF21 FULLWIDTH LATIN CAPITAL A folds to ASCII A.
        self.assertEqual(compare_text("ＡＢＣ", "ABC")["status"], "same")

    def test_math_symbols_are_not_nfkc_folded(self):
        # x² must stay distinct from x2; NFKC would erase the distinction.
        self.assertEqual(compare_text("x²", "x2")["status"], "different")

    def test_content_difference_is_different(self):
        self.assertEqual(compare_text("甲公司", "乙公司")["status"], "different")

    def test_empty_source_is_unknown_not_different(self):
        result = compare_text("", "库中有内容")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "source-content-not-observed")

    def test_image_position_is_preserved_as_token(self):
        self.assertIn("IMAGE", normalize_comparison_text('<img src="a.png">')["strict"])

    def test_option_count_mismatch(self):
        src = [{"label": "A", "text": "1"}, {"label": "B", "text": "2"}]
        rep = [{"label": "A", "text": "1"}]
        self.assertEqual(compare_options(src, rep)["reason"], "option-count-differs")

    def test_option_label_reorder_detected(self):
        src = [{"label": "B", "text": "1"}, {"label": "A", "text": "2"}]
        rep = [{"label": "A", "text": "1"}, {"label": "B", "text": "2"}]
        self.assertEqual(compare_options(src, rep)["status"], "different")

    def test_image_digest_mismatch_is_different(self):
        self.assertEqual(compare_images(["a" * 64], ["b" * 64])["status"], "different")

    def test_image_count_mismatch_is_different(self):
        self.assertEqual(compare_images(["a" * 64], [])["reason"],
                         "image-reference-count-differs")

    def test_no_images_is_not_compared(self):
        self.assertEqual(compare_images([], [])["status"], "not_compared")


class PaperParserTests(unittest.TestCase):
    def test_parses_questions_options_and_materials(self):
        md = (
            "## 材料 1（第1—2题共用）\n共同材料\n\n"
            "## 第 1 题　<sub>qid 111 · 逻辑填空</sub>\n题干一\n\n"
            "- **A**. 甲\n- **B**. 乙\n- **C**. 丙\n- **D**. 丁\n\n"
            "## 第 2 题　<sub>qid 222 · 片段阅读</sub>\n题干二\n\n"
            "- **A**. 一\n- **B**. 二\n"
        )
        parsed = parse_paper(md)
        self.assertEqual(sorted(parsed["questions"]), [1, 2])
        self.assertEqual(parsed["questions"][1]["qid"], "111")
        self.assertEqual(parsed["questions"][1]["material_ids"], ["1"])
        self.assertEqual([o["label"] for o in parsed["questions"][1]["options"]],
                         ["A", "B", "C", "D"])
        self.assertEqual(parsed["questions"][2]["material_ids"], ["1"])

    def test_question_after_material_range_is_not_linked(self):
        md = ("## 材料 1（第1—1题共用）\n材料\n\n"
              "## 第 1 题　<sub>qid 1</sub>\n题干\n\n- **A**. x\n\n"
              "## 第 2 题　<sub>qid 2</sub>\n题干\n\n- **A**. y\n")
        parsed = parse_paper(md)
        self.assertEqual(parsed["questions"][1]["material_ids"], ["1"])
        self.assertEqual(parsed["questions"][2]["material_ids"], [])

    def test_answer_and_explanation_are_extracted(self):
        md = ("## 第 1 题　<sub>qid 1</sub>\n题干\n\n- **A**. x\n\n"
              "# 答案与解析\n\n"
              "<details><summary>第 1 题</summary>\n\n**答案**：B\n\n"
              "解析正文。\n\n</details>\n")
        parsed = parse_paper(md)
        self.assertEqual(parsed["questions"][1]["answer"], "B")
        self.assertIn("解析正文", parsed["questions"][1]["explanation"])


class MatrixTests(unittest.TestCase):
    """The offline matrix must be honest about unobserved dimensions."""

    @classmethod
    def setUpClass(cls):
        cls.doc = paper_matrix.build(repo_root(), donor_map=None)

    def test_covers_the_23_items_of_this_workstream(self):
        self.assertEqual(len(self.doc["items"]), 23)
        self.assertEqual(self.doc["summary"]["items_absent_in_library"], 11)
        self.assertEqual(self.doc["summary"]["items_with_library_content"], 12)

    def test_absent_items_are_marked_library_absent(self):
        item = next(i for i in self.doc["items"] if i["id"] == "广东2020县级卷-69")
        self.assertFalse(item["library"]["heading_present"])
        self.assertEqual(item["source_alignment"]["stem"]["library_side"],
                         "repository-content-absent")

    def test_no_dimension_is_claimed_same_without_a_source(self):
        for item in self.doc["items"]:
            for dim, state in item["source_alignment"].items():
                self.assertIn(state["status"], ("unknown", "not_compared"),
                              f"{item['id']} {dim} claimed {state['status']}")

    def test_answers_are_never_claimed_verified(self):
        for item in self.doc["items"]:
            self.assertEqual(item["verifiability"]["answer"], "unknown")
            self.assertEqual(item["verifiability"]["explanation"], "unknown")

    def test_library_file_digest_is_recorded(self):
        for paper in self.doc["papers"]:
            self.assertEqual(len(paper["file_sha256"]), 64)

    def test_cross_number_donor_is_marked_not_evidence(self):
        doc = paper_matrix.build(repo_root(), donor_map=paper_matrix.load_donor_map(repo_root()))
        cross = [i for i in doc["items"] if i.get("cross_number")]
        self.assertTrue(cross, "expected restored C items to carry a donor mapping")
        for item in cross:
            self.assertFalse(item["cross_number"]["donor_is_evidence_for_this_paper"])

    def test_cross_numbered_four_are_flagged(self):
        doc = paper_matrix.build(repo_root(), donor_map=paper_matrix.load_donor_map(repo_root()))
        shifted = {i["number"] for i in doc["items"]
                   if i.get("cross_number")
                   and i["cross_number"]["donor_number"] != i["number"]}
        self.assertEqual(shifted, {27, 29, 37, 42}, "the four cross-numbered restorations")


class ImageProvenanceTests(unittest.TestCase):
    """A figure referenced from another paper's image tree carries that
    paper's provenance — decisive for figure-reasoning items."""

    @classmethod
    def setUpClass(cls):
        cls.doc = paper_matrix.build(repo_root(), donor_map=None)
        cls.by_label = {p["label"]: p for p in cls.doc["papers"]}

    def test_own_image_dir_is_derived_from_frontmatter(self):
        self.assertEqual(self.by_label["江苏2025C类"]["own_image_dir"],
                         "省考-江苏-2025-行测-C类")
        self.assertEqual(self.by_label["广东2020县级卷"]["own_image_dir"],
                         "省考-广东-2020-行测-县级卷")

    def test_restored_c_figure_items_borrow_the_a_class_image_tree(self):
        paper = self.by_label["江苏2025C类"]
        self.assertEqual(paper["questions_with_foreign_paper_images"], [81, 85])
        self.assertEqual(paper["foreign_paper_image_dirs"],
                         ["省考-江苏-2025-行测-A类"])

    def test_other_papers_have_no_foreign_image_references(self):
        for label in ("江苏2024A类", "广东2020县级卷"):
            self.assertEqual(self.by_label[label]["questions_with_foreign_paper_images"], [])

    def test_borrowed_figure_raises_an_internal_finding(self):
        item = next(i for i in self.doc["items"] if i["id"] == "江苏2025C类-81")
        self.assertTrue(any(f.startswith("image-from-another-paper:")
                            for f in item["library_internal_findings"]))
        self.assertEqual(item["library"]["images"]["foreign_paper"], 1)
        self.assertEqual(item["library"]["images"]["own_paper"], 0)


class HandoffFixtureMixin:
    """Builds handoff documents from the library so no text is committed."""

    def library_handoff(self, repo, paper_rel, source_numbering="same"):
        with open(os.path.join(repo, paper_rel), encoding="utf-8") as fh:
            frontmatter, body = parse_frontmatter(fh.read())
        parsed = parse_paper(body)
        numbers = sorted(parsed["questions"])
        questions = []
        for index, number in enumerate(numbers):
            q = parsed["questions"][number]
            refs = image_refs(q["stem"]) + [r for o in q["options"]
                                            for r in image_refs(o["text"])]
            digests = [resolve_image_ref(repo, paper_rel, r["src"]).get("sha256")
                       for r in refs]
            source_number = number if source_numbering == "same" else index + 1
            questions.append({
                "source_number": source_number,
                "qid": q["qid"],
                "stem": q["stem"],
                "options": [{"label": o["label"], "text": o["text"]} for o in q["options"]],
                "material_ids": q["material_ids"],
                "images": digests,
                "answer": None,
                "explanation": None,
            })
        return {
            "schema": "fenbi-candidate-handoff-v1",
            "paper": {"label": os.path.basename(paper_rel),
                      "library_path": paper_rel,
                      "fenbi_source_id": "TEST",
                      "binding": "unverified"},
            "questions": questions,
        }


class ReconcileTests(unittest.TestCase, HandoffFixtureMixin):
    REPO = repo_root()
    C_PAPER = "省考/江苏/2025/行测-C类.md"
    GD_PAPER = "省考/广东/2020/行测-县级卷.md"

    def test_round_trip_against_own_content_is_same(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        tally = doc["dimension_tally"]
        self.assertEqual(tally["stem"]["different"], 0)
        self.assertEqual(tally["options"]["different"], 0)
        self.assertEqual(tally["stem"]["same"], len(doc["items"]))

    def test_answers_stay_unknown_when_source_publishes_none(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertEqual(doc["dimension_tally"]["answer"]["unknown"], len(doc["items"]))
        self.assertEqual(doc["dimension_tally"]["answer"]["same"], 0)
        for item in doc["items"]:
            self.assertEqual(item["dimensions"]["answer"]["reason"],
                             "source-answer-not-published")

    def test_library_answer_is_not_borrowed_from_source(self):
        # The fixture's library copy has answers; the source has none. The
        # verdict must be unknown, not same and not different-by-absence.
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertNotIn(doc["dimension_tally"]["answer"]["different"], (1,))

    def test_auto_join_uses_sequence_when_library_has_gaps(self):
        handoff = self.library_handoff(self.REPO, self.GD_PAPER, source_numbering="sequence")
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertEqual(doc["join"]["strategy"], "sequence")
        self.assertIn("gaps", doc["join"]["reason"])
        # All 93 source questions should map onto the 93 library questions.
        self.assertEqual(len(doc["items"]), 93)
        self.assertEqual(doc["join"]["library_numbers_not_covered"], [])

    def test_sequence_join_maps_past_the_gap_correctly(self):
        handoff = self.library_handoff(self.REPO, self.GD_PAPER, source_numbering="sequence")
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        # source position 69 (1-based) is library 76: the library omits 69-75.
        item = doc["items"][68]
        self.assertEqual(item["source_number"], 69)
        self.assertEqual(item["library_number"], 76)

    def test_number_join_leaves_declared_gaps_unmapped(self):
        # A source that numbers its own questions 69-75 while the library omits
        # those numbers: a number join must report them unmapped, not force a fit.
        handoff = {
            "schema": "fenbi-candidate-handoff-v1",
            "paper": {"label": "广东2020县级卷", "library_path": self.GD_PAPER,
                      "fenbi_source_id": "96785", "binding": "unverified"},
            "questions": [{
                "source_number": n, "qid": f"test-{n}", "stem": f"合成占位题干 {n}",
                "options": [{"label": lb, "text": f"选项 {lb}"} for lb in "ABCD"],
                "material_ids": [], "images": [], "answer": None, "explanation": None,
            } for n in range(69, 76)],
        }
        doc = handoff_reconcile.build(self.REPO, handoff, "number")
        self.assertEqual(doc["join"]["strategy"], "number")
        self.assertEqual(len(doc["items"]), 0)
        self.assertEqual(len(doc["join"]["unmapped_source_items"]), 7)
        # Every library question goes uncovered: nothing pairs with 69-75.
        with open(os.path.join(self.REPO, self.GD_PAPER), encoding="utf-8") as fh:
            _, body = parse_frontmatter(fh.read())
        library_numbers = sorted(parse_paper(body)["questions"])
        self.assertEqual(doc["join"]["library_numbers_not_covered"], library_numbers)

    def test_stem_mutation_is_detected(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        target = handoff["questions"][0]
        target["stem"] = target["stem"] + "篡改内容"
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertEqual(doc["items"][0]["dimensions"]["stem"]["status"], "different")
        self.assertEqual(doc["dimension_tally"]["stem"]["different"], 1)

    def test_option_mutation_is_detected(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        target = handoff["questions"][0]
        if len(target["options"]) < 2:
            self.skipTest("first question has too few options")
        target["options"][0]["text"] = target["options"][0]["text"] + "篡改"
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertEqual(doc["items"][0]["dimensions"]["options"]["status"], "different")

    def test_material_linkage_mismatch_is_detected(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        # Question 1 has no shared material; claim one.
        handoff["questions"][0]["material_ids"] = ["999"]
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertEqual(doc["items"][0]["dimensions"]["materials"]["status"], "different")

    def test_image_digest_mutation_is_detected(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        mutated = False
        for question in handoff["questions"]:
            if question["images"]:
                question["images"][0] = "0" * 64
                mutated = True
                break
        if not mutated:
            self.skipTest("paper has no image references")
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertEqual(doc["dimension_tally"]["images"]["different"], 1)

    def test_source_answer_present_is_compared(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        handoff["questions"][0]["answer"] = "A"
        doc = handoff_reconcile.build(self.REPO, handoff, "auto")
        self.assertIn(doc["items"][0]["dimensions"]["answer"]["status"],
                      ("same", "different"))

    def test_document_json_shape_is_adapted(self):
        handoff = self.library_handoff(self.REPO, self.C_PAPER)
        document = {
            "identity": {"id": "4189916", "title": "江苏2025C"},
            "source": {"capturedAt": "2026-10-17T00:00:00Z"},
            "assets": [],
            "questions": [{
                "id": q["qid"], "number": q["source_number"],
                "contentHtml": q["stem"],
                "options": [{"label": o["label"], "contentHtml": o["text"]}
                            for o in q["options"]],
                "materialIds": q["material_ids"],
                "answerHtml": "", "explanationHtml": "",
            } for q in handoff["questions"]],
        }
        adapted = handoff_reconcile.adapt_handoff(document)
        self.assertEqual(adapted["adapted_from"], "framework-document-json")
        doc = handoff_reconcile.build(self.REPO, adapted, "auto",
                                      library_path=self.C_PAPER)
        self.assertEqual(doc["dimension_tally"]["stem"]["different"], 0)


class CliSmokeTests(unittest.TestCase):
    """The scripts must run from a different working directory (relative paths)."""

    def test_matrix_runs_with_relative_defaults(self):
        import subprocess
        script = os.path.join(AUDIT, "paper_matrix.py")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "m.json")
            result = subprocess.run(
                [sys.executable, script, "--repo", repo_root(), "--out", out],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(len(json.load(fh)["items"]), 23)

    def test_scripts_contain_no_absolute_host_paths(self):
        for name in ("paper_matrix.py", "handoff_reconcile.py", "_common.py"):
            with open(os.path.join(AUDIT, name), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("/home/", text, name)
            self.assertNotIn("/Users/", text, name)


if __name__ == "__main__":
    unittest.main()
