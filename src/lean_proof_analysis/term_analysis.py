"""Structural analysis of exported Lean expression DAGs.

These tools analyze the encoded expression, without unfolding definitions,
running Lean, or inferring mathematical equivalence. Binder display names are
the only node field intentionally omitted from structural fingerprints.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import heapq
import json
import re
from typing import Any


DEFAULT_COUNT_CAP = 10**12
_ARITY = {
    "bvar": 0, "fvar": 0, "mvar": 0, "sort": 0, "const": 0,
    "app": 2, "lam": 2, "forallE": 2, "letE": 3,
    "lit": 0, "mdata": 1, "proj": 1,
}
_NORMALIZATION = {
    "ignored": ["binder_name"],
    "preserved": ["constructor", "ordered_children", "data", "bound_variable_indices",
                  "binder_info", "constant_names", "universe_encodings", "literal_values"],
    "definition_unfolding": False,
    "interpretation": "Identity of encoded structure, not definitional equality or theorem equivalence.",
}


class TermAnalysisError(ValueError):
    """Invalid analysis arguments or malformed expression records."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": deepcopy(self.details)}


def _integer(name: str, value: int, lower: int, upper: int | None = None) -> None:
    if type(value) is not int or value < lower or (upper is not None and value > upper):
        raise TermAnalysisError("invalid_argument", f"Invalid {name}", argument=name,
                                minimum=lower, maximum=upper)


def _options(field: str, count_cap: int) -> None:
    if not isinstance(field, str) or field not in {"type", "value"}:
        raise TermAnalysisError("invalid_argument", "field must be 'type' or 'value'")
    _integer("count_cap", count_cap, 1, 10**18)


def _count(value: int, exact: bool, cap: int) -> dict[str, Any]:
    return {"value": value, "exact": exact, "cap": cap,
            "interpretation": "exact" if exact else "lower_bound"}


def _add(a: int, a_exact: bool, b: int, b_exact: bool, cap: int) -> tuple[int, bool]:
    total = a + b
    return min(cap, total), a_exact and b_exact and total <= cap


def _availability(record: dict[str, Any], field: str) -> tuple[str, dict[str, Any] | None]:
    expression = record.get(field + "_expr")
    statuses = record.get("expression_status", {})
    if not isinstance(statuses, dict):
        raise TermAnalysisError("invalid_expression", "expression_status must be an object",
                                declaration_id=record.get("id"))
    status = statuses.get(field)
    if status is not None and not isinstance(status, str):
        raise TermAnalysisError("invalid_expression", "Expression status must be a string",
                                declaration_id=record.get("id"), field=field)
    if status is not None and status not in {"available", "node_limit", "no_value", "unavailable"}:
        raise TermAnalysisError("invalid_expression", "Unknown expression status",
                                declaration_id=record.get("id"), field=field)
    if expression is None:
        return status if status in {"node_limit", "no_value", "unavailable"} else "unavailable", None
    if not isinstance(expression, dict):
        raise TermAnalysisError("invalid_expression", "Expression must be a DAG object or null",
                                declaration_id=record.get("id"), field=field)
    if expression.get("truncated") is True:
        return "truncated_expression", None
    if status in {"node_limit", "no_value", "unavailable"}:
        raise TermAnalysisError("invalid_expression", "Expression presence contradicts its status",
                                declaration_id=record.get("id"), field=field)
    return "available", expression


@dataclass
class _Analysis:
    nodes: list[dict[str, Any]]
    root: int
    reachable: list[int]
    fingerprints: list[str]
    sizes: list[int]
    size_exact: list[bool]
    depths: list[int]
    context_binders: list[int]
    contains_fvar: list[bool]
    contains_mvar: list[bool]
    occurrences: list[int]
    occurrence_exact: list[bool]


def _analyze(expression: dict[str, Any], cap: int) -> _Analysis:
    if expression.get("truncated") is not False:
        raise TermAnalysisError("invalid_expression", "Complete DAGs must declare truncated=false")
    nodes, root = expression.get("nodes"), expression.get("root")
    if not isinstance(nodes, list) or not nodes or type(root) is not int or not 0 <= root < len(nodes):
        raise TermAnalysisError("invalid_expression", "Invalid expression nodes or root")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("tag"), str) or node["tag"] not in _ARITY:
            raise TermAnalysisError("invalid_expression", "Unknown expression constructor", node=index)
        if set(node) - {"tag", "data", "children", "binder_name"}:
            raise TermAnalysisError("invalid_expression", "Unsupported expression node fields", node=index)
        children, data = node.get("children"), node.get("data")
        if not isinstance(data, list) or any(not isinstance(item, str) for item in data):
            raise TermAnalysisError("invalid_expression", "Node data must be a list of strings", node=index)
        if (not isinstance(children, list) or len(children) != _ARITY[node["tag"]]
                or any(type(child) is not int or not 0 <= child < index for child in children)):
            raise TermAnalysisError("invalid_expression", "Children must match constructor arity and precede their parent",
                                    node=index)
        if "binder_name" in node and not isinstance(node["binder_name"], str):
            raise TermAnalysisError("invalid_expression", "binder_name must be a string", node=index)
        if node["tag"] == "bvar" and (len(data) != 1 or re.fullmatch(r"0|[1-9][0-9]*", data[0]) is None):
            raise TermAnalysisError("invalid_expression", "Bound variable index must be a nonnegative decimal", node=index)
    seen = set()
    stack = [root]
    while stack:
        index = stack.pop()
        if index not in seen:
            seen.add(index)
            stack.extend(nodes[index]["children"])
    reachable = sorted(seen)
    fingerprints = [""] * len(nodes)
    sizes, exact, depths, contexts = [0] * len(nodes), [True] * len(nodes), [0] * len(nodes), [0] * len(nodes)
    has_fvar, has_mvar = [False] * len(nodes), [False] * len(nodes)
    for index in reachable:
        node = nodes[index]
        children = node["children"]
        signature = [node["tag"], node["data"], [fingerprints[child] for child in children]]
        encoded = json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        fingerprints[index] = hashlib.sha256(encoded).hexdigest()
        size, is_exact = 1, True
        for child in children:
            size, is_exact = _add(size, is_exact, sizes[child], exact[child], cap)
        sizes[index], exact[index] = size, is_exact
        depths[index] = 1 + max((depths[child] for child in children), default=0)
        has_fvar[index] = node["tag"] == "fvar" or any(has_fvar[child] for child in children)
        has_mvar[index] = node["tag"] == "mvar" or any(has_mvar[child] for child in children)
        if node["tag"] == "bvar":
            contexts[index] = int(node["data"][0]) + 1
        elif node["tag"] in {"lam", "forallE"}:
            contexts[index] = max(contexts[children[0]], max(0, contexts[children[1]] - 1))
        elif node["tag"] == "letE":
            contexts[index] = max(contexts[children[0]], contexts[children[1]], max(0, contexts[children[2]] - 1))
        else:
            contexts[index] = max((contexts[child] for child in children), default=0)
    # Multiplicities are propagated over the DAG, never over its exponentially
    # expanded tree. Repeated child edges are intentionally counted twice.
    occurrences, occurrence_exact = [0] * len(nodes), [True] * len(nodes)
    occurrences[root] = 1
    for index in reversed(reachable):
        for child in nodes[index]["children"]:
            occurrences[child], occurrence_exact[child] = _add(
                occurrences[child], occurrence_exact[child], occurrences[index], occurrence_exact[index], cap)
    return _Analysis(nodes, root, reachable, fingerprints, sizes, exact, depths, contexts, has_fvar, has_mvar,
                     occurrences, occurrence_exact)


def _node_preview(node: dict[str, Any]) -> dict[str, Any]:
    # A string literal can be large; examples are explicitly previews while
    # fingerprints always include all of its stored bytes.
    return {"tag": node["tag"], "data": [item[:400] for item in node["data"]],
            "data_truncated": [len(item) > 400 for item in node["data"]],
            "data_characters": [len(item) for item in node["data"]],
            "child_count": len(node["children"])}


def _record_summary(record: dict[str, Any], analysis: _Analysis, cap: int) -> dict[str, Any]:
    return {"id": record["id"], "name": record.get("name", record["id"]), "kind": record.get("kind"),
            "module": record.get("module"), "source_url": record.get("source_url"),
            "evidence": record.get("evidence", "unknown"),
            "serialized_nodes": len(analysis.nodes), "reachable_dag_nodes": len(analysis.reachable),
            "unreachable_serialized_nodes": len(analysis.nodes) - len(analysis.reachable),
            "expanded_occurrences": _count(analysis.sizes[analysis.root], analysis.size_exact[analysis.root], cap),
            "depth": analysis.depths[analysis.root],
            "required_context_binders": analysis.context_binders[analysis.root],
            "contains_fvar": analysis.contains_fvar[analysis.root],
            "contains_mvar": analysis.contains_mvar[analysis.root],
            "requires_expression_context": bool(analysis.context_binders[analysis.root]
                                                  or analysis.contains_fvar[analysis.root]
                                                  or analysis.contains_mvar[analysis.root]),
            "fingerprint": analysis.fingerprints[analysis.root]}


def _coverage(statuses: Counter, evidence: Counter) -> dict[str, Any]:
    return {"scope": "available-exported-expressions", "declarations_seen": sum(statuses.values()),
            "expression_status_counts": dict(sorted(statuses.items())),
            "evidence_counts": dict(sorted(evidence.items())),
            "all_selected_expressions_available": all(key == "available" for key in statuses),
            "proof_correctness_assessed": False,
            "notes": ["Missing, capped and absent values are counted rather than treated as empty proofs.",
                      "Structural size is not mathematical difficulty or proof quality.",
                      "Subterms with loose bound variables, free variables or metavariables require their expression context.",
                      "The absence of those variables does not establish independence from constants or universe parameters."]}


def _result(corpus: Any, operation: str, algorithm: str, options: dict[str, Any],
            coverage: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "lpaf-analysis-v0.1", "operation": operation, "algorithm": algorithm,
            "options": options, "provenance": deepcopy(corpus.metadata),
            "coverage": coverage, "data": data}


def profile_terms(corpus: Any, *, field: str = "value", top_k: int = 20,
                  count_cap: int = DEFAULT_COUNT_CAP) -> dict[str, Any]:
    """Measure exported expression structure, distinguishing DAG nodes and tree occurrences.

    Counts saturate at count_cap with exact=false. The size/depth summaries use
    reachable serialized nodes, excluding any orphaned serialized records.
    """
    _options(field, count_cap)
    _integer("top_k", top_k, 1, 1000)
    statuses, evidence, constructors = Counter(), Counter(), Counter()
    expanded_constructors: dict[str, tuple[int, bool]] = {}
    size_sum = depth_sum = serialized_sum = 0
    minimum_size = maximum_size = minimum_depth = maximum_depth = None
    expanded_total, expanded_exact = 0, True
    largest: list[tuple[int, str, dict[str, Any]]] = []
    for record in corpus.iter_declarations(include_expressions=True):
        status, expression = _availability(record, field)
        statuses[status] += 1
        evidence[str(record.get("evidence", "unknown"))] += 1
        if expression is None:
            continue
        analysis = _analyze(expression, count_cap)
        summary = _record_summary(record, analysis, count_cap)
        size, depth = len(analysis.reachable), analysis.depths[analysis.root]
        size_sum += size
        serialized_sum += len(analysis.nodes)
        depth_sum += depth
        minimum_size = size if minimum_size is None else min(minimum_size, size)
        maximum_size = size if maximum_size is None else max(maximum_size, size)
        minimum_depth = depth if minimum_depth is None else min(minimum_depth, depth)
        maximum_depth = depth if maximum_depth is None else max(maximum_depth, depth)
        expanded_total, expanded_exact = _add(expanded_total, expanded_exact, analysis.sizes[analysis.root],
                                              analysis.size_exact[analysis.root], count_cap)
        for index in analysis.reachable:
            tag = analysis.nodes[index]["tag"]
            constructors[tag] += 1
            old_value, old_exact = expanded_constructors.get(tag, (0, True))
            expanded_constructors[tag] = _add(old_value, old_exact, analysis.occurrences[index],
                                               analysis.occurrence_exact[index], count_cap)
        rank = (size, record["id"], summary)
        if len(largest) < top_k:
            heapq.heappush(largest, rank)
        elif rank[:2] > largest[0][:2]:
            heapq.heapreplace(largest, rank)
    available = statuses["available"]
    data = {
        "analyzed_expressions": available, "serialized_nodes_total": serialized_sum,
        "reachable_dag_nodes_total": size_sum,
        "expanded_occurrences_total": _count(expanded_total, expanded_exact, count_cap),
        "reachable_dag_size": {"minimum": minimum_size, "maximum": maximum_size,
                               "mean": size_sum / available if available else None},
        "depth": {"minimum": minimum_depth, "maximum": maximum_depth,
                  "mean": depth_sum / available if available else None},
        "constructors_reachable_dag": dict(sorted(constructors.items())),
        "constructors_expanded_occurrences": {tag: _count(value, exact, count_cap)
                                                for tag, (value, exact) in sorted(expanded_constructors.items())},
        "largest_expressions": [item[2] for item in sorted(largest, key=lambda item: item[:2], reverse=True)],
        "largest_ranking": "reachable DAG node count descending, then declaration ID descending",
        "normalization": deepcopy(_NORMALIZATION),
    }
    return _result(corpus, "profile_terms", "postorder-dag-dynamic-programming-v1",
                   {"field": field, "top_k": top_k, "count_cap": count_cap},
                   _coverage(statuses, evidence), data)


def find_repeated_subterms(corpus: Any, *, field: str = "value", min_nodes: int = 3,
                          min_declarations: int = 2, limit: int = 20,
                          max_unique_patterns: int = 100000, examples_per_pattern: int = 5,
                          count_cap: int = DEFAULT_COUNT_CAP) -> dict[str, Any]:
    """Find identical encoded subtrees occurring in multiple declarations.

    A declaration contributes once to support even when its term repeats the
    subtree many times. Occurrence counts include overlapping nested occurrences.
    Fingerprint-index truncation is explicit; counts for retained patterns still
    include later declarations. This is not a minimum description-length score.
    """
    _options(field, count_cap)
    _integer("min_nodes", min_nodes, 1, count_cap)
    _integer("min_declarations", min_declarations, 1)
    _integer("limit", limit, 1, 1000)
    _integer("max_unique_patterns", max_unique_patterns, 1, 1000000)
    _integer("examples_per_pattern", examples_per_pattern, 1, 100)
    statuses, evidence = Counter(), Counter()
    patterns: dict[str, dict[str, Any]] = {}
    skipped_observations = 0
    for record in corpus.iter_declarations(include_expressions=True):
        status, expression = _availability(record, field)
        statuses[status] += 1
        evidence[str(record.get("evidence", "unknown"))] += 1
        if expression is None:
            continue
        analysis = _analyze(expression, count_cap)
        local: dict[str, dict[str, Any]] = {}
        for index in analysis.reachable:
            if analysis.sizes[index] < min_nodes:
                continue
            fingerprint = analysis.fingerprints[index]
            item = local.setdefault(fingerprint, {"index": index, "dag_roots": 0, "occurrences": 0, "exact": True})
            item["dag_roots"] += 1
            item["occurrences"], item["exact"] = _add(item["occurrences"], item["exact"],
                                                        analysis.occurrences[index], analysis.occurrence_exact[index], count_cap)
        # Sorted signatures make admission to the capped index reproducible for
        # a given declaration order, independent of dictionary traversal order.
        for fingerprint, item in sorted(local.items()):
            if fingerprint not in patterns:
                if len(patterns) >= max_unique_patterns:
                    skipped_observations += 1
                    continue
                index = item["index"]
                patterns[fingerprint] = {
                    "fingerprint": fingerprint, "root": _node_preview(analysis.nodes[index]),
                    "expanded_nodes": _count(analysis.sizes[index], analysis.size_exact[index], count_cap),
                    "required_context_binders": analysis.context_binders[index],
                    "contains_fvar": analysis.contains_fvar[index],
                    "contains_mvar": analysis.contains_mvar[index],
                    "requires_expression_context": bool(analysis.context_binders[index]
                                                          or analysis.contains_fvar[index]
                                                          or analysis.contains_mvar[index]),
                    "declaration_support": 0, "serialized_root_count": 0,
                    "occurrences": 0, "occurrences_exact": True, "examples": [],
                }
            pattern = patterns[fingerprint]
            pattern["declaration_support"] += 1
            pattern["serialized_root_count"] += item["dag_roots"]
            pattern["occurrences"], pattern["occurrences_exact"] = _add(
                pattern["occurrences"], pattern["occurrences_exact"], item["occurrences"], item["exact"], count_cap)
            if len(pattern["examples"]) < examples_per_pattern:
                pattern["examples"].append({"declaration_id": record["id"], "name": record.get("name", record["id"]),
                                             "field": field, "node_index": item["index"],
                                             "source_url": record.get("source_url"),
                                             "evidence": record.get("evidence", "unknown")})
    qualifying = [p for p in patterns.values() if p["declaration_support"] >= min_declarations]
    qualifying.sort(key=lambda p: (-p["declaration_support"], -p["expanded_nodes"]["value"], p["fingerprint"]))
    output = []
    for pattern in qualifying[:limit]:
        item = {key: deepcopy(value) for key, value in pattern.items() if key not in {"occurrences", "occurrences_exact"}}
        item["expanded_occurrences"] = _count(pattern["occurrences"], pattern["occurrences_exact"], count_cap)
        item["examples_truncated"] = pattern["declaration_support"] > len(pattern["examples"])
        item["context_note"] = ("Contains loose bound variables, free variables or metavariables; identical encoding does not establish interchangeable context."
                                if pattern["requires_expression_context"] else
                                "No loose expression variables in this encoded subtree; constants and universe parameters still require an environment.")
        output.append(item)
    coverage = _coverage(statuses, evidence)
    coverage.update(pattern_index_complete=skipped_observations == 0,
                    omitted_new_pattern_observations=skipped_observations)
    return _result(corpus, "find_repeated_subterms", "ordered-structural-sha256-v1",
                   {"field": field, "min_nodes": min_nodes, "min_declarations": min_declarations,
                    "limit": limit, "max_unique_patterns": max_unique_patterns,
                    "examples_per_pattern": examples_per_pattern, "count_cap": count_cap},
                   coverage,
                   {"patterns": output, "qualifying_patterns": len(qualifying),
                    "indexed_patterns": len(patterns), "output_truncated": len(qualifying) > limit,
                    "ranking": "declaration support descending, capped expanded size descending, fingerprint ascending",
                    "normalization": deepcopy(_NORMALIZATION),
                    "counting": "Support counts distinct declarations; expanded occurrences can overlap and are not additive compression savings.",
                    "index_limit_note": "When capped, retained patterns reflect corpus iteration order; omitted-pattern counts are observations, not distinct omitted patterns."})


def compare_term_structure(corpus: Any, left: str, right: str, *, field: str = "value",
                           count_cap: int = DEFAULT_COUNT_CAP, max_path: int = 256) -> dict[str, Any]:
    """Compare two complete encoded structures and locate their first difference.

    Exact declaration IDs are required. This comparison ignores binder labels,
    but preserves binding indices and every serialized semantic payload.
    """
    _options(field, count_cap)
    _integer("max_path", max_path, 0, 10000)
    if not isinstance(left, str) or not left or not isinstance(right, str) or not right:
        raise TermAnalysisError("invalid_argument", "left and right must be nonempty declaration IDs")
    a = corpus.get_declaration(left, include_expressions=True)
    b = corpus.get_declaration(right, include_expressions=True)
    if a is None or b is None:
        raise TermAnalysisError("declaration_not_found", "A declaration ID is absent from the corpus",
                                left_found=a is not None, right_found=b is not None)
    status_a, expr_a = _availability(a, field)
    status_b, expr_b = _availability(b, field)
    statuses, evidence = Counter((status_a, status_b)), Counter(str(d.get("evidence", "unknown")) for d in (a, b))
    data: dict[str, Any] = {"left": {"id": a["id"], "status": status_a},
                            "right": {"id": b["id"], "status": status_b},
                            "same_structure": None, "relation": "unavailable", "first_difference": None,
                            "normalization": deepcopy(_NORMALIZATION)}
    if expr_a is not None and expr_b is not None:
        aa, bb = _analyze(expr_a, count_cap), _analyze(expr_b, count_cap)
        data["left"].update(_record_summary(a, aa, count_cap))
        data["right"].update(_record_summary(b, bb, count_cap))
        equal = aa.fingerprints[aa.root] == bb.fingerprints[bb.root]
        data.update(same_structure=equal, relation="same_encoded_structure" if equal else "different_encoded_structure")
        if not equal:
            i, j, path = aa.root, bb.root, []
            path_length = 0
            while True:
                na, nb = aa.nodes[i], bb.nodes[j]
                if na["tag"] != nb["tag"] or na["data"] != nb["data"] or len(na["children"]) != len(nb["children"]):
                    data["first_difference"] = {"child_path": path, "path_length": path_length,
                                                "path_truncated": path_length > len(path),
                                                "left_node": i, "right_node": j,
                                                "left": _node_preview(na), "right": _node_preview(nb)}
                    break
                for position, (ca, cb) in enumerate(zip(na["children"], nb["children"])):
                    if aa.fingerprints[ca] != bb.fingerprints[cb]:
                        i, j = ca, cb
                        path_length += 1
                        if len(path) < max_path:
                            path.append(position)
                        break
                else:
                    # Structural hashes are evidence of encoded identity, not
                    # a formal collision-free certificate. Never invent a diff.
                    data["first_difference"] = {"status": "fingerprint_disagreement_without_local_difference"}
                    break
    return _result(corpus, "compare_term_structure", "ordered-structural-sha256-v1",
                   {"field": field, "count_cap": count_cap, "max_path": max_path}, _coverage(statuses, evidence), data)
