"""Integration tests: CLI dispatch uses persisted corpus and the scientific APIs."""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lean_proof_analysis import analyze_project
from lean_proof_analysis.analysis_cli import ANALYSIS_COMMANDS, add_analysis_parsers, run_analysis_command
from lean_proof_analysis.corpus import CorpusError, open_corpus
from lean_proof_analysis.cli import main
from lean_proof_analysis.graph_analysis import analyze_dependencies, dependency_bottlenecks, dependency_overlap
from lean_proof_analysis.term_analysis import compare_term_structure, find_repeated_subterms, profile_terms


def parse(argv):
    parser = argparse.ArgumentParser()
    add_analysis_parsers(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(argv)


def expression(value="2"):
    return {"nodes": [{"tag": "const", "data": ["Nat.succ"], "children": []},
                      {"tag": "lit", "data": ["nat", value], "children": []},
                      {"tag": "app", "data": [], "children": [0, 1]}],
            "root": 2, "truncated": False}


class AnalysisCLITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "fixture.jsonl"
        self.db = self.root / "fixture.sqlite"
        # Deliberately synthetic expression data, not an assertion these test
        # records were produced by a real Lean invocation.
        rows = [{"record": "header", "schema": "lpaf-corpus-v0.1", "test_fixture": True}]
        for name, dependencies in [("Root", ["A", "B"]), ("A", ["B"]), ("B", [])]:
            rows.append({"record": "declaration", "id": name, "name": name, "kind": "def",
                         "module": "Fixture", "source_url": None, "evidence": "lean_elaborated",
                         "type_expr": {"nodes": [{"tag": "const", "data": ["Nat"], "children": []}],
                                       "root": 0, "truncated": False},
                         "value_expr": expression("3" if name == "Root" else "2"),
                         "expression_status": {"type": "available", "value": "available"},
                         "references": {"type": ["Nat"], "value": dependencies}})
        rows.append({"record": "footer", "declarations": 3, "complete": True})
        self.input.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def import_fixture(self):
        return run_analysis_command(parse(["corpus", "import", str(self.input), "--db", str(self.db), "--json"]))

    def test_import_and_info_report_persisted_inventory(self):
        result = self.import_fixture()
        self.assertTrue(self.db.is_file())
        self.assertEqual(result["data"]["counts"], {"declarations": 3, "references": 6})
        self.assertEqual(result["operation"], "import_corpus")
        info = run_analysis_command(parse(["corpus", "info", str(self.db), "--json"]))
        self.assertEqual(info["data"]["counts"], result["data"]["counts"])
        self.assertEqual(info["provenance"]["input"]["sha256"], result["provenance"]["input"]["sha256"])
        with self.assertRaises(CorpusError) as caught:
            self.import_fixture()
        self.assertEqual(caught.exception.code, "destination_exists")

    def test_graph_commands_match_the_library_payloads(self):
        self.import_fixture()
        cases = [
            (["graph", str(self.db), "--role", "value", "--root", "Root", "--top-k", "2"],
             lambda corpus: analyze_dependencies(corpus, role="value", roots=["Root"], top_k=2)),
            (["overlap", str(self.db), "Root", "A", "--role", "value", "--limit", "1"],
             lambda corpus: dependency_overlap(corpus, "Root", "A", role="value", limit=1)),
            (["bottlenecks", str(self.db), "Root", "--role", "value", "--top-k", "2", "--max-work", "1000"],
             lambda corpus: dependency_bottlenecks(corpus, "Root", role="value", top_k=2, max_work=1000)),
        ]
        for argv, library in cases:
            with self.subTest(command=argv[0]), open_corpus(self.db) as corpus:
                self.assertEqual(run_analysis_command(parse(argv + ["--json"])), library(corpus))

    def test_expression_commands_match_the_library_payloads(self):
        self.import_fixture()
        cases = [
            (["terms", str(self.db), "--field", "value", "--top-k", "2"],
             lambda corpus: profile_terms(corpus, field="value", top_k=2)),
            (["patterns", str(self.db), "--field", "value", "--min-nodes", "3",
              "--min-declarations", "2", "--limit", "4", "--max-unique-patterns", "100"],
             lambda corpus: find_repeated_subterms(corpus, field="value", min_nodes=3,
                                                   min_declarations=2, limit=4, max_unique_patterns=100)),
            (["term-compare", str(self.db), "A", "B", "--field", "value"],
             lambda corpus: compare_term_structure(corpus, "A", "B", field="value")),
        ]
        for argv, library in cases:
            with self.subTest(command=argv[0]), open_corpus(self.db) as corpus:
                self.assertEqual(run_analysis_command(parse(argv + ["--json"])), library(corpus))

    def test_source_import_keeps_candidate_edges_and_no_invented_terms(self):
        source = self.root / "source"
        source.mkdir()
        (source / "Demo.lean").write_text("theorem first : True := True.intro\ntheorem second : True := first\n", encoding="utf-8")
        out = self.root / "source-report"
        analyze_project(source, out, repository="example/demo", commit="a" * 40)
        run_analysis_command(parse(["corpus", "import", str(out / "analysis.json"), "--db", str(self.db), "--format", "source"]))
        graph = run_analysis_command(parse(["graph", str(self.db)]))
        self.assertEqual(set(graph["data"]["layers"]), {"lexical_candidate"})
        compared = run_analysis_command(parse(["term-compare", str(self.db), "first", "second"]))
        self.assertEqual(compared["data"]["relation"], "unavailable")

    def test_invalid_graph_limits_remain_an_error(self):
        self.import_fixture()
        with self.assertRaises(ValueError):
            run_analysis_command(parse(["graph", str(self.db), "--top-k", "0"]))
        with self.assertRaises(ValueError):
            run_analysis_command(argparse.Namespace(command="not-an-analysis-command"))

    def relabel_fixture(self):
        rows = [json.loads(line) for line in self.input.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row["record"] == "declaration":
                row["kind"] = "definition" if row["id"] == "Root" else "theorem"
                row["module"] = "Generated" if row["id"] == "Root" else "Proofs"
        self.input.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_selected_graph_keeps_unselected_targets_as_boundary(self):
        self.relabel_fixture()
        self.import_fixture()
        result = run_analysis_command(parse([
            "graph", str(self.db), "--role", "value", "--kind", "theorem",
            "--module", "Proofs", "--prefix", "A", "--json",
        ]))
        self.assertEqual(result["data"]["declarations"], 1)
        data = result["data"]["layers"]["lean_elaborated"]
        self.assertEqual(data["internal_edges"], 0)
        self.assertEqual(data["outside_edges"], 1)
        self.assertEqual(data["top_referenced"][0]["id"], "B")
        self.assertFalse(data["top_referenced"][0]["in_corpus"])

    def test_every_analysis_command_uses_the_same_selected_view(self):
        self.relabel_fixture()
        self.import_fixture()
        cases = [
            (["graph", str(self.db)], lambda view: analyze_dependencies(view)),
            (["overlap", str(self.db), "A", "B"], lambda view: dependency_overlap(view, "A", "B")),
            (["bottlenecks", str(self.db), "A"], lambda view: dependency_bottlenecks(view, "A")),
            (["terms", str(self.db)], lambda view: profile_terms(view)),
            (["patterns", str(self.db)], lambda view: find_repeated_subterms(view)),
            (["term-compare", str(self.db), "A", "B"], lambda view: compare_term_structure(view, "A", "B")),
        ]
        for argv, library in cases:
            with self.subTest(command=argv[0]), open_corpus(self.db) as corpus:
                view = corpus.select(kinds=["theorem"], modules=["Proofs"], name_prefix=None)
                actual = run_analysis_command(parse(argv + ["--kind", "theorem", "--module", "Proofs", "--json"]))
                self.assertEqual(actual, library(view))

    def test_repeatable_selection_flags_allow_multiple_exact_kinds_and_modules(self):
        self.relabel_fixture()
        self.import_fixture()
        result = run_analysis_command(parse([
            "graph", str(self.db), "--kind", "theorem", "--kind", "definition",
            "--module", "Proofs", "--module", "Generated",
        ]))
        self.assertEqual(result["data"]["declarations"], 3)
        args = parse(["terms", str(self.db), "--kind", "custom-kind"])
        self.assertEqual(args.kind, ["custom-kind"])

    def test_selected_identity_queries_do_not_escape_the_view(self):
        self.relabel_fixture()
        self.import_fixture()
        with self.assertRaises(ValueError):
            run_analysis_command(parse(["term-compare", str(self.db), "Root", "A", "--kind", "theorem"]))

    def test_all_expected_commands_are_registered(self):
        self.assertEqual(ANALYSIS_COMMANDS,
                         {"export", "corpus", "graph", "overlap", "bottlenecks", "terms", "patterns", "term-compare"})

    def test_export_dispatch_preserves_selection_and_explicit_runner(self):
        binary = self.root / "toolchain" / "lean"
        result = {"schema": "lpaf-export-v0.1", "declarations": 12}
        with patch("lean_proof_analysis.analysis_cli.export_lean", return_value=result) as exporter:
            actual = run_analysis_command(parse([
                "export", str(self.root), "--out", str(self.input),
                "--module", "Fixture", "--module", "Init", "--prefix", "Example",
                "--name", "Other.seed", "--lean", str(binary), "--max-declarations", "20",
                "--max-nodes", "300", "--timeout", "15", "--lean-path", str(self.root), "--json",
            ]))
        self.assertEqual(actual, result)
        exporter.assert_called_once_with(
            self.root, self.input, modules=["Fixture", "Init"], prefixes=["Example"],
            names=["Other.seed"], runner=(str(binary.resolve()),), max_declarations=20,
            max_nodes=300, timeout=15.0, lean_path=self.root,
        )

    def test_export_failure_is_a_structured_cli_error(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["export", str(self.root), "--out", str(self.root / "new.jsonl"),
                              "--module", "Init", "--json"])
        self.assertEqual(exit_code, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["schema"], "lpaf-analysis-v0.1")
        self.assertEqual(result["error"]["code"], "missing_toolchain")
        self.assertFalse((self.root / "new.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
