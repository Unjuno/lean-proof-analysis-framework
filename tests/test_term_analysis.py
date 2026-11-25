"""Known structural outcomes, including DAG sharing and incomplete evidence."""
from copy import deepcopy
import unittest

from lean_proof_analysis.term_analysis import (
    TermAnalysisError, compare_term_structure, find_repeated_subterms, profile_terms,
)


class MemoryCorpus:
    def __init__(self, declarations):
        self.records = {d["id"]: deepcopy(d) for d in declarations}
        self.metadata = {"fixture": "synthetic-expression-dags", "lean_version": "test-only"}

    def iter_declarations(self, include_expressions=False):
        for key in sorted(self.records):
            yield deepcopy(self.records[key])

    def get_declaration(self, identifier, include_expressions=True):
        return deepcopy(self.records.get(identifier))


def node(tag, data=(), children=(), **extra):
    return {"tag": tag, "data": list(data), "children": list(children), **extra}


def expr(nodes, root=None):
    return {"nodes": nodes, "root": len(nodes) - 1 if root is None else root, "truncated": False}


def declaration(identifier, expression, *, status="available", field="value"):
    return {"id": identifier, "name": identifier, "kind": "theorem", "module": "Fixture",
            "evidence": "synthetic", "source_url": None,
            "type_expr": None, "value_expr": None, field + "_expr": expression,
            "expression_status": {"type": "unavailable", "value": "unavailable", field: status}}


def identity(binder="x", *, index="0", level="0", binder_info="default"):
    return expr([node("sort", [level]), node("bvar", [index]),
                 node("lam", [binder_info], [0, 1], binder_name=binder)])


class TermAnalysisTest(unittest.TestCase):
    def test_display_binder_renaming_keeps_structure_but_binding_indices_do_not(self):
        corpus = MemoryCorpus([declaration("a", identity("x")), declaration("b", identity("renamed")),
                               declaration("c", identity(index="1"))])
        same = compare_term_structure(corpus, "a", "b")
        self.assertTrue(same["data"]["same_structure"])
        self.assertEqual(same["data"]["relation"], "same_encoded_structure")
        changed = compare_term_structure(corpus, "a", "c")["data"]
        self.assertFalse(changed["same_structure"])
        self.assertEqual(changed["first_difference"]["child_path"], [1])
        self.assertEqual(changed["right"]["required_context_binders"], 1)
        self.assertFalse(same["coverage"]["proof_correctness_assessed"])

    def test_binder_info_universes_constants_and_literal_values_are_retained(self):
        cases = [
            (identity(), identity(binder_info="implicit")),
            (identity(level="0"), identity(level="u")),
            (expr([node("const", ["Nat", "u"])]), expr([node("const", ["Nat", "v"])])),
            (expr([node("const", ["Nat"])]), expr([node("const", ["Int"])])),
            (expr([node("lit", ["str", "a b"])]), expr([node("lit", ["str", "a  b"])])),
            (expr([node("lit", ["nat", "1"])]), expr([node("lit", ["nat", "2"])])),
        ]
        for left, right in cases:
            with self.subTest(left=left, right=right):
                corpus = MemoryCorpus([declaration("a", left), declaration("b", right)])
                self.assertFalse(compare_term_structure(corpus, "a", "b")["data"]["same_structure"])

    def test_ordered_application_children_are_not_a_bag(self):
        left = expr([node("const", ["f"]), node("const", ["x"]), node("app", [], [0, 1])])
        right = expr([node("const", ["f"]), node("const", ["x"]), node("app", [], [1, 0])])
        data = compare_term_structure(MemoryCorpus([declaration("a", left), declaration("b", right)]), "a", "b")["data"]
        self.assertFalse(data["same_structure"])
        self.assertEqual(data["first_difference"]["child_path"], [0])

    def test_serialization_sharing_does_not_change_structural_identity(self):
        shared = expr([node("const", ["x"]), node("app", [], [0, 0])])
        unshared = expr([node("const", ["x"]), node("const", ["x"]), node("app", [], [0, 1])])
        data = compare_term_structure(MemoryCorpus([declaration("a", shared), declaration("b", unshared)]), "a", "b")["data"]
        self.assertTrue(data["same_structure"])
        self.assertEqual(data["left"]["reachable_dag_nodes"], 2)
        self.assertEqual(data["right"]["reachable_dag_nodes"], 3)
        self.assertEqual(data["left"]["expanded_occurrences"]["value"], 3)
        self.assertEqual(data["right"]["expanded_occurrences"]["value"], 3)

    def test_dag_profile_counts_shared_occurrences_without_expansion(self):
        term = expr([node("const", ["x"]), node("app", [], [0, 0]), node("app", [], [1, 1])])
        data = profile_terms(MemoryCorpus([declaration("a", term)]))["data"]
        self.assertEqual(data["reachable_dag_nodes_total"], 3)
        self.assertEqual(data["expanded_occurrences_total"]["value"], 7)
        self.assertTrue(data["expanded_occurrences_total"]["exact"])
        self.assertEqual(data["depth"]["maximum"], 3)
        self.assertEqual(data["constructors_reachable_dag"], {"app": 2, "const": 1})
        self.assertEqual(data["constructors_expanded_occurrences"]["app"]["value"], 3)
        self.assertEqual(data["constructors_expanded_occurrences"]["const"]["value"], 4)

    def test_exponential_counts_are_explicit_lower_bounds_when_capped(self):
        nodes = [node("const", ["x"])]
        nodes += [node("app", [], [i - 1, i - 1]) for i in range(1, 100)]
        corpus = MemoryCorpus([declaration("a", expr(nodes))])
        data = profile_terms(corpus, count_cap=1000)["data"]
        self.assertEqual(data["reachable_dag_nodes_total"], 100)
        self.assertEqual(data["expanded_occurrences_total"], {"value": 1000, "exact": False, "cap": 1000, "interpretation": "lower_bound"})
        self.assertFalse(data["constructors_expanded_occurrences"]["app"]["exact"])

    def test_internal_orphan_nodes_do_not_inflate_reachable_statistics(self):
        term = expr([node("const", ["used"]), node("const", ["unused"])], root=0)
        data = profile_terms(MemoryCorpus([declaration("a", term)]))["data"]
        self.assertEqual(data["serialized_nodes_total"], 2)
        self.assertEqual(data["reachable_dag_nodes_total"], 1)
        self.assertEqual(data["largest_expressions"][0]["unreachable_serialized_nodes"], 1)

    def test_profile_and_comparison_do_not_recurse_on_long_terms(self):
        nodes = [node("const", ["x"])]
        nodes += [node("mdata", [], [i - 1]) for i in range(1, 2500)]
        left, right = expr(nodes), expr(deepcopy(nodes))
        right["nodes"][0]["data"] = ["y"]
        corpus = MemoryCorpus([declaration("a", left), declaration("b", right)])
        self.assertEqual(profile_terms(corpus)["data"]["depth"]["maximum"], 2500)
        difference = compare_term_structure(corpus, "a", "b")["data"]["first_difference"]
        self.assertEqual(len(difference["child_path"]), 256)
        self.assertEqual(difference["path_length"], 2499)
        self.assertTrue(difference["path_truncated"])
        self.assertEqual(difference["left_node"], 0)

    def test_unavailable_no_value_and_node_limit_remain_separate(self):
        corpus = MemoryCorpus([declaration("available", identity()), declaration("opaque", None, status="no_value"),
                               declaration("capped", None, status="node_limit"), declaration("source", None, status="unavailable")])
        result = profile_terms(corpus)
        self.assertEqual(result["data"]["analyzed_expressions"], 1)
        self.assertEqual(result["coverage"]["expression_status_counts"],
                         {"available": 1, "no_value": 1, "node_limit": 1, "unavailable": 1})
        self.assertFalse(result["coverage"]["all_selected_expressions_available"])
        comparison = compare_term_structure(corpus, "available", "capped")["data"]
        self.assertIsNone(comparison["same_structure"])
        self.assertEqual(comparison["relation"], "unavailable")

    def test_empty_corpus_has_no_fabricated_size_summary(self):
        data = profile_terms(MemoryCorpus([]))["data"]
        self.assertEqual(data["analyzed_expressions"], 0)
        self.assertIsNone(data["reachable_dag_size"]["minimum"])
        self.assertIsNone(data["depth"]["mean"])
        self.assertEqual(data["largest_expressions"], [])

    def test_repeated_subterms_count_declarations_separately_from_occurrences(self):
        small = expr([node("const", ["x"]), node("app", [], [0, 0])])
        large = expr([node("const", ["x"]), node("app", [], [0, 0]), node("app", [], [1, 1])])
        result = find_repeated_subterms(MemoryCorpus([declaration("a", small), declaration("b", large)]), min_nodes=3)
        self.assertEqual(result["data"]["qualifying_patterns"], 1)
        pattern = result["data"]["patterns"][0]
        self.assertEqual(pattern["declaration_support"], 2)
        self.assertEqual(pattern["serialized_root_count"], 2)
        self.assertEqual(pattern["expanded_occurrences"]["value"], 3)
        self.assertEqual(pattern["expanded_nodes"]["value"], 3)
        self.assertEqual(len(pattern["examples"]), 2)

    def test_repeated_subterms_do_not_promote_one_declaration_to_multiple_support(self):
        term = expr([node("const", ["x"]), node("app", [], [0, 0]), node("app", [], [1, 1])])
        result = find_repeated_subterms(MemoryCorpus([declaration("a", term)]), min_nodes=3, min_declarations=2)
        self.assertEqual(result["data"]["patterns"], [])

    def test_loose_bvar_patterns_require_context_and_binders_discharge_it(self):
        corpus = MemoryCorpus([declaration("a", identity()), declaration("b", identity("z"))])
        result = find_repeated_subterms(corpus, min_nodes=1)
        patterns = result["data"]["patterns"]
        bvar = next(p for p in patterns if p["root"]["tag"] == "bvar")
        lam = next(p for p in patterns if p["root"]["tag"] == "lam")
        self.assertEqual(bvar["required_context_binders"], 1)
        self.assertIn("loose bound variables", bvar["context_note"])
        self.assertIn("interchangeable context", bvar["context_note"])
        self.assertEqual(lam["required_context_binders"], 0)

    def test_free_and_meta_variables_propagate_context_requirements(self):
        term = expr([node("fvar", ["local-x"]), node("mvar", ["goal-1"]), node("app", [], [0, 1])])
        corpus = MemoryCorpus([declaration("a", term), declaration("b", deepcopy(term))])
        profile = profile_terms(corpus)["data"]["largest_expressions"][0]
        self.assertEqual(profile["required_context_binders"], 0)
        self.assertTrue(profile["contains_fvar"])
        self.assertTrue(profile["contains_mvar"])
        self.assertTrue(profile["requires_expression_context"])
        pattern = find_repeated_subterms(corpus)["data"]["patterns"][0]
        self.assertTrue(pattern["contains_fvar"])
        self.assertTrue(pattern["contains_mvar"])
        self.assertTrue(pattern["requires_expression_context"])

    def test_type_field_and_top_output_limits(self):
        records = [declaration(f"d{i}", identity(str(i)), field="type") for i in range(8)]
        corpus = MemoryCorpus(records)
        self.assertEqual(profile_terms(corpus, field="value")["data"]["analyzed_expressions"], 0)
        profile = profile_terms(corpus, field="type", top_k=2)
        self.assertEqual(len(profile["data"]["largest_expressions"]), 2)
        patterns = find_repeated_subterms(corpus, field="type", min_nodes=1, limit=1, examples_per_pattern=2)
        self.assertTrue(patterns["data"]["output_truncated"])
        self.assertEqual(len(patterns["data"]["patterns"]), 1)
        self.assertTrue(patterns["data"]["patterns"][0]["examples_truncated"])
        self.assertEqual(len(patterns["data"]["patterns"][0]["examples"]), 2)

    def test_pattern_memory_cap_retains_known_patterns_and_reports_omissions(self):
        corpus = MemoryCorpus([declaration("a", identity()), declaration("b", identity("z")),
                               declaration("c", identity("w"))])
        first = find_repeated_subterms(corpus, min_nodes=1, max_unique_patterns=1)
        second = find_repeated_subterms(corpus, min_nodes=1, max_unique_patterns=1)
        self.assertEqual(first, second)
        self.assertEqual(first["data"]["indexed_patterns"], 1)
        self.assertFalse(first["coverage"]["pattern_index_complete"])
        self.assertGreater(first["coverage"]["omitted_new_pattern_observations"], 0)
        self.assertEqual(first["data"]["patterns"][0]["declaration_support"], 3)

    def test_output_does_not_alias_or_modify_corpus(self):
        corpus = MemoryCorpus([declaration("a", identity()), declaration("b", identity("y"))])
        before = deepcopy(corpus.records)
        result = find_repeated_subterms(corpus)
        result["provenance"]["fixture"] = "modified"
        profile_terms(corpus)
        compare_term_structure(corpus, "a", "b")
        self.assertEqual(corpus.records, before)
        self.assertNotEqual(corpus.metadata["fixture"], "modified")

    def test_invalid_options_and_dags_fail_explicitly(self):
        corpus = MemoryCorpus([declaration("a", identity())])
        for operation in [lambda: profile_terms(corpus, field=[]), lambda: profile_terms(corpus, top_k=0),
                          lambda: profile_terms(corpus, count_cap=True),
                          lambda: find_repeated_subterms(corpus, min_nodes=10, count_cap=5),
                          lambda: find_repeated_subterms(corpus, limit=0),
                          lambda: compare_term_structure(corpus, "a", "missing")]:
            with self.assertRaises(TermAnalysisError):
                operation()
        malformed = [
            {"nodes": [], "root": 0, "truncated": False},
            expr([node("app", [], [0, 0])]),
            expr([node("unknown")]),
            expr([node("bvar", ["-1"])]),
            expr([node("const", ["T"], extra="ignored?")]),
            {"nodes": [node("const", ["T"])], "root": True, "truncated": False},
        ]
        for term in malformed:
            with self.subTest(term=term), self.assertRaises(TermAnalysisError):
                profile_terms(MemoryCorpus([declaration("bad", term)]))


if __name__ == "__main__":
    unittest.main()
