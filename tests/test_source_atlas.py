"""Executable unit tests; run `python -m unittest discover -s tests -v`."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lean_proof_analysis.source_atlas import masked, git_blob_sha, scan_file, analyze


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

if __name__=='__main__':unittest.main()
