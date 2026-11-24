"""Readable Markdown views of the same bounded records returned to agents."""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit


def _inline(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace("\n", " ").replace("\r", " ")
    for char in "`*_{}[]<>|":
        text = text.replace(char, "\\" + char)
    return text


def _link(label: str, url: str | None) -> str:
    if not url or urlsplit(url).scheme not in {"http", "https"}:
        return _inline(label)
    target = quote(url, safe=":/#?&=%+@._~-")
    return f"[{_inline(label)}]({target})"


def _name(declaration: dict) -> str:
    return _link(declaration.get("name", declaration.get("id", "Declaration")),
                 declaration.get("source_url"))


def _fence(text: str, language: str = "lean") -> str:
    longest = max((len(match.group()) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _text_block(title: str, record: dict) -> list[str]:
    lines = [f"### {title}", ""]
    if not record.get("available", False):
        return lines + ["Captured text is unavailable.", ""]
    lines.extend([_fence(record.get("text", "")), ""])
    if record.get("truncated"):
        lines.extend([
            f"**Output truncated:** {record.get('returned_characters', 0)} of "
            f"{record.get('available_characters', 0)} available characters returned.", "",
        ])
    if record.get("input_completeness") != "complete_capture":
        lines.extend([f"Input completeness: `{record.get('input_completeness', 'unknown')}`.", ""])
    return lines


def _location(declaration: dict) -> str:
    path = declaration.get("path", "")
    first, last = declaration.get("line"), declaration.get("end_line")
    return _inline(f"{path}:{first}" + (f"–{last}" if last and last != first else ""))


def _pagination(data: dict) -> str:
    text = f"Total matches: **{data.get('total', 0)}**. Offset: {data.get('offset', 0)}."
    if data.get("next_offset") is not None:
        text += f" Next offset: **{data['next_offset']}**."
    return text


def _search(data: dict) -> list[str]:
    lines = [f"Query: {_inline(data.get('query', '')) or '(all declarations)'}. "
             f"Kind: {_inline(data.get('kind') or 'all')}.", "", _pagination(data), "",
             "| Declaration | Kind | Location | Captured statement preview |",
             "|---|---|---|---|"]
    for item in data.get("declarations", []):
        preview = item.get("statement_preview", {})
        suffix = " [truncated]" if preview.get("truncated") else ""
        if preview.get("input_completeness") != "complete_capture":
            suffix += " [incomplete or unknown input]"
        lines.append(f"| {_name(item)} | {_inline(item.get('kind', ''))} | {_location(item)} | "
                     f"{_inline(preview.get('text', ''))}{suffix} |")
    return lines + [""]


def _inspect(data: dict) -> list[str]:
    declaration = data["declaration"]
    lines = [f"## {_name(declaration)}", "", f"- ID: {_inline(declaration['id'])}",
             f"- Kind: {_inline(declaration.get('kind', ''))}",
             f"- Location: {_location(declaration)}",
             f"- {_link('Open enclosing source file', declaration.get('source_file_url'))}", ""]
    for key, label in (("statement", "Captured statement"), ("body", "Captured body"),
                       ("source_text", "Exact captured source span")):
        record = declaration.get("text", {}).get(key)
        if record is not None:
            lines.extend(_text_block(label, record))
    if declaration.get("tactics"):
        lines.extend(["Detected tactic-name tokens: " +
                      ", ".join(_inline(token) for token in declaration["tactics"]) + ".", ""])
    return lines


def _difference(title: str, difference: dict) -> list[str]:
    labels = {
        "same_captured_text": "Same captured text",
        "different_captured_text": "Different captured text",
        "unknown_incomplete_input": "Relationship unknown: incomplete input",
    }
    relation = difference.get("relation", "unknown")
    lines = [f"## {title}", "", labels.get(relation, _inline(relation)) + ".",
             f"Diff status: `{difference.get('status', 'unknown')}`. "
             f"Returned changes: {difference.get('returned_changes', 0)}; "
             f"total changes: {difference.get('total_changes') if difference.get('total_changes') is not None else 'unknown'}.", ""]
    if difference.get("truncated"):
        lines.extend(["**The returned diff is truncated; additional text or changes were omitted.**", ""])
    if difference.get("reason"):
        lines.extend([_inline(difference["reason"]), ""])
    for number, change in enumerate(difference.get("changes", []), 1):
        lines.extend([f"### Change {number}: {_inline(change.get('kind', 'change'))}", ""])
        for side in ("left", "right"):
            record = change.get(side, {})
            if record.get("line_count") == 0:
                label = f"{side.title()} (insertion point after captured-text line {record.get('insertion_after_line', 0)})"
            else:
                label = f"{side.title()} (captured-text lines {record.get('start_line', '?')}–{record.get('end_line', '?')})"
            # Diff sides use the same text record contract as declaration fields.
            lines.extend(_text_block(label, record))
    return lines


def _compare(data: dict) -> list[str]:
    lines = [f"Left: {_name(data['left'])} ({_location(data['left'])}).", "",
             f"Right: {_name(data['right'])} ({_location(data['right'])}).", ""]
    lines.extend(_difference("Statement text", data["statement"]))
    lines.extend(_difference("Body text", data["body"]))
    lines.extend(["## Candidate reference comparison", "",
                  "These are lexical name matches, not a comparison of mathematical assumptions.", ""])
    for role in ("statement", "body"):
        references = data.get("references", {}).get(role, {})
        lines.extend([f"### {role.title()} references", ""])
        for key, label in (("shared", "Shared"), ("left_only", "Left only"), ("right_only", "Right only")):
            items = references.get(key, [])
            count = references.get("counts", {}).get(key, len(items))
            lines.append(f"- {label} ({count} total): " + (", ".join(_name(item) for item in items) or "no candidates returned"))
        if references.get("truncated"):
            lines.append("- **Reference lists are truncated.**")
        lines.append("")
    return lines


def _slice(data: dict) -> list[str]:
    lines = [f"Root: {_name(data['root'])}.", "",
             f"Direction: `{data['direction']}`. Role: `{data['role']}`. "
             f"Candidate traversal complete within the recorded graph: **{'yes' if data.get('traversal_complete') else 'no'}**.", "",
             f"Limits: depth {data.get('limits', {}).get('max_depth')}, "
             f"nodes {data.get('limits', {}).get('max_nodes')}.", "",
             "| Depth | Declaration | Location |", "|---:|---|---|"]
    for node in data.get("nodes", []):
        declaration = node["declaration"]
        lines.append(f"| {node['depth']} | {_name(declaration)} | {_location(declaration)} |")
    lines.extend(["", "### Candidate edges", "", "| From ID | To ID | Role | Matched token |",
                  "|---|---|---|---|"])
    for edge in data.get("edges", []):
        lines.append(f"| {_inline(edge['from'])} | {_inline(edge['to'])} | {_inline(edge['role'])} | "
                     f"{_inline(edge.get('evidence_token', ''))} |")
    if data.get("edges_truncated"):
        lines.extend(["", f"**Edge output truncated:** {len(data.get('edges', []))} of "
                      f"{data.get('edges_total', 'unknown')} recorded edges returned."])
    lines.extend(["", f"Frontier candidates omitted by traversal limits: **{data.get('frontier_total', 0)}**.", ""])
    for frontier in data.get("frontier", []):
        lines.append(f"- {_inline(frontier['from'])} → {_inline(frontier['next'])}: {_inline(frontier['reason'])}")
    if data.get("frontier_truncated"):
        lines.append("- **The displayed frontier is itself truncated.**")
    return lines + [""]


def _similar(data: dict) -> list[str]:
    lines = [f"Target: {_name(data['target'])}.", "", _pagination(data), "",
             "The list retrieves candidates from the existing bounded similarity search.", "",
             "| Candidate | Text cosine score | Same syntax fingerprint | Shared tactic tokens |",
             "|---|---:|---|---|"]
    for match in data.get("matches", []):
        similarity = match.get("similarity", {})
        lines.append(f"| {_name(match['declaration'])} | {_inline(similarity.get('tfidf_cosine', ''))} | "
                     f"{'yes' if similarity.get('same_syntax_fingerprint') else 'no'} | "
                     f"{_inline(', '.join(similarity.get('shared_tactics', [])))} |")
    coverage = data.get("search_coverage", {})
    if coverage:
        lines.extend(["", "Search coverage:", ""])
        for key, value in coverage.items():
            lines.append(f"- {_inline(key)}: {_inline(value)}")
    return lines + [""]


def render_markdown(result: dict) -> str:
    """Render a query envelope without dropping coverage or truncation warnings."""
    operation = result["operation"]
    titles = {
        "list_declarations": "Declaration search",
        "get_declaration": "Declaration reading card",
        "compare_declarations": "Captured text comparison",
        "dependency_slice": "Candidate reference slice",
        "find_similar": "Similar declaration candidates",
    }
    provenance = result.get("provenance", {})
    lines = [f"# {titles.get(operation, _inline(operation))}", "",
             "> Source-only reading aid. References and similarities are candidates; this is not a proof check.", "",
             f"Source: {_inline(provenance.get('repository', 'unknown'))} at "
             f"`{_inline(provenance.get('commit', 'unknown'))}`.", "",
             f"Input manifest matched: {_inline(provenance.get('source_hashes_checked'))}. "
             f"Manifest complete for the analyzed sample: {_inline(provenance.get('manifest_complete'))}.", ""]
    renderers = {"list_declarations": _search, "get_declaration": _inspect,
                 "compare_declarations": _compare, "dependency_slice": _slice,
                 "find_similar": _similar}
    renderer = renderers.get(operation)
    if renderer is None:
        raise ValueError(f"Unsupported reading operation: {operation}")
    lines.extend(renderer(result["data"]))
    coverage = result.get("coverage", {})
    lines.extend(["## Reading limits", "",
                  f"- Scope: {_inline(coverage.get('scope', 'unknown'))}.",
                  "- Enclosing context and semantic dependency completeness are not established by source scanning."])
    for note in coverage.get("notes", []):
        lines.append(f"- {_inline(note)}")
    return "\n".join(lines).rstrip() + "\n"
