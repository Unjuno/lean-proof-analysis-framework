"""Extraction runner lifecycle, provenance and atomic publication checks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from lean_proof_analysis.extraction import ExportError, export_lean

FAKE_RUNNER = r'''
import json, os, subprocess, sys, time
mode = sys.argv[1]
args = sys.argv[2:]
def values(flag):
    return [args[i+1] for i, arg in enumerate(args[:-1]) if arg == flag]
maximum = int(values('--max-declarations')[0])
nodes = int(values('--max-nodes')[0])
if mode == 'fail':
    sys.stderr.write('x' * 20000 + ' FINAL ERROR')
    sys.exit(7)
if mode == 'timeout':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    open('child.pid', 'w').write(str(child.pid))
    print('partial output', flush=True)
    time.sleep(60)
header = {'record':'header','schema':'lpaf-corpus-v0.1','lean_version':'4.33.1',
          'evidence':'lean_elaborated','not_proof_check':True,
          'modules':values('--module'),'prefixes':values('--prefix'),'names':values('--name')}
expr = {'nodes':[{'tag':'const','data':['True'],'children':[]}],'root':0,'truncated':False}
decl = {'record':'declaration','id':'Fixture.x','name':'Fixture.x','kind':'theorem',
        'module':'Fixture','source_url':None,'evidence':'lean_elaborated',
        'type_expr':expr,'value_expr':None,
        'expression_status':{'type':'available','value':'unavailable'},
        'references':{'type':['True'],'value':[]}}
footer = {'record':'footer','declarations':1,'matched_declarations':1,'complete':True,
          'limits':{'max_declarations':maximum,'max_nodes_per_expression':nodes}}
if mode == 'capped':
    footer['matched_declarations'] = maximum+5
    footer['complete'] = False
if mode == 'bad-count':
    footer['declarations'] = 2
if mode == 'changed-project':
    open('lean-toolchain','w').write('leanprover/lean4:v4.33.2\n')
print(json.dumps(header))
print(json.dumps(decl))
if mode != 'incomplete':
    print(json.dumps(footer))
'''


class ExtractionRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.pin = self.project / "lean-toolchain"
        self.pin.write_text("leanprover/lean4:v4.33.1\n", encoding="utf-8")
        self.script = self.root / "fake.py"
        self.script.write_text(FAKE_RUNNER, encoding="utf-8")
        self.output = self.root / "corpus.jsonl"

    def run_export(self, mode="ok", **options):
        return export_lean(self.project, self.output, modules=["Fixture"],
                           runner=[sys.executable, str(self.script), mode], **options)

    def assert_no_partial_output(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".lpaf-export-*")))

    def test_success_is_atomic_hashed_and_attaches_provenance(self):
        manifest = self.project / "lake-manifest.json"
        manifest.write_text('{"version":"1.1.0"}', encoding="utf-8")
        literal_prefix = "not-a-shell-command; touch SHOULD_NOT_EXIST"
        result = self.run_export(prefixes=[literal_prefix])
        self.assertEqual(result["operation"], "export_lean")
        self.assertEqual(result["declarations"], 1)
        self.assertEqual(result["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        records = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(records[0]["prefixes"], [literal_prefix])
        self.assertEqual(records[0]["provenance"], result["provenance"])
        self.assertEqual(result["provenance"]["lean_toolchain"]["sha256"], hashlib.sha256(self.pin.read_bytes()).hexdigest())
        self.assertEqual(result["provenance"]["lake_manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
        self.assertEqual(result["provenance"]["toolchain_version_check"], "matched")
        self.assertFalse((self.project / "SHOULD_NOT_EXIST").exists())
        self.assertFalse(list(self.root.glob(".lpaf-export-*")))

    def test_existing_output_is_never_overwritten(self):
        self.output.write_text("existing", encoding="utf-8")
        with self.assertRaises(ExportError) as caught:
            self.run_export()
        self.assertEqual(caught.exception.code, "destination_exists")
        self.assertEqual(self.output.read_text(), "existing")

    def test_failed_process_has_bounded_error_tail_and_no_published_output(self):
        with self.assertRaises(ExportError) as caught:
            self.run_export("fail")
        error = caught.exception.as_dict()
        self.assertEqual(error["code"], "export_process_failed")
        self.assertEqual(error["details"]["returncode"], 7)
        self.assertTrue(error["details"]["stderr_tail"].endswith(" FINAL ERROR"))
        self.assertLess(len(error["details"]["stderr_tail"]), 8300)
        self.assert_no_partial_output()

    def test_toolchain_mismatch_and_project_mutation_are_rejected(self):
        self.pin.write_text("leanprover/lean4:v4.33.2\n", encoding="utf-8")
        with self.assertRaises(ExportError) as caught:
            self.run_export()
        self.assertEqual(caught.exception.code, "toolchain_mismatch")
        self.assert_no_partial_output()
        self.pin.write_text("leanprover/lean4:v4.33.1\n", encoding="utf-8")
        with self.assertRaises(ExportError) as caught:
            self.run_export("changed-project")
        self.assertEqual(caught.exception.code, "project_changed")
        self.assert_no_partial_output()

    def test_missing_footer_and_incorrect_counts_do_not_publish(self):
        for mode, code in [("incomplete", "incomplete_export"), ("bad-count", "invalid_export")]:
            with self.subTest(mode=mode), self.assertRaises(ExportError) as caught:
                self.run_export(mode)
            self.assertEqual(caught.exception.code, code)
            self.assert_no_partial_output()

    def test_bounded_selection_is_valid_but_not_complete(self):
        result = self.run_export("capped", max_declarations=1)
        self.assertFalse(result["selection_complete"])
        self.assertTrue(self.output.exists())

    def test_timeout_cleans_process_group_and_temporary_output(self):
        with self.assertRaises(ExportError) as caught:
            self.run_export("timeout", timeout=0.5)
        self.assertEqual(caught.exception.code, "export_timeout")
        self.assert_no_partial_output()
        if sys.platform.startswith("linux"):
            pid = int((self.project / "child.pid").read_text())
            status = Path(f"/proc/{pid}/stat")
            deadline = time.monotonic() + 1.0
            while status.exists() and time.monotonic() < deadline:
                try:
                    if status.read_text().split()[2] == "Z":
                        break
                except FileNotFoundError:
                    break
                time.sleep(0.01)
            if status.exists():
                self.assertEqual(status.read_text().split()[2], "Z")

    def test_invalid_arguments_and_missing_pin_fail_before_execution(self):
        for options in ({"max_nodes": 0}, {"timeout": float("nan")}, {"prefixes": "Fixture"}):
            with self.subTest(options=options), self.assertRaises(ExportError) as caught:
                self.run_export(**options)
            self.assertEqual(caught.exception.code, "invalid_argument")
        self.pin.unlink()
        with self.assertRaises(ExportError) as caught:
            self.run_export()
        self.assertEqual(caught.exception.code, "missing_toolchain")


@unittest.skipUnless(os.environ.get("LPAF_LEAN"), "Set LPAF_LEAN for actual Lean runner integration")
class LeanRunnerIntegrationTest(unittest.TestCase):
    def test_python_runner_loads_real_built_module_and_records_pinned_version(self):
        binary = Path(os.environ["LPAF_LEAN"]).resolve()
        fixture_root = Path(__file__).resolve().parents[1] / "lean"
        with tempfile.TemporaryDirectory() as directory:
            built = Path(directory)
            environment = dict(os.environ)
            environment["PATH"] = str(binary.parent) + os.pathsep + environment.get("PATH", "")
            subprocess.run([str(binary), "-o", str(built / "Fixture.olean"), "Fixture.lean"],
                           cwd=fixture_root, env=environment, check=True, capture_output=True, timeout=120)
            result = export_lean(fixture_root, built / "real.jsonl", modules=["Fixture"],
                                 prefixes=["LPAF.Fixture"], runner=[str(binary)], lean_path=built)
            self.assertEqual(result["provenance"]["lean_version"], "4.33.1")
            self.assertTrue(result["selection_complete"])
            records = [json.loads(line) for line in (built / "real.jsonl").read_text().splitlines()]
            proof = next(record for record in records[1:-1] if record["id"] == "LPAF.Fixture.trueCopy")
            self.assertIsNotNone(proof["value_expr"])
            self.assertEqual(proof["expression_status"]["value"], "available")


if __name__ == "__main__":
    unittest.main()
