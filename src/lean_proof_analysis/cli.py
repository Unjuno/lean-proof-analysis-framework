"""CLI for people, scripts, and tool-using agents."""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .api import analyze_project, load_report
from .presentation import render_markdown
from .analysis_cli import ANALYSIS_COMMANDS, add_analysis_parsers, run_analysis_command
from .corpus import CorpusError
from .term_analysis import TermAnalysisError
from .reading import (
    ReadingError,
    compare_declarations,
    dependency_slice,
    find_similar,
    get_declaration,
    list_declarations,
)


class _ArgumentError(ValueError):
    """Allow the same argument errors to be rendered for people or agents."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _error(exc: Exception, *, as_json: bool, schema: str = "lpaf-reading-v0.1") -> int:
    if isinstance(exc, (ReadingError, CorpusError, TermAnalysisError)):
        detail = exc.as_dict()
    else:
        if isinstance(exc, _ArgumentError):
            code = "invalid_arguments"
        elif isinstance(exc, json.JSONDecodeError):
            code = "invalid_json"
        elif isinstance(exc, OSError):
            code = "io_error"
        else:
            code = "invalid_input"
        detail = {"code": code, "message": str(exc), "details": {}}
    if as_json:
        print(json.dumps({"schema": schema, "error": detail},
                         ensure_ascii=False, sort_keys=True))
    else:
        print(f"lpaf: {detail['message']}", file=sys.stderr)
        if detail.get("details"):
            print(json.dumps(detail["details"], ensure_ascii=False, indent=2), file=sys.stderr)
    return 2


def _reading_arguments(sub: argparse._SubParsersAction) -> None:
    search = sub.add_parser("search", help="Find declarations in a saved analysis report")
    search.add_argument("report", type=Path)
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--kind", help="Exact declaration kind, e.g. theorem or def")
    search.add_argument("--offset", type=int, default=0)
    search.add_argument("--limit", type=int, default=50)

    inspect = sub.add_parser("inspect", help="Read a declaration and its source evidence")
    inspect.add_argument("report", type=Path)
    inspect.add_argument("selector", help="Declaration ID, full name, or unique short name")
    text_limit = inspect.add_mutually_exclusive_group()
    text_limit.add_argument("--max-chars", type=int, default=12000)
    text_limit.add_argument("--full-text", action="store_true", help="Return captured text without a character cap")
    inspect.add_argument("--source-text", action="store_true", help="Include the exact captured source span")

    compare = sub.add_parser("compare", help="Compare captured statements and bodies")
    compare.add_argument("report", type=Path)
    compare.add_argument("left")
    compare.add_argument("right")
    compare.add_argument("--max-changes", type=int, default=100)
    compare.add_argument("--max-chars", type=int, default=12000)

    slice_cmd = sub.add_parser("slice", help="Follow bounded candidate reference links")
    slice_cmd.add_argument("report", type=Path)
    slice_cmd.add_argument("selector")
    slice_cmd.add_argument("--direction", choices=("dependencies", "dependents"), default="dependencies")
    slice_cmd.add_argument("--role", choices=("all", "statement", "body"), default="all")
    slice_cmd.add_argument("--max-depth", type=int, default=2)
    slice_cmd.add_argument("--max-nodes", type=int, default=50)

    similar = sub.add_parser("similar", help="Retrieve existing similarity candidates")
    similar.add_argument("report", type=Path)
    similar.add_argument("selector")
    similar.add_argument("--offset", type=int, default=0)
    similar.add_argument("--limit", type=int, default=20)

    for parser in (search, inspect, compare, slice_cmd, similar):
        parser.add_argument("--json", action="store_true", help="Print the same evidence as structured JSON")


def _query(args: argparse.Namespace) -> dict:
    report = load_report(args.report)
    if args.command == "search":
        return list_declarations(report, query=args.query, kind=args.kind,
                                 offset=args.offset, limit=args.limit)
    if args.command == "inspect":
        return get_declaration(report, args.selector,
                               max_chars=None if args.full_text else args.max_chars,
                               include_source=args.source_text)
    if args.command == "compare":
        return compare_declarations(report, args.left, args.right,
                                    max_changes=args.max_changes, max_chars=args.max_chars)
    if args.command == "slice":
        return dependency_slice(report, args.selector, direction=args.direction,
                                role=args.role, max_depth=args.max_depth, max_nodes=args.max_nodes)
    return find_similar(report, args.selector, offset=args.offset, limit=args.limit)


def main(argv: list[str] | None = None) -> int:
    p = _Parser(prog="lpaf", description="Scientific Lean proof-corpus analysis and source navigation")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="Analyze .lean files and produce review material")
    a.add_argument("source", type=Path)
    a.add_argument("--out", type=Path, default=Path("reports/latest"))
    a.add_argument("--repo", required=True, help="Source repo owner/name for links")
    a.add_argument("--commit", required=True, help="Pinned source Git commit SHA")
    a.add_argument("--expected-manifest", type=Path, help="Complete mapping of .lean paths to Git blob SHA-1")
    a.add_argument("--entry", action="append", default=[], help="Starting theorem name (repeatable)")
    a.add_argument("--source-prefix", default="", help="Input directory path inside source repository")
    a.add_argument("--max-pairs", type=int, default=100_000)
    a.add_argument("--min-similarity", type=float, default=.78)
    a.add_argument("--json", action="store_true", help="Print machine-readable result descriptor to stdout")
    _reading_arguments(sub)
    add_analysis_parsers(sub)
    raw_args = sys.argv[1:] if argv is None else argv
    try:
        args = p.parse_args(raw_args)
    except _ArgumentError as exc:
        schema = "lpaf-analysis-v0.1" if raw_args and raw_args[0] in ANALYSIS_COMMANDS else "lpaf-reading-v0.1"
        return _error(exc, as_json="--json" in raw_args, schema=schema)
    if args.command in ANALYSIS_COMMANDS:
        try:
            result = run_analysis_command(args)
        except (OSError, ValueError, sqlite3.Error) as exc:
            return _error(exc, as_json=args.json, schema="lpaf-analysis-v0.1")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=None if args.json else 2))
        return 0
    if args.command == "analyze":
        try:
            result = analyze_project(
                args.source, args.out, repository=args.repo, commit=args.commit,
                expected_blobs=args.expected_manifest, entry_points=args.entry, source_prefix=args.source_prefix,
                max_pairs=args.max_pairs, min_similarity=args.min_similarity,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _error(exc, as_json=args.json)
        descriptor = {
            "schema": result["schema"],
            "mode": result["mode"],
            "not_proof_check": result["not_proof_check"],
            "summary": result["summary"],
            "report": str((args.out / "analysis.json").resolve()),
            "overview": str((args.out / "OVERVIEW.md").resolve()),
        }
        if args.json:
            print(json.dumps(descriptor, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(descriptor, indent=2, ensure_ascii=False))
        return 0
    try:
        result = _query(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _error(exc, as_json=args.json)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_markdown(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
