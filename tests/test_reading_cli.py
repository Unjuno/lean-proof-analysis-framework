"""Public reader commands must expose the same evidence as the Python API."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from lean_proof_analysis.api import analyze_project
from lean_proof_analysis.cli import main
from lean_proof_analysis.presentation import render_markdown
from lean_proof_analysis.reading import (
    compare_declarations,
    dependency_slice,
    find_similar,
    get_declaration,
    list_declarations,
)


class ReadingCLITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "src"
        root.mkdir()
        source = (
            "namespace Demo\n"
            "def bound : Nat := 7\n"
            "theorem first : bound = bound := rfl\n"
            "theorem target : bound = bound := Demo.first\n"
            "theorem alternative : bound = bound := by\n  exact Demo.first\n"
            'def longLabel : String := "' + "long captured text " * 30 + '"\n'
            "end Demo\n"
            "namespace Other\n"
            "theorem first : True := True.intro\n"
            "end Other\n"
        )
        (root / "Fixture.lean").write_text(source, encoding="utf-8")
        self.output = Path(self.temp.name) / "out"
        self.report = analyze_project(root, self.output, repository="example/fixture", commit="a" * 40)
        self.path = str(self.output / "analysis.json")

    def invoke(self, args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_json_result(self, args, expected):
        code, stdout, stderr = self.invoke(args + ["--json"])
        self.assertEqual(code, 0, stderr or stdout)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), expected)

    def test_all_reader_commands_match_python_api(self):
        cases = [
            (["search", self.path, "Demo", "--kind", "theorem", "--limit", "1"],
             list_declarations(self.report, query="Demo", kind="theorem", limit=1)),
            (["inspect", self.path, "Demo.target", "--max-chars", "8", "--source-text"],
             get_declaration(self.report, "Demo.target", max_chars=8, include_source=True)),
            (["compare", self.path, "Demo.target", "Demo.alternative"],
             compare_declarations(self.report, "Demo.target", "Demo.alternative")),
            (["slice", self.path, "Demo.first", "--direction", "dependents", "--role", "body", "--max-depth", "1"],
             dependency_slice(self.report, "Demo.first", direction="dependents", role="body", max_depth=1)),
            (["similar", self.path, "Demo.target", "--limit", "1"],
             find_similar(self.report, "Demo.target", limit=1)),
        ]
        for args, expected in cases:
            with self.subTest(command=args[0]):
                self.assert_json_result(args, expected)

    def test_inspect_full_text_and_explicit_truncation(self):
        code, stdout, _ = self.invoke(["inspect", self.path, "Demo.longLabel", "--max-chars", "8", "--json"])
        self.assertEqual(code, 0)
        body = json.loads(stdout)["data"]["declaration"]["text"]["body"]
        self.assertTrue(body["truncated"])
        self.assertEqual(body["returned_characters"], 8)
        self.assert_json_result(
            ["inspect", self.path, "Demo.longLabel", "--full-text", "--source-text"],
            get_declaration(self.report, "Demo.longLabel", max_chars=None, include_source=True),
        )

    def test_slice_direction_and_bounds_are_visible(self):
        code, stdout, stderr = self.invoke([
            "slice", self.path, "Demo.first", "--direction", "dependents", "--role", "body",
            "--max-depth", "0", "--max-nodes", "1", "--json",
        ])
        self.assertEqual(code, 0, stderr)
        result = json.loads(stdout)
        self.assertEqual(result["data"]["direction"], "dependents")
        self.assertEqual(result["data"]["role"], "body")
        self.assertEqual(len(result["data"]["nodes"]), 1)
        self.assertFalse(result["data"]["traversal_complete"])
        self.assertGreater(result["data"]["frontier_total"], 0)
        self.assertFalse(result["coverage"]["semantic_dependencies_complete"])

    def test_json_errors_have_one_machine_readable_object(self):
        cases = [
            ["inspect", self.path, "first", "--json"],
            ["inspect", self.path, "missing", "--json"],
            ["search", self.path, "--limit", "-1", "--json"],
            ["slice", self.path, "Demo.target", "--direction", "wrong", "--json"],
            ["inspect", self.path, "Demo.target", "--full-text", "--max-chars", "8", "--json"],
            ["inspect", str(Path(self.temp.name) / "absent.json"), "Demo.target", "--json"],
        ]
        for args in cases:
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual(code, 2)
                self.assertEqual(stderr, "")
                result = json.loads(stdout)
                self.assertEqual(result["schema"], "lpaf-reading-v0.1")
                self.assertTrue(result["error"]["code"])
                self.assertTrue(result["error"]["message"])
                self.assertIn("details", result["error"])

    def test_bad_json_and_analyze_errors_are_structured(self):
        invalid = Path(self.temp.name) / "invalid.json"
        invalid.write_text("{not json", encoding="utf-8")
        for args in (
            ["search", str(invalid), "--json"],
            ["analyze", str(Path(self.temp.name) / "missing"), "--repo", "example/fixture",
             "--commit", "a" * 40, "--out", str(self.output), "--json"],
        ):
            code, stdout, stderr = self.invoke(args)
            self.assertEqual(code, 2)
            self.assertEqual(stderr, "")
            self.assertIn("error", json.loads(stdout))

    def test_markdown_uses_same_result_and_preserves_limits(self):
        expected = get_declaration(self.report, "Demo.longLabel", max_chars=8)
        code, stdout, stderr = self.invoke(["inspect", self.path, "Demo.longLabel", "--max-chars", "8"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, render_markdown(expected) + "\n")
        self.assertIn("Output truncated", stdout)
        self.assertIn("Reading limits", stdout)
        self.assertIn("https://github.com/example/fixture/blob/", stdout)

    def test_all_markdown_commands_render(self):
        commands = [
            ["search", self.path],
            ["compare", self.path, "Demo.target", "Demo.alternative"],
            ["slice", self.path, "Demo.target"],
            ["similar", self.path, "Demo.target"],
        ]
        for args in commands:
            with self.subTest(command=args[0]):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual(code, 0, stderr)
                self.assertIn("Reading limits", stdout)
                self.assertIn("not a proof check", stdout)

    def test_incomplete_or_size_skipped_diff_is_not_an_empty_success(self):
        legacy = deepcopy(self.report)
        legacy["schema"] = "lean-atlas-v0.1"
        for declaration in legacy["declarations"]:
            declaration.pop("text_truncated", None)
        text = render_markdown(compare_declarations(legacy, "Demo.target", "Demo.alternative"))
        self.assertIn("Relationship unknown: incomplete input", text)
        self.assertIn("input_incomplete", text)
        self.assertNotIn("Same captured text", text)

        large = deepcopy(self.report)
        target = next(d for d in large["declarations"] if d["name"] == "Demo.target")
        target["body"] = "line\n" * 4001
        text = render_markdown(compare_declarations(large, "Demo.target", "Demo.alternative"))
        self.assertIn("skipped_size_limit", text)
        self.assertIn("detailed diff exceeds the line budget", text)

    def test_markdown_reports_omitted_edges(self):
        result = dependency_slice(self.report, "Demo.target")
        result["data"]["edges_truncated"] = True
        result["data"]["edges_total"] = 100
        self.assertIn("Edge output truncated", render_markdown(result))

    def test_inserted_diff_lines_use_an_insertion_point(self):
        report = deepcopy(self.report)
        left = next(d for d in report["declarations"] if d["name"] == "Demo.target")
        right = next(d for d in report["declarations"] if d["name"] == "Demo.alternative")
        left["body"] = "by\n  exact Demo.first\n"
        right["body"] = "by\n  -- an added source comment\n  exact Demo.first\n"
        Path(self.path).write_text(json.dumps(report), encoding="utf-8")
        code, stdout, stderr = self.invoke(["compare", self.path, "Demo.target", "Demo.alternative"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("insertion point after captured-text line 1", stdout)
        self.assertNotIn("None–None", stdout)


if __name__ == "__main__":
    unittest.main()
