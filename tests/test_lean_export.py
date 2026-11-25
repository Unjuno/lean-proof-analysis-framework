"""Compiler-backed integration tests; enabled by an explicit LPAF_LEAN binary."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_lean_export", ROOT / "scripts" / "check_lean_export.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


@unittest.skipUnless(os.environ.get("LPAF_LEAN"), "Set LPAF_LEAN to run actual Lean integration tests")
class LeanExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = HELPER.lean_path(None)
        _, cls.records = HELPER.run_fixture(cls.binary)
        cls.by_name = {r["name"]: r for r in cls.records[1:-1]}

    def test_real_environment_exports_proof_terms_and_origins(self):
        summary = HELPER.check_records(self.records)
        self.assertTrue(summary["complete"])
        self.assertGreater(summary["expr_nodes"], 0)
        declaration = self.by_name["LPAF.Fixture.trueCopy"]
        self.assertEqual(declaration["kind"], "theorem")
        self.assertEqual(declaration["module"], "Fixture")
        self.assertEqual(declaration["expression_status"]["value"], "available")
        self.assertIn("LPAF.Fixture.trueSeed", declaration["references"]["value"])
        self.assertNotIn("LPAF.Fixture.trueSeed", declaration["references"]["type"])
        self.assertIsNone(declaration["source_url"])

    def test_alpha_renamed_binders_keep_same_structural_payload(self):
        def without_display_names(expression):
            return [{k: v for k, v in node.items() if k != "binder_name"} for node in expression["nodes"]]
        left = self.by_name["LPAF.Fixture.twice"]["value_expr"]
        right = self.by_name["LPAF.Fixture.twiceRenamed"]["value_expr"]
        self.assertEqual(without_display_names(left), without_display_names(right))
        self.assertNotEqual(left, right)
        self.assertTrue(any(n["tag"] == "bvar" and n["data"] == ["0"] for n in left["nodes"]))

    def test_exact_literals_universes_and_dependency_diamond_survive(self):
        string_nodes = self.by_name["LPAF.Fixture.literalString"]["value_expr"]["nodes"]
        nat_nodes = self.by_name["LPAF.Fixture.literalNat"]["value_expr"]["nodes"]
        self.assertTrue(any(n["tag"] == "lit" and n["data"] == ["str", "1"] for n in string_nodes))
        self.assertTrue(any(n["tag"] == "lit" and n["data"] == ["nat", "1"] for n in nat_nodes))
        poly = self.by_name["LPAF.Fixture.identityPoly"]
        self.assertIn("u", poly["level_params"])
        self.assertTrue(any(n["tag"] == "sort" and "u" in n["data"][0] for n in poly["type_expr"]["nodes"]))
        diamond = self.by_name["LPAF.Fixture.diamond"]["references"]["value"]
        self.assertIn("LPAF.Fixture.leftStep", diamond)
        self.assertIn("LPAF.Fixture.rightStep", diamond)
        self.assertIn("LPAF.Fixture.twice", self.by_name["LPAF.Fixture.leftStep"]["references"]["value"])
        self.assertIn("LPAF.Fixture.twice", self.by_name["LPAF.Fixture.rightStep"]["references"]["value"])

    def test_axiom_no_value_is_distinct_from_a_capped_expression(self):
        axiom = self.by_name["LPAF.Fixture.declaredPremise"]
        self.assertEqual(axiom["kind"], "axiom")
        self.assertIsNone(axiom["value_expr"])
        self.assertEqual(axiom["expression_status"]["value"], "no_value")
        _, capped = HELPER.run_fixture(self.binary, ["--max-nodes", "1"])
        HELPER.check_records(capped)
        twice = next(r for r in capped[1:-1] if r["name"] == "LPAF.Fixture.twice")
        self.assertIsNone(twice["value_expr"])
        self.assertEqual(twice["expression_status"]["value"], "node_limit")
        self.assertTrue(twice["references_complete"])
        self.assertEqual(twice["references"], self.by_name["LPAF.Fixture.twice"]["references"])

    def test_declaration_limit_has_an_explicit_incomplete_footer(self):
        _, capped = HELPER.run_fixture(self.binary, ["--max-declarations", "2"])
        self.assertEqual(len(capped[1:-1]), 2)
        self.assertFalse(capped[-1]["complete"])
        self.assertEqual(capped[-1]["matched_declarations"], len(self.by_name))
        HELPER.check_records(capped)


if __name__ == "__main__":
    unittest.main()
