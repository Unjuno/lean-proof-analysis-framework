"""Tests against known graph structure and an independent dominance oracle."""
from copy import deepcopy
import random
import unittest

from lean_proof_analysis.graph_analysis import (
    analyze_dependencies, dependency_bottlenecks, dependency_overlap,
)


class Corpus:
    def __init__(self, names, edges=(), *, evidence="lean_elaborated", modules=None):
        self.metadata = {"schema": "lpaf-corpus-v0.1", "fixture": True}
        self.declarations = [{"id": name, "name": name, "kind": "theorem",
                              "module": (modules or {}).get(name), "evidence": evidence,
                              "source_url": None} for name in names]
        self.references = []
        for edge in edges:
            source, target = edge[:2]
            role = edge[2] if len(edge) >= 3 else "value"
            level = edge[3] if len(edge) >= 4 else evidence
            self.references.append({"from": source, "to": target, "role": role, "evidence": level})

    def iter_declarations(self, include_expressions=False):
        yield from self.declarations

    def iter_references(self, role="all"):
        yield from (edge for edge in self.references if role == "all" or edge["role"] == role)


def layer(result, evidence="lean_elaborated"):
    return result["data"]["layers"][evidence]


class GraphAnalysisTest(unittest.TestCase):
    def test_chain_has_expected_condensation_depth_and_degrees(self):
        corpus = Corpus(["root", "middle", "leaf"], [("root", "middle"), ("middle", "leaf")])
        report = analyze_dependencies(corpus, roots=["root"])
        data = layer(report)
        self.assertEqual(data["nodes"], 3)
        self.assertEqual(data["internal_edges"], 2)
        self.assertEqual(data["strong_components"]["count"], 3)
        self.assertEqual(data["weak_components"]["count"], 1)
        self.assertEqual(data["condensation"]["depth_to_internal_sink"]["maximum"], 2)
        self.assertEqual(data["degree"]["incoming_internal"]["histogram"],
                         [{"value": 0, "count": 1}, {"value": 1, "count": 2}])
        self.assertEqual(data["roots"][0]["reachable_internal_nodes"], 3)
        self.assertEqual(report["coverage"]["edge_direction"], "consumer-to-reference")
        self.assertTrue(report["not_proof_check"])

    def test_cycle_condensation_is_not_a_proof_flaw_claim(self):
        corpus = Corpus(["a", "b", "c", "d", "isolated"],
                        [("a", "b"), ("b", "a"), ("b", "c"), ("c", "d"), ("d", "d")])
        data = layer(analyze_dependencies(corpus))
        self.assertEqual(data["strong_components"]["count"], 4)
        self.assertEqual(data["cyclic_components"]["count"], 2)
        self.assertEqual(data["weak_components"]["count"], 2)
        self.assertEqual(data["self_loops"], 1)
        self.assertEqual(data["condensation"]["depth_to_internal_sink"]["maximum"], 2)
        self.assertNotIn("proof_flaws", data)

    def test_outside_targets_are_boundary_not_known_internal_leaves(self):
        corpus = Corpus(["a", "b"], [("a", "b"), ("b", "external"), ("a", "external")])
        data = layer(analyze_dependencies(corpus, roots=["a"]))
        self.assertEqual(data["nodes"], 2)
        self.assertEqual(data["outside_targets"], 1)
        self.assertEqual(data["outside_edges"], 2)
        self.assertEqual(data["condensation"]["depth_to_internal_sink"]["maximum"], 1)
        self.assertEqual(data["roots"][0]["outside_targets"], 1)
        self.assertEqual(data["top_referenced"][0]["id"], "external")
        self.assertFalse(data["top_referenced"][0]["in_corpus"])

    def test_duplicate_and_cross_role_edges_do_not_inflate_degree(self):
        corpus = Corpus(["a", "b"], [("a", "b", "type"), ("a", "b", "value"), ("a", "b", "value")])
        data = layer(analyze_dependencies(corpus))
        self.assertEqual(data["reference_records"], 3)
        self.assertEqual(data["unique_edges"], 1)
        self.assertEqual(data["reference_records_by_role"], {"type": 1, "value": 2})
        self.assertEqual(data["top_referenced"][0]["distinct_consumers"], 1)
        self.assertEqual(layer(analyze_dependencies(corpus, role="type"))["reference_records"], 1)

    def test_evidence_layers_are_never_silently_merged(self):
        corpus = Corpus(["a", "b", "c"], [("a", "b", "value", "lean_elaborated"),
                                            ("b", "c", "value", "lexical_candidate")])
        report = analyze_dependencies(corpus, roots=["a"])
        self.assertEqual(set(report["data"]["layers"]), {"lean_elaborated", "lexical_candidate"})
        self.assertFalse(report["coverage"]["layers_combined"])
        self.assertEqual(layer(report)["roots"][0]["reachable_internal_nodes"], 2)
        self.assertEqual(layer(report, "lexical_candidate")["roots"][0]["reachable_internal_nodes"], 1)

    def test_component_and_module_summaries_report_truncation(self):
        corpus = Corpus(["a", "b", "c", "d"], [("a", "b"), ("c", "d")],
                        modules={"a": "M1", "b": "M2", "c": "M3"})
        data = layer(analyze_dependencies(corpus, top_k=1))
        self.assertTrue(data["weak_components"]["components_truncated"])
        self.assertTrue(data["weak_components"]["largest"][0]["members_truncated"])
        self.assertEqual(data["module_coupling"]["pairs"], [{"from": "M1", "to": "M2", "edges": 1}])
        self.assertEqual(data["module_coupling"]["edges_with_unknown_module"], 1)

    def test_deep_chain_is_not_limited_by_python_recursion(self):
        names = [f"n{i:05d}" for i in range(2500)]
        corpus = Corpus(names, zip(names[:-1], names[1:]))
        data = layer(analyze_dependencies(corpus, top_k=3))
        self.assertEqual(data["condensation"]["depth_to_internal_sink"]["maximum"], 2499)
        self.assertEqual(data["weak_components"]["count"], 1)
        dom = layer(dependency_bottlenecks(corpus, names[0], top_k=1))
        self.assertEqual(dom["status"], "complete")
        self.assertEqual(dom["top_bottlenecks"][0]["id"], names[1])
        self.assertEqual(dom["top_bottlenecks"][0]["dominated_nodes"], 2499)

    def test_dense_graph_is_single_cyclic_component(self):
        names = [f"n{i:02d}" for i in range(35)]
        corpus = Corpus(names, ((a, b) for a in names for b in names if a != b))
        data = layer(analyze_dependencies(corpus, top_k=2))
        self.assertEqual(data["internal_edges"], 35 * 34)
        self.assertEqual(data["strong_components"]["count"], 1)
        self.assertEqual(data["cyclic_components"]["count"], 1)
        self.assertEqual(data["condensation"]["depth_to_internal_sink"]["maximum"], 0)

    def test_overlap_includes_outside_targets_and_defines_empty_union(self):
        corpus = Corpus(["a", "b", "leaf"], [("a", "external"), ("b", "external"), ("a", "leaf")])
        data = layer(dependency_overlap(corpus, "a", "b"))
        self.assertEqual(data["counts"], {"shared": 1, "left_only": 1, "right_only": 0})
        self.assertEqual(data["jaccard"], .5)
        self.assertFalse(data["shared"][0]["in_corpus"])
        empty = layer(dependency_overlap(corpus, "leaf", "leaf"))
        self.assertTrue(empty["empty_union"])
        self.assertIsNone(empty["jaccard"])

    def test_diamond_has_no_false_branch_bottleneck(self):
        corpus = Corpus(["root", "left", "right", "join", "tail"],
                        [("root", "left"), ("root", "right"), ("left", "join"),
                         ("right", "join"), ("join", "tail")])
        data = layer(dependency_bottlenecks(corpus, "root"))
        rankings = {row["id"]: row for row in data["top_bottlenecks"]}
        self.assertEqual(rankings["join"]["immediate_dominator"], "root")
        self.assertEqual(rankings["tail"]["immediate_dominator"], "join")
        self.assertEqual(rankings["join"]["dominated_nodes"], 2)
        self.assertEqual(rankings["left"]["dominated_nodes"], 1)
        self.assertEqual(rankings["right"]["dominated_nodes"], 1)

    def test_dominators_agree_with_independent_vertex_removal_oracle(self):
        rng = random.Random(29)
        names = ["root", "a", "b", "c", "d", "e"]
        for case in range(40):
            edges = [(a, b) for a in names for b in names if a != b and rng.random() < .3]
            corpus = Corpus(names, edges)
            data = layer(dependency_bottlenecks(corpus, "root"))
            self.assertEqual(data["status"], "complete")
            adjacency = {a: {b for source, b in edges if source == a} for a in names}

            def reachable_without(removed):
                reached, pending = {"root"}, ["root"]
                while pending:
                    for nxt in adjacency[pending.pop()]:
                        if nxt != removed and nxt not in reached:
                            reached.add(nxt)
                            pending.append(nxt)
                return reached

            baseline = reachable_without(None)
            expected = {node: len(baseline - reachable_without(node)) for node in baseline if node != "root"}
            actual = {row["id"]: row["dominated_nodes"] for row in data["top_bottlenecks"]}
            with self.subTest(case=case):
                self.assertEqual(actual, expected)

    def test_dominator_budget_never_returns_partial_claims(self):
        corpus = Corpus(["root", "a", "b"], [("root", "a"), ("a", "b")])
        data = layer(dependency_bottlenecks(corpus, "root", max_work=1))
        self.assertEqual(data["status"], "work_limit")
        self.assertFalse(data["computation"]["complete"])
        self.assertEqual(data["top_bottlenecks"], [])

    def test_empty_and_isolated_corpora(self):
        empty = analyze_dependencies(Corpus([]))
        self.assertEqual(empty["data"]["declarations"], 0)
        self.assertEqual(layer(empty, "unspecified")["strong_components"]["count"], 0)
        singleton = Corpus(["alone"])
        data = layer(dependency_bottlenecks(singleton, "alone"))
        self.assertEqual(data["reachable_internal_nodes"], 1)
        self.assertEqual(data["top_bottlenecks"], [])

    def test_outputs_are_deterministic_and_input_is_unmodified(self):
        corpus = Corpus(["d", "c", "b", "a"], [("a", "c"), ("a", "b"), ("b", "d"), ("c", "d")])
        before = deepcopy((corpus.declarations, corpus.references, corpus.metadata))
        first = analyze_dependencies(corpus)
        corpus.declarations.reverse()
        corpus.references.reverse()
        self.assertEqual(first, analyze_dependencies(corpus))
        first["provenance"]["fixture"] = False
        self.assertTrue(corpus.metadata["fixture"])
        corpus.declarations.reverse()
        corpus.references.reverse()
        self.assertEqual(before, (corpus.declarations, corpus.references, corpus.metadata))

    def test_invalid_bounds_identity_and_reference_data(self):
        corpus = Corpus(["a", "b"])
        for operation in [lambda: analyze_dependencies(corpus, role="body"),
                          lambda: analyze_dependencies(corpus, top_k=0),
                          lambda: analyze_dependencies(corpus, roots=["unknown"]),
                          lambda: analyze_dependencies(corpus, roots=["a"] * 17),
                          lambda: dependency_bottlenecks(corpus, "a", max_work=True),
                          lambda: dependency_overlap(corpus, "a", "b", limit=0)]:
            with self.assertRaises(ValueError):
                operation()
        corpus.references.append({"from": "missing", "to": "a", "role": "value", "evidence": "lean_elaborated"})
        with self.assertRaises(ValueError):
            analyze_dependencies(corpus)


if __name__ == "__main__":
    unittest.main()
