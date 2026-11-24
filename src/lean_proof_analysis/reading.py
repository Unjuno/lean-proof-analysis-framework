"""Read-only, source-grounded queries shared by people and tool-using agents.

These operations navigate a saved report; they neither execute Lean nor infer
mathematical equivalence. All graph edges remain lexical candidates.
"""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

READING_SCHEMA = "lpaf-reading-v0.1"
SUPPORTED_REPORTS = {"lean-atlas-v0.1", "lean-atlas-v0.2"}
MAX_DIFF_LINES = 4000


class ReadingError(ValueError):
    """A stable error code, explanation, and machine-readable recovery details."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": deepcopy(self.details)}


def _integer(name: str, value: int, minimum: int, maximum: int | None = None) -> None:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ReadingError("invalid_argument", f"Invalid {name}", argument=name,
                           minimum=minimum, maximum=maximum)


def _character_limit(value: int | None) -> None:
    if value is not None:
        _integer("max_chars", value, 1)


class _Index:
    def __init__(self, report: dict[str, Any]):
        if (not isinstance(report, dict) or not isinstance(report.get("schema"), str)
                or report["schema"] not in SUPPORTED_REPORTS):
            raise ReadingError("unsupported_report", "Use a supported LPAF analysis.json report",
                               supported_schemas=sorted(SUPPORTED_REPORTS))
        if report.get("mode") != "source-only-unelaborated" or report.get("not_proof_check") is not True:
            raise ReadingError("unsupported_report", "These queries require source-only evidence metadata")
        self.report = report
        records = report.get("declarations")
        if not isinstance(records, list) or not isinstance(report.get("provenance"), dict):
            raise ReadingError("invalid_report", "Missing declarations or provenance")
        self.by_id: dict[str, dict[str, Any]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_short: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for d in records:
            if not isinstance(d, dict) or any(not isinstance(d.get(k), str) for k in
                                             ("id", "name", "kind", "path", "source_url", "statement", "body")):
                raise ReadingError("invalid_report", "Declaration fields have missing or invalid types")
            if not d["id"] or d["id"] in self.by_id:
                raise ReadingError("invalid_report", "Declaration IDs must be nonempty and unique")
            if any(type(d.get(k)) is not int or d[k] < 1 for k in ("line", "end_line")):
                raise ReadingError("invalid_report", "Invalid declaration line anchors", declaration=d["id"])
            if d["end_line"] < d["line"]:
                raise ReadingError("invalid_report", "Declaration end_line precedes line", declaration=d["id"])
            short = d.get("short_name", d["name"].rsplit(".", 1)[-1])
            if not isinstance(short, str) or not short:
                raise ReadingError("invalid_report", "Invalid short declaration name", declaration=d["id"])
            if "source_text" in d and not isinstance(d["source_text"], str):
                raise ReadingError("invalid_report", "source_text must be a string", declaration=d["id"])
            flags = d.get("text_truncated", {})
            if not isinstance(flags, dict) or any(type(v) is not bool for v in flags.values()):
                raise ReadingError("invalid_report", "text_truncated must contain boolean flags", declaration=d["id"])
            if "extraction" in d and not isinstance(d["extraction"], dict):
                raise ReadingError("invalid_report", "extraction must be an object", declaration=d["id"])
            self.by_id[d["id"]] = d
            self.by_name[d["name"]].append(d)
            self.by_short[short].append(d)
        self.records = sorted(records, key=lambda d: (d["path"], d["line"], d["id"]))
        files = report["provenance"].get("files", [])
        if not isinstance(files, list) or any(not isinstance(f, dict) or not isinstance(f.get("path"), str) for f in files):
            raise ReadingError("invalid_report", "Invalid file provenance")
        self.files = {f["path"]: f for f in files}
        if len(self.files) != len(files):
            raise ReadingError("invalid_report", "File provenance paths must be unique")
        edges = report.get("candidate_links", [])
        if not isinstance(edges, list):
            raise ReadingError("invalid_report", "candidate_links must be a list")
        self.edges = []
        for edge in edges:
            if (not isinstance(edge, dict) or not isinstance(edge.get("from"), str)
                    or not isinstance(edge.get("to"), str) or not isinstance(edge.get("role"), str)
                    or edge.get("from") not in self.by_id
                    or edge.get("to") not in self.by_id or edge.get("role") not in {"statement", "body"}):
                raise ReadingError("invalid_report", "Invalid or dangling candidate link")
            self.edges.append({k: deepcopy(edge.get(k)) for k in
                               ("from", "to", "role", "resolution", "evidence_token")} |
                              {"evidence": "lexical_candidate"})
        self.edges.sort(key=lambda e: tuple(str(e[k]) for k in
                                           ("from", "to", "role", "resolution", "evidence_token")))

    def resolve(self, selector: str) -> dict[str, Any]:
        if not isinstance(selector, str) or not selector.strip():
            raise ReadingError("invalid_selector", "Provide an exact declaration ID or name")
        if selector in self.by_id:
            return self.by_id[selector]
        choices = self.by_name.get(selector) or self.by_short.get(selector) or []
        if not choices:
            raise ReadingError("declaration_not_found", "No matching declaration in the analyzed sample", selector=selector)
        if len(choices) > 1:
            ordered = sorted(choices, key=lambda d: (d["path"], d["line"], d["id"]))
            raise ReadingError("ambiguous_selector", "Use an exact declaration ID to disambiguate",
                               selector=selector, candidates=[self.brief(d) for d in ordered[:50]],
                               total_candidates=len(ordered), candidates_truncated=len(ordered) > 50)
        return choices[0]

    def brief(self, d: dict[str, Any]) -> dict[str, Any]:
        result = {k: d[k] for k in ("id", "name", "kind", "path", "line", "end_line", "source_url")}
        result["source_file_url"] = d["source_url"].split("#", 1)[0]
        result["git_blob_sha1"] = self.files.get(d["path"], {}).get("git_blob_sha1")
        return result

    def envelope(self, operation: str, data: dict[str, Any], ids: list[str]) -> dict[str, Any]:
        paths = {self.by_id[i]["path"] for i in ids}
        provenance = {k: deepcopy(self.report["provenance"].get(k)) for k in
                      ("repository", "commit", "source_hashes_checked", "manifest_complete")}
        provenance["files"] = [deepcopy(self.files[p]) for p in sorted(paths) if p in self.files]
        return {
            "schema": READING_SCHEMA, "operation": operation, "mode": self.report["mode"],
            "not_proof_check": True, "provenance": provenance,
            "coverage": {
                "input_schema": self.report["schema"], "scope": "analyzed-source-sample",
                "declarations_in_report": len(self.records), "semantic_dependencies_complete": False,
                "context_complete": False,
                "notes": [
                    "Declaration boundaries and names are source-level heuristics.",
                    "Section variables, notation, implicit arguments and name resolution are not reconstructed.",
                    "Candidate links can be missing or spurious; an empty result does not establish absence of dependencies.",
                    "Manifest checks compare bytes with the supplied manifest, not an independently authenticated revision.",
                ],
            },
            "data": data,
        }


def _completeness(d: dict[str, Any], field: str) -> str:
    flags = d.get("text_truncated", {})
    flag = flags.get(field) if isinstance(flags, dict) else None
    if field not in d or flag is None:
        return "unknown"
    return "complete_capture" if flag is False else "truncated_input"


def _text(value: str, limit: int | None, completeness: str, *, available: bool = True) -> dict[str, Any]:
    shown = value if limit is None else value[:limit]
    return {"text": shown, "available": available, "available_characters": len(value),
            "returned_characters": len(shown), "truncated": len(shown) < len(value),
            "input_completeness": completeness}


def list_declarations(report: dict[str, Any], *, query: str = "", kind: str | None = None,
                      offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """Case-insensitive substring search over name, path and captured statement.

    Pagination is deterministic in path/line/ID order. It is not semantic search.
    """
    _integer("offset", offset, 0)
    _integer("limit", limit, 1, 1000)
    if not isinstance(query, str) or (kind is not None and not isinstance(kind, str)):
        raise ReadingError("invalid_argument", "query and kind must be strings")
    idx = _Index(report)
    needle = query.casefold()
    matches = [d for d in idx.records if (kind is None or d["kind"] == kind) and
               any(needle in d[k].casefold() for k in ("name", "path", "statement"))]
    page = matches[offset:offset + limit]
    data = {"query": query, "kind": kind, "search_fields": ["name", "path", "statement"],
            "declarations": [idx.brief(d) | {"statement_preview": _text(d["statement"], 240,
                                _completeness(d, "statement"))} for d in page],
            "total": len(matches), "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(matches) else None}
    return idx.envelope("list_declarations", data, [d["id"] for d in page])


def get_declaration(report: dict[str, Any], selector: str, *, max_chars: int | None = 12000,
                    include_source: bool = False) -> dict[str, Any]:
    """Return captured statement/body and, optionally, the original source span.

    max_chars=None returns all stored text. A complete capture is still not an
    elaborated signature: enclosing context may be absent.
    """
    _character_limit(max_chars)
    idx = _Index(report)
    d = idx.resolve(selector)
    fields = ["statement", "body"] + (["source_text"] if include_source else [])
    card = idx.brief(d) | {
        "text": {k: _text(d.get(k, ""), max_chars, _completeness(d, k), available=k in d) for k in fields},
        "tactics": deepcopy(d.get("tactics", [])),
        "extraction": deepcopy(d.get("extraction", {
            "method": "source-regex", "boundaries": "heuristic", "elaborated": False,
            "context_complete": False, "text_completeness": "unknown-legacy-report"})),
    }
    return idx.envelope("get_declaration", {
        "declaration": card, "limits": {"max_chars_per_field": max_chars, "include_source": include_source}
    }, [d["id"]])


def _diff(left: dict[str, Any], right: dict[str, Any], field: str,
          max_changes: int, max_chars: int) -> dict[str, Any]:
    a, b = left[field], right[field]
    complete = all(_completeness(d, field) == "complete_capture" for d in (left, right))
    result: dict[str, Any] = {
        "relation": ("same_captured_text" if a == b else "different_captured_text") if complete else "unknown_incomplete_input",
        "equal": a == b if complete else None, "input_complete": complete,
        "changes": [], "total_changes": None, "returned_changes": 0, "truncated": False,
        "status": "complete" if complete else "input_incomplete",
        "limits": {"max_changes": max_changes, "max_characters_total": max_chars,
                   "max_lines_per_input": MAX_DIFF_LINES},
    }
    if not complete:
        result["reason"] = "Re-analyze the source to compare complete captured text; legacy previews cannot establish equality."
        return result
    if a == b:
        result["total_changes"] = 0
        return result
    aa, bb = a.splitlines(keepends=True), b.splitlines(keepends=True)
    if max(len(aa), len(bb)) > MAX_DIFF_LINES:
        result.update(status="skipped_size_limit", truncated=True,
                      reason="Texts differ; detailed diff exceeds the line budget. Inspect each declaration.")
        return result
    opcodes = [op for op in SequenceMatcher(None, aa, bb, autojunk=True).get_opcodes() if op[0] != "equal"]
    budget = max_chars
    for tag, i, j, k, l in opcodes[:max_changes]:
        left_text, right_text = "".join(aa[i:j]), "".join(bb[k:l])
        # Share the character budget between both sides; do not hide the changed
        # side simply because the original side is a very long line.
        left_allowance = min(len(left_text), (budget + 1) // 2 if right_text else budget)
        right_allowance = min(len(right_text), budget - left_allowance)
        left_allowance = min(len(left_text), budget - right_allowance)
        lt = _text(left_text, left_allowance, "complete_capture")
        rt = _text(right_text, right_allowance, "complete_capture")
        result["changes"].append({
            "kind": tag,
            "left": {"start_line": i + 1 if j > i else None, "end_line": j if j > i else None,
                     "line_count": j - i, "insertion_after_line": i if j == i else None, **lt},
            "right": {"start_line": k + 1 if l > k else None, "end_line": l if l > k else None,
                      "line_count": l - k, "insertion_after_line": k if l == k else None, **rt},
        })
        budget -= lt["returned_characters"] + rt["returned_characters"]
        result["truncated"] |= lt["truncated"] or rt["truncated"]
        if budget <= 0:
            break
    result["total_changes"] = len(opcodes)
    result["returned_changes"] = len(result["changes"])
    result["truncated"] |= len(result["changes"]) < len(opcodes)
    if result["truncated"]:
        result["status"] = "truncated"
    return result


def compare_declarations(report: dict[str, Any], left: str, right: str, *,
                         max_changes: int = 100, max_chars: int = 12000) -> dict[str, Any]:
    """Compare statement and body text independently, preserving literal values.

    Differences have line anchors relative to each captured field. Neither text
    equality nor shared candidate references establishes mathematical equivalence.
    """
    _integer("max_changes", max_changes, 1, 1000)
    _integer("max_chars", max_chars, 1)
    idx = _Index(report)
    a, b = idx.resolve(left), idx.resolve(right)
    reference_data = {}
    cited_ids = [a["id"], b["id"]]
    for role in ("statement", "body"):
        aset = {e["to"] for e in idx.edges if e["from"] == a["id"] and e["role"] == role}
        bset = {e["to"] for e in idx.edges if e["from"] == b["id"] and e["role"] == role}
        buckets = {"shared": sorted(aset & bset), "left_only": sorted(aset - bset), "right_only": sorted(bset - aset)}
        reference_data[role] = {k: [idx.brief(idx.by_id[i]) for i in ids[:max_changes]] for k, ids in buckets.items()}
        reference_data[role].update(counts={k: len(ids) for k, ids in buckets.items()},
                                    truncated=any(len(ids) > max_changes for ids in buckets.values()),
                                    evidence="lexical_candidate")
        cited_ids.extend(i for ids in buckets.values() for i in ids[:max_changes])
    data = {"left": idx.brief(a), "right": idx.brief(b),
            "statement": _diff(a, b, "statement", max_changes, max_chars),
            "body": _diff(a, b, "body", max_changes, max_chars), "references": reference_data,
            "limits": {"max_changes_per_field": max_changes, "max_chars_per_field": max_chars,
                       "max_references_per_bucket": max_changes},
            "interpretation": "Text differences and candidate-reference overlap only; no equivalence or implication judgment."}
    return idx.envelope("compare_declarations", data, cited_ids)


def dependency_slice(report: dict[str, Any], selector: str, *, direction: str = "dependencies",
                     role: str = "all", max_depth: int = 2, max_nodes: int = 50) -> dict[str, Any]:
    """Bounded breadth-first navigation of the available candidate graph.

    Incoming navigation retains original consumer-to-reference edge directions.
    Nodes are ordered by distance, then deterministic neighbor IDs. A complete
    traversal means only that no *observed candidate* was excluded by the bounds.
    """
    _integer("max_depth", max_depth, 0, 1000)
    _integer("max_nodes", max_nodes, 1, 1000)
    if (not isinstance(direction, str) or not isinstance(role, str)
            or direction not in {"dependencies", "dependents"} or role not in {"all", "statement", "body"}):
        raise ReadingError("invalid_argument", "Invalid direction or role")
    idx = _Index(report)
    root = idx.resolve(selector)
    selected_edges = [e for e in idx.edges if role == "all" or e["role"] == role]
    adjacency: dict[str, set[str]] = defaultdict(set)
    for e in selected_edges:
        source, target = (e["from"], e["to"]) if direction == "dependencies" else (e["to"], e["from"])
        adjacency[source].add(target)
    depths = {root["id"]: 0}
    via: dict[str, str | None] = {root["id"]: None}
    queue = deque([root["id"]])
    while queue:
        node = queue.popleft()
        if depths[node] >= max_depth:
            continue
        for nxt in sorted(adjacency[node]):
            if nxt not in depths and len(depths) < max_nodes:
                depths[nxt] = depths[node] + 1
                via[nxt] = node
                queue.append(nxt)
    frontier = []
    frontier_total = 0
    for node in depths:
        for nxt in sorted(adjacency[node]):
            if nxt not in depths:
                frontier_total += 1
                if len(frontier) < max_nodes:
                    frontier.append({"from": node, "next": nxt,
                                     "reason": "max_depth" if depths[node] >= max_depth else "max_nodes"})
    edges = [e for e in selected_edges if e["from"] in depths and e["to"] in depths]
    # Edge evidence can repeat for multiple lexical tokens; bound its output
    # independently from the node budget and expose omissions.
    edge_limit = max_nodes * 20
    data = {"root": idx.brief(root), "direction": direction, "role": role,
            "nodes": [{"declaration": idx.brief(idx.by_id[i]), "depth": depth, "via": via[i]}
                      for i, depth in depths.items()],
            "edges": deepcopy(edges[:edge_limit]), "edges_total": len(edges),
            "edges_truncated": len(edges) > edge_limit,
            "frontier": frontier, "frontier_total": frontier_total,
            "frontier_truncated": frontier_total > len(frontier),
            "limits": {"max_depth": max_depth, "max_nodes": max_nodes, "max_edges": edge_limit},
            "traversal_complete": frontier_total == 0,
            "interpretation": "Reachability in a lexical candidate graph, not a sufficient or minimal proof-reading set."}
    return idx.envelope("dependency_slice", data, list(depths))


def find_similar(report: dict[str, Any], selector: str, *, limit: int = 20,
                 offset: int = 0) -> dict[str, Any]:
    """Retrieve existing source-similarity candidates, without model calls."""
    _integer("limit", limit, 1, 1000)
    _integer("offset", offset, 0)
    idx = _Index(report)
    target = idx.resolve(selector)
    candidates = report.get("similarity_candidates", [])
    if not isinstance(candidates, list):
        raise ReadingError("invalid_report", "similarity_candidates must be a list")
    matches = []
    for c in candidates:
        if (not isinstance(c, dict) or not isinstance(c.get("from"), str)
                or not isinstance(c.get("to"), str) or c["from"] not in idx.by_id or c["to"] not in idx.by_id):
            raise ReadingError("invalid_report", "Invalid or dangling similarity candidate")
        if target["id"] not in {c["from"], c["to"]}:
            continue
        other = c["to"] if c["from"] == target["id"] else c["from"]
        matches.append({"declaration": idx.brief(idx.by_id[other]), "similarity": deepcopy(c)})
    # The saved report defines the ranking; do not silently re-rank by a
    # different interpretation of the similarity score.
    page = matches[offset:offset + limit]
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        raise ReadingError("invalid_report", "summary must be an object")
    data = {"target": idx.brief(target), "matches": page, "total": len(matches),
            "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(matches) else None,
            "search_coverage": {"scope": "stored-candidates-only", "exhaustive": False,
                                "analysis_limits": deepcopy(summary.get("similarity_search", {}))},
            "interpretation": "Source-text similarity candidates; scores do not establish equivalence."}
    return idx.envelope("find_similar", data, [target["id"]] + [m["declaration"]["id"] for m in page])
