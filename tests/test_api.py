import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from lean_proof_analysis import analyze_project, load_report
from lean_proof_analysis.cli import main

class PublicAPITest(unittest.TestCase):
    def fixture(self, root):
        root.mkdir()
        (root / "Demo.lean").write_text("namespace Demo\ntheorem x : True := True.intro\nend Demo\n", encoding="utf-8")

    def test_api_writes_reports(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/"src"; self.fixture(root)
            out=Path(t)/"out"
            report=analyze_project(root,out,repository="example/demo",commit="0"*40,entry_points=["Demo.x"])
            self.assertEqual(report["mode"],"source-only-unelaborated")
            self.assertTrue(report["not_proof_check"])
            self.assertTrue((out/"analysis.json").exists())
            self.assertEqual(load_report(out/"analysis.json")["summary"]["declarations"],1)

    def test_cli_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/"src"; self.fixture(root)
            out=Path(t)/"out"
            stdout=StringIO()
            with redirect_stdout(stdout):
                code=main(["analyze",str(root),"--out",str(out),"--repo","example/demo","--commit","0"*40,"--json"])
            self.assertEqual(code,0)
            record=json.loads(stdout.getvalue())
            self.assertTrue(record["not_proof_check"])
            self.assertEqual(record["summary"]["files"],1)

    def test_invalid_source_returns_error_code(self):
        with tempfile.TemporaryDirectory() as t:
            stderr=StringIO()
            with redirect_stderr(stderr):
                code=main(["analyze",t,"--repo","example/demo","--commit","0"*40])
            self.assertEqual(code,2)
            self.assertIn("No Lean",stderr.getvalue())

if __name__ == '__main__':
    unittest.main()
