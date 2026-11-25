"""Ingestion integrity and source/elaborated evidence boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lean_proof_analysis import analyze_project
from lean_proof_analysis.corpus import CorpusError, import_corpus, import_source_report, open_corpus


def expr(name="True"):
    return {"nodes": [{"tag": "const", "data": [name], "children": []}], "root": 0, "truncated": False}


def record(name="Demo.a"):
    return {"record": "declaration", "id": name, "name": name, "kind": "theorem", "module": "Demo",
            "evidence": "lean_elaborated", "source_url": None, "type_expr": expr(), "value_expr": expr("True.intro"),
            "expression_status": {"type": "available", "value": "available"},
            "references": {"type": ["True"], "value": ["True.intro"]}}


class CorpusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, records=None, *, complete=True, footer=True, name="source.jsonl"):
        records = [record()] if records is None else records
        lines = [{"record": "header", "schema": "lpaf-corpus-v0.1", "lean_version": "fixture"}] + records
        if footer:
            lines.append({"record": "footer", "declarations": len(records), "complete": complete})
        path = self.root / name
        path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return path

    def test_roundtrip_roles_hashes_and_lazy_expression_access(self):
        source = self.write()
        with import_corpus(source, self.root / "proofs.sqlite") as corpus:
            self.assertEqual(corpus.metadata["input"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(corpus.metadata["declarations"], 1)
            rows = list(corpus.iter_declarations())
            self.assertNotIn("type_expr", rows[0])
            self.assertEqual(corpus.get_declaration("Demo.a")["value_expr"], expr("True.intro"))
            self.assertEqual([r["to"] for r in corpus.iter_references("type")], ["True"])
            self.assertEqual([r["to"] for r in corpus.iter_references("value")], ["True.intro"])
            metadata = corpus.metadata
            metadata["header"]["lean_version"] = "mutated"
            self.assertEqual(corpus.metadata["header"]["lean_version"], "fixture")
        with open_corpus(self.root / "proofs.sqlite") as reopened:
            self.assertEqual(reopened.metadata["references"], 2)

    def test_bounded_selection_retains_incomplete_footer(self):
        with import_corpus(self.write(complete=False), self.root / "bounded.sqlite") as corpus:
            self.assertFalse(corpus.metadata["selection_complete"])

    def test_interrupted_or_mismatched_exports_never_publish_partial_database(self):
        source = self.write(footer=False)
        destination = self.root / "broken.sqlite"
        with self.assertRaises(CorpusError) as caught:
            import_corpus(source, destination)
        self.assertEqual(caught.exception.code, "incomplete_export")
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob(".lpaf-import-*")), [])
        source.write_text(source.read_text() + json.dumps({"record": "footer", "declarations": 2, "complete": True}) + "\n")
        with self.assertRaises(CorpusError):
            import_corpus(source, destination)
        self.assertFalse(destination.exists())

    def test_existing_database_is_not_overwritten(self):
        source = self.write()
        destination = self.root / "existing.sqlite"
        destination.write_bytes(b"keep these bytes")
        with self.assertRaises(CorpusError) as caught:
            import_corpus(source, destination)
        self.assertEqual(caught.exception.code, "destination_exists")
        self.assertEqual(destination.read_bytes(), b"keep these bytes")

    def test_duplicate_ids_and_forward_references_in_expr_are_rejected(self):
        source = self.write([record(), record()])
        with self.assertRaises(CorpusError) as caught:
            import_corpus(source, self.root / "duplicate.sqlite")
        self.assertEqual(caught.exception.code, "duplicate_declaration")
        malformed = record()
        malformed["value_expr"] = {"nodes": [{"tag": "app", "data": [], "children": [0, 0]}], "root": 0, "truncated": False}
        with self.assertRaises(CorpusError) as caught:
            import_corpus(self.write([malformed]), self.root / "dag.sqlite")
        self.assertEqual(caught.exception.code, "invalid_expression")

    def test_caps_missing_values_and_contradictory_status_are_distinct(self):
        capped, axiom = record("capped"), record("axiom")
        capped["value_expr"], capped["expression_status"]["value"] = None, "node_limit"
        axiom["value_expr"], axiom["expression_status"]["value"] = None, "no_value"
        axiom["references"]["value"] = []
        with import_corpus(self.write([capped, axiom]), self.root / "caps.sqlite") as corpus:
            self.assertEqual(corpus.get_declaration("capped")["expression_status"]["value"], "node_limit")
            self.assertEqual(corpus.get_declaration("axiom")["expression_status"]["value"], "no_value")
            self.assertEqual(len(list(corpus.iter_references("value"))), 1)
        capped["expression_status"]["value"] = "available"
        with self.assertRaises(CorpusError):
            import_corpus(self.write([capped]), self.root / "contradiction.sqlite")

    def test_invalid_literal_and_absence_semantics_are_rejected(self):
        for value in ("-1", "banana", "01", "１"):
            invalid = record()
            invalid["value_expr"]["nodes"][0] = {"tag": "lit", "data": ["nat", value], "children": []}
            with self.subTest(value=value), self.assertRaises(CorpusError):
                import_corpus(self.write([invalid]), self.root / "bad.sqlite")
        invalid = record()
        invalid["type_expr"], invalid["expression_status"]["type"] = None, "no_value"
        with self.assertRaises(CorpusError):
            import_corpus(self.write([invalid]), self.root / "bad-type.sqlite")
        invalid = record()
        invalid["value_expr"], invalid["expression_status"]["value"] = None, "no_value"
        with self.assertRaises(CorpusError):
            import_corpus(self.write([invalid]), self.root / "bad-value.sqlite")

    def test_record_budget_and_duplicate_json_keys_fail_explicitly(self):
        with self.assertRaises(CorpusError) as caught:
            import_corpus(self.write(), self.root / "small.sqlite", max_record_bytes=10)
        self.assertEqual(caught.exception.code, "record_limit")
        bad = self.root / "duplicate.jsonl"
        bad.write_text('{"record":"header","record":"header","schema":"lpaf-corpus-v0.1"}\n')
        with self.assertRaises(CorpusError):
            import_corpus(bad, self.root / "keys.sqlite")

    def test_nonempty_records_after_footer_are_rejected(self):
        source = self.write()
        source.write_text(source.read_text() + json.dumps(record("extra")) + "\n")
        with self.assertRaises(CorpusError):
            import_corpus(source, self.root / "trailing.sqlite")

    def test_source_adapter_never_fabricates_expr_or_upgrades_references(self):
        source = self.root / "lean"
        source.mkdir()
        (source / "Demo.lean").write_text("theorem first : True := True.intro\ntheorem second : True := first\n")
        out = self.root / "report"
        analyze_project(source, out, repository="example/demo", commit="a" * 40)
        with import_source_report(out / "analysis.json", self.root / "source.sqlite") as corpus:
            rows = list(corpus.iter_declarations(include_expressions=True))
            self.assertTrue(all(d["evidence"] == "lexical_candidate" and d["type_expr"] is None and d["value_expr"] is None for d in rows))
            self.assertTrue(all(e["evidence"] == "lexical_candidate" for e in corpus.iter_references()))
            self.assertEqual(len(list(corpus.iter_references("value"))), 1)

    def test_view_filters_sources_but_preserves_reference_boundary(self):
        theorem, definition = record("Demo.theorem"), record("Demo.definition")
        definition["kind"] = "definition"
        theorem["references"]["value"] = ["Demo.definition"]
        with import_corpus(self.write([theorem, definition]), self.root / "view.sqlite") as corpus:
            view = corpus.select(kinds=["theorem"])
            self.assertEqual([d["id"] for d in view.iter_declarations()], ["Demo.theorem"])
            self.assertEqual(list(view.iter_references("value"))[0]["to"], "Demo.definition")
            self.assertEqual(view.metadata["declarations"], 1)
            self.assertEqual(view.metadata["unfiltered_counts"]["declarations"], 2)
            with self.assertRaises(CorpusError):
                view.get_declaration("Demo.definition")
            self.assertEqual(corpus.metadata["declarations"], 2)

    def test_view_namespace_prefix_is_case_sensitive_and_module_exact(self):
        records = [record("Demo.yes"), record("Demography.no"), record("demo.no")]
        records[0]["module"] = "Module.One"
        with import_corpus(self.write(records), self.root / "prefix.sqlite") as corpus:
            self.assertEqual([d["id"] for d in corpus.select(name_prefix="Demo").iter_declarations()], ["Demo.yes"])
            self.assertEqual([d["id"] for d in corpus.select(modules=["Module.One"]).iter_declarations()], ["Demo.yes"])
            self.assertEqual(list(corpus.select(kinds=[]).iter_declarations()), [])
            with self.assertRaises(CorpusError):
                corpus.select(kinds="theorem")


if __name__ == "__main__":
    unittest.main()
