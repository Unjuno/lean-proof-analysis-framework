"""Scientific analysis of recorded proof-reference graphs.

Edges point from a declaration to a referenced declaration. Evidence layers stay
separate. Graph statistics and graph dominators are not mathematical importance,
proof difficulty, necessary premises, or correctness judgments.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from copy import deepcopy
from statistics import median
from typing import Any, Iterable

SCHEMA = "lpaf-analysis-v0.1"
EVIDENCE = {"lean_elaborated", "lexical_candidate"}
MAX_ROOTS = 16


def _integer(name: str, value: int, low: int = 1, high: int | None = None) -> None:
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f"{name} must be an integer in [{low}, {high if high is not None else 'unbounded'}]")


def _role(role: str) -> None:
    if not isinstance(role, str) or role not in {"all", "type", "value"}:
        raise ValueError("role must be all, type, or value")


class _Graph:
    def __init__(self, corpus: Any, role: str):
        _role(role)
        self.metadata = deepcopy(corpus.metadata)
        self.records = {}
        self.names = defaultdict(list)
        for record in corpus.iter_declarations(include_expressions=False):
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError("Declarations require nonempty string IDs")
            ident = record["id"]
            if ident in self.records:
                raise ValueError(f"Duplicate declaration ID: {ident}")
            name = record.get("name", ident)
            if not isinstance(name, str):
                raise ValueError("Declaration names must be strings")
            self.records[ident] = record
            self.names[name].append(ident)
        self.ids = sorted(self.records)
        self.layers = defaultdict(set)
        self.records_by_evidence = Counter()
        self.records_by_role = defaultdict(Counter)
        for edge in corpus.iter_references(role=role):
            if not isinstance(edge, dict):
                raise ValueError("References must be objects")
            source, target = edge.get("from"), edge.get("to")
            edge_role, evidence = edge.get("role"), edge.get("evidence")
            if not isinstance(source, str) or not isinstance(target, str) or not target:
                raise ValueError("Reference endpoints must be nonempty strings")
            if source not in self.records:
                raise ValueError(f"Reference source is outside the declaration inventory: {source}")
            if not isinstance(edge_role, str) or edge_role not in {"type", "value"}:
                raise ValueError("Reference role must be type or value")
            if not isinstance(evidence, str) or evidence not in EVIDENCE:
                raise ValueError("Reference evidence must be lean_elaborated or lexical_candidate")
            if role != "all" and edge_role != role:
                continue
            self.records_by_evidence[evidence] += 1
            self.records_by_role[evidence][edge_role] += 1
            self.layers[evidence].add((source, target))
        # Preserve recorded evidence contexts even when that layer has no edges.
        declared_evidence = {r["evidence"] for r in self.records.values()
                             if isinstance(r.get("evidence"), str) and r["evidence"] in EVIDENCE}
        for evidence in sorted(declared_evidence):
            self.layers.setdefault(evidence, set())
        if not self.layers:
            self.layers["unspecified"] = set()

    def resolve(self, selector: str) -> str:
        if not isinstance(selector, str) or not selector:
            raise ValueError("Declaration selector must be a nonempty string")
        if selector in self.records:
            return selector
        matches = self.names.get(selector, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous declaration name; use an exact ID: {selector}")
        raise ValueError(f"Declaration not found in corpus: {selector}")

    def brief(self, ident: str) -> dict[str, Any]:
        record = self.records.get(ident)
        if record is None:
            return {"id": ident, "name": ident, "kind": None, "module": None,
                    "source_url": None, "in_corpus": False}
        return {"id": ident, "name": record.get("name", ident), "kind": record.get("kind"),
                "module": record.get("module"), "source_url": record.get("source_url"),
                "in_corpus": True}

    def envelope(self, operation: str, algorithm: str, options: dict, data: dict) -> dict:
        return {"schema": SCHEMA, "operation": operation, "algorithm": algorithm,
                "options": options, "provenance": deepcopy(self.metadata),
                "not_proof_check": True,
                "coverage": {
                    "scope": "recorded-corpus", "edge_direction": "consumer-to-reference",
                    "node_inventory": "all-recorded-declarations",
                    "evidence_layers": sorted(self.layers), "layers_combined": False,
                    "outside_target_adjacency_known": False,
                    "notes": [
                        "Metrics use recorded references; unrecorded declarations and references are not inferred.",
                        "Structural statistics and graph dominators do not establish mathematical necessity or correctness.",
                        "Candidate references can be missing or spurious; elaborated references describe stored expressions only.",
                    ],
                }, "data": data}


def _adjacency(ids: list[str], edges: set[tuple[str, str]]):
    out = {ident: set() for ident in ids}
    incoming = {ident: set() for ident in ids}
    outside = []
    for source, target in edges:
        if target in out:
            out[source].add(target)
            incoming[target].add(source)
        else:
            outside.append((source, target))
    return ({i: tuple(sorted(out[i])) for i in ids},
            {i: tuple(sorted(incoming[i])) for i in ids}, sorted(outside))


def _finish_order(ids: Iterable[str], adjacency: dict[str, tuple[str, ...]]) -> list[str]:
    """Iterative DFS postorder, including every requested start component."""
    seen = set()
    order = []
    for start in ids:
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(adjacency[start]))]
        while stack:
            node, neighbors = stack[-1]
            nxt = next(neighbors, None)
            if nxt is None:
                order.append(node)
                stack.pop()
            elif nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, iter(adjacency[nxt])))
    return order


def _strong_components(ids: list[str], out: dict, incoming: dict):
    assigned = set()
    components = []
    for start in reversed(_finish_order(ids, out)):
        if start in assigned:
            continue
        assigned.add(start)
        stack = [start]
        members = []
        while stack:
            node = stack.pop()
            members.append(node)
            for nxt in incoming[node]:
                if nxt not in assigned:
                    assigned.add(nxt)
                    stack.append(nxt)
        components.append(sorted(members))
    components.sort(key=lambda group: group[0])
    component_of = {node: index for index, group in enumerate(components) for node in group}
    return components, component_of


def _weak_components(ids: list[str], out: dict, incoming: dict):
    seen = set()
    components = []
    for start in ids:
        if start in seen:
            continue
        seen.add(start)
        queue = deque([start])
        members = []
        while queue:
            node = queue.popleft()
            members.append(node)
            for nxt in (*out[node], *incoming[node]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(sorted(members))
    return components


def _distribution(values: Iterable[int]) -> dict:
    values = list(values)
    if not values:
        return {"count": 0, "minimum": None, "median": None, "maximum": None, "mean": None,
                "histogram": []}
    histogram = Counter(values)
    return {"count": len(values), "minimum": min(values), "median": median(values),
            "maximum": max(values), "mean": sum(values) / len(values),
            "histogram": [{"value": value, "count": histogram[value]} for value in sorted(histogram)]}


def _component_summary(groups: list[list[str]], top_k: int) -> dict:
    ordered = sorted(groups, key=lambda group: (-len(group), group[0]))
    return {"count": len(groups), "sizes": _distribution(len(group) for group in groups),
            "largest": [{"id": group[0], "size": len(group), "members": group[:top_k],
                         "members_truncated": len(group) > top_k} for group in ordered[:top_k]],
            "components_truncated": len(ordered) > top_k}


def _condensation_depth(components: list[list[str]], component_of: dict, out: dict):
    successors = {i: set() for i in range(len(components))}
    predecessors = {i: set() for i in range(len(components))}
    for source in out:
        a = component_of[source]
        for target in out[source]:
            b = component_of[target]
            if a != b:
                successors[a].add(b)
                predecessors[b].add(a)
    # Edges go consumer -> dependency. A sink component has depth zero;
    # a consumer's depth is one plus its deepest observed dependency component.
    remaining = {i: len(successors[i]) for i in successors}
    queue = deque(sorted(i for i in remaining if remaining[i] == 0))
    depths = {i: 0 for i in remaining}
    while queue:
        component = queue.popleft()
        for parent in sorted(predecessors[component]):
            depths[parent] = max(depths[parent], depths[component] + 1)
            remaining[parent] -= 1
            if remaining[parent] == 0:
                queue.append(parent)
    return depths, sum(map(len, successors.values()))


def _reachable(root: str, out: dict) -> set[str]:
    seen = {root}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for nxt in out[node]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def analyze_dependencies(corpus: Any, *, role: str = "all", roots: Iterable[str] = (),
                         top_k: int = 20) -> dict:
    """Analyze each evidence layer without recursive DFS or all-pairs reachability.

    Condensation depth counts component transitions to an observed internal sink;
    outside targets remain boundary records and are not treated as known leaves.
    Output component samples are bounded by top_k. Histograms retain exact counts.
    """
    _integer("top_k", top_k, high=1000)
    graph = _Graph(corpus, role)
    if isinstance(roots, str):
        roots = (roots,)
    requested = list(roots)
    if len(requested) > MAX_ROOTS:
        raise ValueError(f"At most {MAX_ROOTS} roots may be analyzed in one call")
    root_ids = sorted({graph.resolve(root) for root in requested})
    layers = {}
    for evidence, edges in sorted(graph.layers.items()):
        out, incoming, outside = _adjacency(graph.ids, edges)
        strong, component_of = _strong_components(graph.ids, out, incoming)
        weak = _weak_components(graph.ids, out, incoming)
        cyclic = [group for group in strong if len(group) > 1 or group[0] in out[group[0]]]
        depths, condensation_edges = _condensation_depth(strong, component_of, out)
        all_incoming = Counter(target for _, target in edges)
        external_outgoing = Counter(source for source, _ in outside)
        coupling = Counter()
        coupling_unknown = 0
        for source, target in edges:
            sm = graph.records[source].get("module")
            tm = graph.records.get(target, {}).get("module")
            if not isinstance(sm, str) or not sm or not isinstance(tm, str) or not tm:
                coupling_unknown += 1
            else:
                coupling[(sm, tm)] += 1
        root_summaries = []
        outside_by_source = defaultdict(set)
        for source, target in outside:
            outside_by_source[source].add(target)
        for root in root_ids:
            reachable = _reachable(root, out)
            boundary = {target for node in reachable for target in outside_by_source[node]}
            root_summaries.append({"root": graph.brief(root), "reachable_internal_nodes": len(reachable),
                                   "outside_targets": len(boundary),
                                   "outside_target_examples": sorted(boundary)[:top_k],
                                   "outside_examples_truncated": len(boundary) > top_k})
        most_referenced = sorted(all_incoming, key=lambda i: (-all_incoming[i], i))
        depth_order = sorted(depths, key=lambda i: (-depths[i], strong[i][0]))
        module_order = sorted(coupling, key=lambda pair: (-coupling[pair], pair))
        layers[evidence] = {
            "evidence": evidence, "nodes": len(graph.ids),
            "reference_records": graph.records_by_evidence[evidence],
            "reference_records_by_role": dict(sorted(graph.records_by_role[evidence].items())),
            "unique_edges": len(edges), "internal_edges": sum(map(len, out.values())),
            "outside_edges": len(outside), "outside_targets": len({target for _, target in outside}),
            "self_loops": sum(node in out[node] for node in graph.ids),
            "degree": {"incoming_internal": _distribution(map(len, incoming.values())),
                       "outgoing_internal": _distribution(map(len, out.values())),
                       "outgoing_boundary": _distribution(external_outgoing[i] for i in graph.ids)},
            "weak_components": _component_summary(weak, top_k),
            "strong_components": _component_summary(strong, top_k),
            "cyclic_components": _component_summary(cyclic, top_k),
            "condensation": {"nodes": len(strong), "edges": condensation_edges,
                             "depth_to_internal_sink": _distribution(depths.values()),
                             "deepest_components": [{"id": strong[i][0], "depth": depths[i],
                                                       "size": len(strong[i])} for i in depth_order[:top_k]],
                             "deepest_components_truncated": len(strong) > top_k,
                             "scope": "internal-induced-graph"},
            "top_referenced": [graph.brief(i) | {"distinct_consumers": all_incoming[i]}
                               for i in most_referenced[:top_k]],
            "top_referenced_truncated": len(most_referenced) > top_k,
            "module_coupling": {"pairs": [{"from": sm, "to": tm, "edges": coupling[(sm, tm)]}
                                            for sm, tm in module_order[:top_k]],
                                "pair_count": len(coupling), "pairs_truncated": len(coupling) > top_k,
                                "edges_with_unknown_module": coupling_unknown,
                                "includes_within_module": True},
            "roots": root_summaries,
        }
    return graph.envelope("analyze_dependencies", "iterative-kosaraju-condensation-v1",
                          {"role": role, "roots": root_ids, "top_k": top_k},
                          {"declarations": len(graph.ids), "layers": layers})


def dependency_overlap(corpus: Any, left: str, right: str, *, role: str = "all",
                       limit: int = 100) -> dict:
    """Compare direct recorded reference sets, separately for every evidence layer."""
    _integer("limit", limit, high=1000)
    graph = _Graph(corpus, role)
    a, b = graph.resolve(left), graph.resolve(right)
    layers = {}
    for evidence, edges in sorted(graph.layers.items()):
        aa = {target for source, target in edges if source == a}
        bb = {target for source, target in edges if source == b}
        groups = {"shared": sorted(aa & bb), "left_only": sorted(aa - bb), "right_only": sorted(bb - aa)}
        union = aa | bb
        layers[evidence] = {
            "evidence": evidence,
            **{key: [graph.brief(i) for i in values[:limit]] for key, values in groups.items()},
            "counts": {key: len(values) for key, values in groups.items()},
            "truncated": {key: len(values) > limit for key, values in groups.items()},
            "jaccard": len(aa & bb) / len(union) if union else None,
            "empty_union": not union,
            "interpretation": "Overlap of recorded direct references; not equivalent assumptions or proof methods.",
        }
    return graph.envelope("dependency_overlap", "direct-reference-set-overlap-v1",
                          {"role": role, "limit": limit},
                          {"left": graph.brief(a), "right": graph.brief(b), "layers": layers})


class _BudgetExceeded(Exception):
    pass


def _dominators(root: str, out: dict, incoming: dict, max_work: int):
    """Cooper-style reverse-postorder immediate dominators with an explicit budget."""
    order = list(reversed(_finish_order([root], out)))
    position = {node: i for i, node in enumerate(order)}
    parents = {root: root}
    work = 0
    passes = 0

    def tick():
        nonlocal work
        work += 1
        if work > max_work:
            raise _BudgetExceeded

    def intersect(a, b):
        while a != b:
            while position[a] > position[b]:
                tick()
                a = parents[a]
            while position[b] > position[a]:
                tick()
                b = parents[b]
        return a

    try:
        changed = True
        while changed:
            changed = False
            passes += 1
            for node in order[1:]:
                tick()
                known = [pred for pred in incoming[node] if pred in parents]
                if not known:
                    continue
                parent = known[0]
                for pred in known[1:]:
                    tick()
                    parent = intersect(parent, pred)
                if parents.get(node) != parent:
                    parents[node] = parent
                    changed = True
    except _BudgetExceeded:
        return None, order, {"work": max_work, "passes": passes, "complete": False}
    return parents, order, {"work": work, "passes": passes, "complete": True}


def dependency_bottlenecks(corpus: Any, root: str, *, role: str = "all", top_k: int = 20,
                           max_work: int = 2_000_000) -> dict:
    """Find graph dominators in each root-reachable internal reference graph.

    A returned node lies on every recorded directed path from the selected root
    to each node counted beneath it. This is a graph property only. The root is
    excluded from rankings, and each node's count includes itself. On budget
    exhaustion no partial dominance claim is returned.
    """
    _integer("top_k", top_k, high=1000)
    _integer("max_work", max_work)
    graph = _Graph(corpus, role)
    root_id = graph.resolve(root)
    layers = {}
    for evidence, edges in sorted(graph.layers.items()):
        out, incoming, outside = _adjacency(graph.ids, edges)
        parents, order, computation = _dominators(root_id, out, incoming, max_work)
        reachable = set(order)
        boundary = {target for source, target in outside if source in reachable}
        base = {"evidence": evidence, "reachable_internal_nodes": len(order),
                "outside_targets": len(boundary), "scope": "root-reachable-internal-induced-graph",
                "computation": computation, "root_excluded_from_ranking": True,
                "dominated_count_includes_self": True}
        if parents is None:
            layers[evidence] = base | {"status": "work_limit", "top_bottlenecks": [],
                                       "reason": "Work budget exhausted; no incomplete dominance claims returned."}
            continue
        subtree = {node: 1 for node in order}
        # An immediate dominator precedes its child in reverse postorder.
        for node in reversed(order):
            if node != root_id:
                subtree[parents[node]] += subtree[node]
        ranked = sorted((node for node in order if node != root_id), key=lambda n: (-subtree[n], n))
        layers[evidence] = base | {
            "status": "complete",
            "top_bottlenecks": [graph.brief(node) | {
                "dominated_nodes": subtree[node], "immediate_dominator": parents[node],
            } for node in ranked[:top_k]],
            "ranking_truncated": len(ranked) > top_k,
            "ranked_nodes": len(ranked),
        }
    return graph.envelope("dependency_bottlenecks", "budgeted-reverse-postorder-immediate-dominators-v1",
                          {"root": root_id, "role": role, "top_k": top_k, "max_work": max_work},
                          {"root": graph.brief(root_id), "layers": layers})
