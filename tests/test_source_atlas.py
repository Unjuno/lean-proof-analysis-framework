"""Executable unit tests; run `python -m unittest discover -s tests -v`."""
import hashlib
import csv
import json
from pathlib import Path
import tempfile
import unittest

from lean_proof_analysis.source_atlas import masked, without_comments, git_blob_sha, scan_file, analyze, normalized_expression


class AtlasTest(unittest.TestCase):
    def test_nested_comments_and_string(self):
        s = 'theorem x : True := by\n  /- a /- theorem fake : False -/ z -/\n  exact True.intro -- theorem bogus : False\n  #eval "theorem hidden : False"\n'
        m = masked(s)
        self.assertNotIn('fake',m)
        self.assertNotIn('bogus',m)
        self.assertNotIn('hidden',m)
        self.assertIn('theorem x',m)
        self.assertEqual(s.count('\n'),m.count('\n'))

    def test_git_blob_hash_known(self):
        self.assertEqual(git_blob_sha(b'hello\n'),'ce013625030ba8dba906f756967f9e9ca394464a')

    def test_namespace_and_scope(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'src'/'A.lean';p.parent.mkdir()
            p.write_text('namespace A\n\nsection\n\ntheorem x : True := True.intro\n\nend\n\ntheorem y : True := x\nend A\n',encoding='utf-8')
            dd,imps,info=scan_file(p,Path(d),'https://example.org')
            self.assertEqual([x.name for x in dd],['A.x','A.y'])
            self.assertEqual(info['declarations'],2)

    def test_prop_definition_compared_by_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'sample';root.mkdir()
            (root/'Test.lean').write_text('def P : Prop := 1 = 2\ndef Q : Prop := 2 = 3\ndef R : Prop := 1 = 2\n',encoding='utf-8')
            r=analyze(root,Path(tmp)/'out','someone/repo','d'*40)
            p={(x['from'].split(':')[-1],x['to'].split(':')[-1]):x for x in r['similarity_candidates']}
            self.assertTrue(p[('P','R')]['same_syntax_fingerprint'])
            self.assertFalse(p.get(('P','Q'),{}).get('same_syntax_fingerprint',False))

    def test_projection_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'sample';root.mkdir()
            (root/'Test.lean').write_text('theorem claimAll : True := True.intro\ntheorem target : True := claimAll.2.1\n',encoding='utf-8')
            r=analyze(root,Path(tmp)/'out','someone/repo','d'*40)
            self.assertTrue(any(x['evidence_token']=='claimAll.2.1' and x['to'].endswith(':claimAll') for x in r['candidate_links']))

    def test_manifest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'sample';root.mkdir()
            (root/'T.lean').write_text('theorem t : True := True.intro\n')
            with self.assertRaisesRegex(ValueError,'SOURCE HASH MISMATCH'):
                analyze(root,Path(tmp)/'out','someone/repo','d'*40,expected={'T.lean':'f'*40})


    def test_string_literal_values_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"Text.lean").write_text('def A : String := "red"\ndef B : String := "blue"\n', encoding="utf-8")
            r=analyze(root,Path(tmp)/"out","example/synthetic","0"*40)
            self.assertFalse(any(x["same_syntax_fingerprint"] for x in r["similarity_candidates"]))

    def test_missing_manifest_file_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"A.lean").write_text('theorem a : True := True.intro\n',encoding="utf-8")
            manifest={"A.lean":git_blob_sha((root/"A.lean").read_bytes()), "B.lean":"0"*40}
            with self.assertRaisesRegex(ValueError,"SOURCE MANIFEST INCOMPLETE"):
                analyze(root,Path(tmp)/"out","example/synthetic","0"*40,expected=manifest)

    def test_complete_manifest_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"A.lean").write_text('theorem a : True := True.intro\n',encoding="utf-8")
            manifest={"A.lean":git_blob_sha((root/"A.lean").read_bytes())}
            r=analyze(root,Path(tmp)/"out","example/synthetic","0"*40,expected=manifest)
            self.assertTrue(r["provenance"]["source_hashes_checked"])
            self.assertTrue(r["provenance"]["manifest_complete"])

    def test_pair_cap_on_equal_source_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"A.lean").write_text(''.join(f'theorem t{i} : True := True.intro\n' for i in range(30)))
            r=analyze(root,Path(tmp)/"out","example/synthetic","0"*40,max_pairs=12)
            self.assertLessEqual(r["summary"]["similarity_search"]["potential_pairs_examined"],12)

    def test_complete_captured_text_and_explicit_csv_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            signature='(label : String := "'+('x'*220)+'") : True'
            body='by\n  have anotherLabel := "'+('y'*120)+'"\n  exact True.intro'
            source='theorem longOne '+signature+' := '+body+'\n'
            (root/"Long.lean").write_text(source,encoding="utf-8")
            out=Path(tmp)/"out"
            report=analyze(root,out,"example/synthetic","0"*40)
            declaration=report["declarations"][0]
            self.assertEqual(report["schema"],"lean-atlas-v0.2")
            self.assertEqual(declaration["statement"],signature)
            self.assertEqual(declaration["body"],body)
            self.assertEqual(declaration["source_text"],source)
            self.assertEqual(declaration["text_truncated"],
                             {"statement":False,"body":False,"source_text":False})
            self.assertEqual(declaration["extraction"]["boundaries"],"heuristic")
            self.assertFalse(declaration["extraction"]["elaborated"])
            self.assertFalse(declaration["extraction"]["context_complete"])
            persisted=json.loads((out/"analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["declarations"][0]["source_text"],source)
            with (out/"index.csv").open(encoding="utf-8",newline="") as stream:
                row=next(csv.DictReader(stream))
            self.assertEqual(len(row["statement"]),180)
            self.assertEqual(len(row["body"]),70)
            self.assertEqual(row["statement_truncated"],"True")
            self.assertEqual(row["body_truncated"],"True")

    def test_internal_whitespace_and_literal_characters_are_distinct(self):
        for left,right in [
            ('"a  b"','"a b"'),
            ("' '","'\\t'"),
            ('«a  b»','«a b»'),
            ('by\n  exact h','by exact h'),
        ]:
            with self.subTest(left=left,right=right):
                self.assertNotEqual(normalized_expression(left),normalized_expression(right))
        self.assertEqual(normalized_expression('  : True\n'),': True')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"Text.lean").write_text(
                'def A : String := "a  b"\ndef B : String := "a b"\n',encoding="utf-8")
            report=analyze(root,Path(tmp)/"out","example/synthetic","0"*40)
            self.assertEqual(report["declarations"][0]["body"],'"a  b"')
            self.assertNotEqual(report["declarations"][0]["statement_fp"],
                                report["declarations"][1]["statement_fp"])
            self.assertFalse(any(row["same_syntax_fingerprint"] for row in report["similarity_candidates"]))

    def test_quoted_separator_and_parenthesis_do_not_split_statement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source='theorem delimiters : ":=(" = ":=(" := by\n  rfl\n'
            path=root/"Quoted.lean"; path.write_text(source,encoding="utf-8")
            declarations,_,_=scan_file(path,root,"https://example.org")
            self.assertEqual(declarations[0].statement,': ":=(" = ":=("')
            self.assertEqual(declarations[0].body,'by\n  rfl')

    def test_tactic_and_reference_candidates_ignore_strings_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"Tokens.lean").write_text(
                'theorem known : True := True.intro\n'
                'def label : String := "simp exact known" /- rw known -/\n'
                'theorem used : True := by\n  exact known -- simp\n',encoding="utf-8")
            report=analyze(root,Path(tmp)/"out","example/synthetic","0"*40)
            by_name={row["name"]:row for row in report["declarations"]}
            self.assertEqual(by_name["label"]["tactics"],[])
            self.assertEqual(by_name["used"]["tactics"],["exact"])
            self.assertFalse(any(row["from"]==by_name["label"]["id"] for row in report["candidate_links"]))
            self.assertTrue(any(row["from"]==by_name["used"]["id"] and row["to"]==by_name["known"]["id"]
                                for row in report["candidate_links"]))

    def test_multiline_strings_preserve_line_offsets(self):
        source='def text : String := "line one\nline two"\ntheorem after : True := True.intro\n'
        self.assertEqual(masked(source).count('\n'),source.count('\n'))
        self.assertEqual(len(masked(source)),len(source))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/"Lines.lean"
            path.write_text(source,encoding="utf-8")
            declarations,_,_=scan_file(path,root,"https://example.org")
            self.assertEqual(declarations[1].line,3)

    def test_import_inventory_marks_outside_sample_without_missing_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"sample"; root.mkdir()
            (root/"Local.lean").write_text('theorem localFact : True := True.intro\n',encoding="utf-8")
            (root/"Main.lean").write_text('import Local Mathlib.Unknown\ntheorem t : True := localFact\n',encoding="utf-8")
            report=analyze(root,Path(tmp)/"out","example/synthetic","0"*40)
            self.assertEqual(report["imports_by_file"]["Main.lean"],["Local","Mathlib.Unknown"])
            self.assertEqual(report["imports_outside_sample"],[
                {"path":"Main.lean","module":"Mathlib.Unknown","status":"not-in-analyzed-sample"}])
            self.assertEqual(report["import_links"],[
                {"from":"Main.lean","to":"Local.lean","evidence":"explicit-import"}])

    def test_character_raw_string_and_quoted_identifier_contents_survive(self):
        raw_literal='r##"one " -- literal /- text -/ two"##'
        quoted_name='«name--still  name»'
        source=("def quote : Char := '\"'\n"
                'def raw : String := '+raw_literal+'\n'
                'def reference := '+quoted_name+'\n'
                'theorem last : True := True.intro\n')
        self.assertEqual(without_comments(source),source)
        self.assertNotIn('literal',masked(source))
        self.assertNotIn('still',masked(source))
        self.assertIn('theorem last',masked(source))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/"Literal.lean"
            path.write_text(source,encoding="utf-8")
            declarations,_,_=scan_file(path,root,"https://example.org")
            self.assertEqual([d.name for d in declarations],["quote","raw","reference","last"])
            self.assertEqual(declarations[0].body,"'\"'")
            self.assertEqual(declarations[1].body,raw_literal)
            self.assertEqual(declarations[2].body,quoted_name)

if __name__=='__main__':unittest.main()
