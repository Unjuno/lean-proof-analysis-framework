"""Behavior tests for reading tasks and explicit limits, not proof checking."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from lean_proof_analysis import (
    ReadingError, analyze_project, compare_declarations, dependency_slice,
    find_similar, get_declaration, list_declarations, load_report,
)


def declaration(name, *, path="Fixture.lean", line=1, statement=": True", body="by trivial", kind="theorem"):
    return {
        "id": f"{path}:{line}:{name}", "name": name, "short_name": name.rsplit(".", 1)[-1],
        "kind": kind, "path": path, "line": line, "end_line": line,
        "statement": statement, "body": body, "source_text": f"{kind} {name} {statement} := {body}",
        "source_url": f"https://github.com/example/proof/blob/{'a' * 40}/{path}#L{line}",
        "text_truncated": {"statement": False, "body": False, "source_text": False},
        "extraction": {"method": "source-regex", "boundaries": "heuristic", "elaborated": False,
                       "context_complete": False},
    }


def report_with(records, edge_specs=()):
    by_name = {d["name"]: d for d in records}
    return {
        "schema": "lean-atlas-v0.2", "mode": "source-only-unelaborated", "not_proof_check": True,
        "provenance": {"repository": "example/proof", "commit": "a" * 40,
                       "source_hashes_checked": False, "manifest_complete": False,
                       "files": [{"path": p, "git_blob_sha1": "b" * 40} for p in sorted({d["path"] for d in records})]},
        "declarations": records,
        "candidate_links": [{"from": by_name[a]["id"], "to": by_name[b]["id"], "role": role,
                             "resolution": "unique-short-name", "evidence_token": b} for a, b, role in edge_specs],
        "similarity_candidates": [], "summary": {"similarity_search": {"cap_reached": False}},
    }


class ReadingTest(unittest.TestCase):
    def test_persisted_source_has_full_capture_and_queries_retain_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            text = 'def message : String := "' + "x" * 500 + '"\n'
            (root / "Long.lean").write_text(text, encoding="utf-8")
            out = Path(directory) / "report"
            analyze_project(root, out, repository="example/proof", commit="a" * 40)
            report = load_report(out / "analysis.json")
            full = get_declaration(report, "message", max_chars=None, include_source=True)
            self.assertEqual(full["data"]["declaration"]["text"]["source_text"]["text"], text)
            self.assertEqual(len(full["data"]["declaration"]["text"]["body"]["text"]), 502)
            short = get_declaration(report, "message", max_chars=10)
            field = short["data"]["declaration"]["text"]["body"]
            self.assertTrue(field["truncated"])
            self.assertEqual(field["available_characters"], 502)
            self.assertEqual(field["returned_characters"], 10)
            self.assertEqual(field["input_completeness"], "complete_capture")
            self.assertFalse(short["coverage"]["context_complete"])
            self.assertFalse(short["coverage"]["semantic_dependencies_complete"])
            self.assertEqual(len(short["provenance"]["files"]), 1)
            self.assertIsNotNone(short["data"]["declaration"]["git_blob_sha1"])

    def test_search_is_stable_paginated_and_field_limited(self):
        report = report_with([declaration("A.z", line=3), declaration("A.y", line=2),
                              declaration("A.x", line=1), declaration("B.defn", line=4, kind="def", body="A.x")])
        page = list_declarations(report, query="a.", limit=2)["data"]
        self.assertEqual([d["name"] for d in page["declarations"]], ["A.x", "A.y"])
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["next_offset"], 2)
        last = list_declarations(report, query="A.", offset=2, limit=2)["data"]
        self.assertIsNone(last["next_offset"])
        self.assertEqual(last["declarations"][0]["name"], "A.z")
        self.assertEqual(list_declarations(report, kind="def")["data"]["total"], 1)

    def test_selectors_do_not_guess_between_duplicate_names(self):
        a, b = declaration("A.same"), declaration("B.same", path="Other.lean")
        report = report_with([a, b])
        with self.assertRaises(ReadingError) as caught:
            get_declaration(report, "same")
        self.assertEqual(caught.exception.code, "ambiguous_selector")
        self.assertEqual(caught.exception.details["total_candidates"], 2)
        self.assertEqual(get_declaration(report, a["id"])["data"]["declaration"]["name"], "A.same")
        duplicate = declaration("A.same", path="Duplicate.lean")
        with self.assertRaises(ReadingError) as caught:
            get_declaration(report_with([a, duplicate]), "A.same")
        self.assertEqual(caught.exception.code, "ambiguous_selector")

    def test_missing_case_sensitive_and_empty_selectors(self):
        report = report_with([declaration("A.Name")])
        for selector, code in [("A.name", "declaration_not_found"), ("", "invalid_selector")]:
            with self.subTest(selector=selector), self.assertRaises(ReadingError) as caught:
                get_declaration(report, selector)
            self.assertEqual(caught.exception.as_dict()["code"], code)

    def test_comparison_preserves_prop_bodies_operators_and_strings(self):
        records = [declaration("P", kind="def", statement="(n : Nat) : Prop", body="0 < n"),
                   declaration("Q", line=2, kind="def", statement="(n : Nat) : Prop", body="0 ≤ n"),
                   declaration("S", line=3, kind="def", body='"a b"'),
                   declaration("T", line=4, kind="def", body='"a  b"')]
        report = report_with(records)
        diff = compare_declarations(report, "P", "Q")["data"]
        self.assertTrue(diff["statement"]["equal"])
        self.assertFalse(diff["body"]["equal"])
        self.assertEqual(diff["body"]["changes"][0]["left"]["text"], "0 < n")
        self.assertEqual(diff["body"]["changes"][0]["right"]["text"], "0 ≤ n")
        self.assertFalse(compare_declarations(report, "S", "T")["data"]["body"]["equal"])
        self.assertNotIn("equivalent", diff)

    def test_comparison_keeps_quantifiers_and_numerals(self):
        report = report_with([declaration("all", statement=": ∀ n : Nat, n < 2"),
                              declaration("some", line=2, statement=": ∃ n : Nat, n < 3")])
        diff = compare_declarations(report, "all", "some")["data"]["statement"]
        self.assertFalse(diff["equal"])
        self.assertIn("∀", diff["changes"][0]["left"]["text"])
        self.assertIn("3", diff["changes"][0]["right"]["text"])

    def test_diff_budget_is_visible_and_does_not_claim_equality(self):
        report = report_with([declaration("a", body="x" * 100 + "0"),
                              declaration("b", line=2, body="x" * 100 + "1")])
        diff = compare_declarations(report, "a", "b", max_chars=8)["data"]["body"]
        self.assertFalse(diff["equal"])
        self.assertTrue(diff["truncated"])
        self.assertEqual(diff["status"], "truncated")
        self.assertEqual(sum(c[s]["returned_characters"] for c in diff["changes"] for s in ("left", "right")), 8)

    def test_large_diff_has_an_explicit_computation_limit(self):
        report = report_with([declaration("a", body="a\n" * 4001), declaration("b", line=2, body="b\n" * 4001)])
        diff = compare_declarations(report, "a", "b")["data"]["body"]
        self.assertFalse(diff["equal"])
        self.assertEqual(diff["status"], "skipped_size_limit")
        self.assertTrue(diff["truncated"])

    def test_legacy_preview_cannot_be_reported_as_equal_complete_text(self):
        report = report_with([declaration("a"), declaration("b", line=2)])
        report["schema"] = "lean-atlas-v0.1"
        for d in report["declarations"]:
            d.pop("text_truncated")
            d.pop("source_text")
        diff = compare_declarations(report, "a", "b")["data"]["statement"]
        self.assertIsNone(diff["equal"])
        self.assertEqual(diff["status"], "input_incomplete")
        card = get_declaration(report, "a", include_source=True)["data"]["declaration"]
        self.assertEqual(card["text"]["statement"]["input_completeness"], "unknown")
        self.assertFalse(card["text"]["source_text"]["available"])

    def graph(self):
        records = [declaration(n, line=i + 1) for i, n in enumerate(["root", "a", "b", "c", "leaf"])]
        return report_with(records, [("root", "a", "statement"), ("root", "b", "body"),
                                     ("a", "c", "body"), ("b", "c", "body"), ("c", "root", "body")])

    def test_candidate_cycle_and_diamond_terminate_preserving_edges(self):
        report = self.graph()
        data = dependency_slice(report, "root", max_depth=8)["data"]
        self.assertEqual(len(data["nodes"]), 4)
        self.assertEqual(len(data["edges"]), 5)
        self.assertTrue(data["traversal_complete"])
        self.assertEqual(data["nodes"][3]["depth"], 2)

    def test_depth_node_and_frontier_limits(self):
        report = self.graph()
        depth = dependency_slice(report, "root", max_depth=0)["data"]
        self.assertEqual(len(depth["nodes"]), 1)
        self.assertEqual(depth["frontier_total"], 2)
        self.assertTrue(all(f["reason"] == "max_depth" for f in depth["frontier"]))
        capped = dependency_slice(report, "root", max_nodes=2)["data"]
        self.assertEqual([n["declaration"]["name"] for n in capped["nodes"]], ["root", "a"])
        self.assertFalse(capped["traversal_complete"])
        self.assertTrue(all(f["reason"] == "max_nodes" for f in capped["frontier"]))

    def test_incoming_navigation_preserves_edge_orientation_and_role(self):
        report = self.graph()
        data = dependency_slice(report, "a", direction="dependents", role="statement")["data"]
        self.assertEqual([n["declaration"]["name"] for n in data["nodes"]], ["a", "root"])
        self.assertTrue(data["edges"][0]["from"].endswith(":root"))
        self.assertTrue(data["edges"][0]["to"].endswith(":a"))
        self.assertEqual(data["edges"][0]["role"], "statement")

    def test_leaf_is_not_a_claim_of_no_semantic_dependencies(self):
        result = dependency_slice(self.graph(), "leaf")
        self.assertTrue(result["data"]["traversal_complete"])
        self.assertFalse(result["coverage"]["semantic_dependencies_complete"])
        self.assertEqual(result["coverage"]["scope"], "analyzed-source-sample")

    def test_query_functions_do_not_mutate_report_or_alias_output(self):
        report = self.graph()
        before = deepcopy(report)
        result = get_declaration(report, "a")
        result["data"]["declaration"]["extraction"]["elaborated"] = True
        for operation in [lambda: list_declarations(report), lambda: dependency_slice(report, "root"),
                          lambda: compare_declarations(report, "a", "b"), lambda: find_similar(report, "root")]:
            operation()
        self.assertEqual(report, before)

    def test_invalid_bounds_and_dangling_edges_report_clear_errors(self):
        report = self.graph()
        for operation in [lambda: list_declarations(report, limit=0), lambda: list_declarations(report, offset=-1),
                          lambda: dependency_slice(report, "root", max_nodes=0),
                          lambda: dependency_slice(report, "root", max_depth=True),
                          lambda: get_declaration(report, "root", max_chars=0)]:
            with self.assertRaises(ReadingError) as caught:
                operation()
            self.assertEqual(caught.exception.code, "invalid_argument")
        report["candidate_links"][0]["to"] = "not-present"
        with self.assertRaises(ReadingError) as caught:
            dependency_slice(report, "root")
        self.assertEqual(caught.exception.code, "invalid_report")

    def test_similarity_uses_stored_candidates_and_explicit_search_coverage(self):
        report = self.graph()
        a, b = report["declarations"][:2]
        report["similarity_candidates"] = [{"from": a["id"], "to": b["id"], "tfidf_cosine": .9,
                                            "same_syntax_fingerprint": False, "shared_tactics": []}]
        result = find_similar(report, "root")["data"]
        self.assertEqual(result["matches"][0]["declaration"]["name"], "a")
        self.assertEqual(result["matches"][0]["similarity"]["tfidf_cosine"], .9)
        self.assertFalse(result["search_coverage"]["exhaustive"])

    def test_empty_diff_side_has_no_invalid_line_range(self):
        report = report_with([declaration("empty", body=""), declaration("value", line=2, body="1")])
        change = compare_declarations(report, "empty", "value")["data"]["body"]["changes"][0]
        self.assertEqual(change["kind"], "insert")
        self.assertIsNone(change["left"]["start_line"])
        self.assertEqual(change["left"]["line_count"], 0)
        self.assertEqual(change["left"]["insertion_after_line"], 0)

    def test_malformed_report_fields_raise_reading_errors(self):
        for field, value in [("short_name", []), ("source_text", 7), ("end_line", 0),
                             ("text_truncated", {"body": "false"}), ("extraction", [])]:
            report = report_with([declaration("x")])
            report["declarations"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ReadingError):
                get_declaration(report, "x", include_source=True)
        report = self.graph()
        report["candidate_links"][0]["from"] = []
        with self.assertRaises(ReadingError):
            dependency_slice(report, "root")
        report = self.graph()
        report["schema"] = []
        with self.assertRaises(ReadingError):
            list_declarations(report)
        report = self.graph()
        report["summary"] = []
        with self.assertRaises(ReadingError):
            find_similar(report, "root")
        with self.assertRaises(ReadingError):
            dependency_slice(self.graph(), "root", direction=[])


if __name__ == "__main__":
    unittest.main()
