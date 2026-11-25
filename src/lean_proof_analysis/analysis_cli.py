"""CLI adapters for the scientific corpus, graph and expression analyzers.

Each command returns the same dictionary as the library operation. The caller
owns formatting and error handling; no alternate analysis is implemented here.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .corpus import import_corpus, import_source_report, open_corpus
from .extraction import export_lean
from .graph_analysis import analyze_dependencies, dependency_bottlenecks, dependency_overlap

ANALYSIS_COMMANDS = frozenset({"export", "corpus", "graph", "overlap", "bottlenecks", "terms", "patterns", "term-compare"})


def _json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Print compact machine-readable JSON")


def _role(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--role", choices=("all", "type", "value"), default="all")


def _field(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--field", choices=("type", "value"), default="value")


def _selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kind", action="append", default=None,
                        help="Exact declaration kind to include (repeatable)")
    parser.add_argument("--module", action="append", default=None,
                        help="Exact source module to include (repeatable)")
    parser.add_argument("--prefix", default=None,
                        help="Include a namespace and its descendants")


def add_analysis_parsers(sub) -> None:
    exporter = sub.add_parser("export", help="Export built Lean modules under the project's pinned toolchain")
    exporter.add_argument("project", type=Path)
    exporter.add_argument("--out", type=Path, required=True)
    exporter.add_argument("--module", action="append", required=True,
                          help="Built module to import (repeatable)")
    exporter.add_argument("--prefix", action="append", default=[],
                          help="Declaration namespace to select (repeatable)")
    exporter.add_argument("--name", action="append", default=[],
                          help="Exact declaration name to select (repeatable)")
    exporter.add_argument("--max-declarations", type=int, default=1000)
    exporter.add_argument("--max-nodes", type=int, default=100000)
    exporter.add_argument("--timeout", type=float, default=300,
                          help="Process time limit in seconds")
    exporter.add_argument("--lean", type=Path,
                          help="Explicit Lean binary; default runs lake env lean")
    exporter.add_argument("--lean-path", type=Path,
                          help="Override LEAN_PATH for the exporter process")
    _json(exporter)

    corpus = sub.add_parser("corpus", help="Import or inspect a disk-backed proof corpus")
    actions = corpus.add_subparsers(dest="corpus_command", required=True)
    importer = actions.add_parser("import", help="Import complete exporter JSONL or a source report into a new SQLite database")
    importer.add_argument("input", type=Path)
    importer.add_argument("--db", type=Path, required=True)
    importer.add_argument("--format", choices=("jsonl", "source"), default="jsonl")
    _json(importer)
    info = actions.add_parser("info", help="Show corpus metadata and stored inventory counts")
    info.add_argument("database", type=Path)
    _json(info)

    graph = sub.add_parser("graph", help="Analyze reference degrees, components, condensation depth and module coupling")
    graph.add_argument("database", type=Path)
    _role(graph)
    graph.add_argument("--root", action="append", default=[])
    graph.add_argument("--top-k", type=int, default=20)
    _json(graph)

    overlap = sub.add_parser("overlap", help="Compare direct reference sets in each evidence layer")
    overlap.add_argument("database", type=Path)
    overlap.add_argument("left")
    overlap.add_argument("right")
    _role(overlap)
    overlap.add_argument("--limit", type=int, default=100)
    _json(overlap)

    bottlenecks = sub.add_parser("bottlenecks", help="Find recorded-graph dominators of a selected declaration")
    bottlenecks.add_argument("database", type=Path)
    bottlenecks.add_argument("root")
    _role(bottlenecks)
    bottlenecks.add_argument("--top-k", type=int, default=20)
    bottlenecks.add_argument("--max-work", type=int, default=2_000_000)
    _json(bottlenecks)

    terms = sub.add_parser("terms", help="Measure recorded expression DAG structure")
    terms.add_argument("database", type=Path)
    _field(terms)
    terms.add_argument("--top-k", type=int, default=20)
    _json(terms)

    patterns = sub.add_parser("patterns", help="Find repeated structural subterms across declarations")
    patterns.add_argument("database", type=Path)
    _field(patterns)
    patterns.add_argument("--min-nodes", type=int, default=3)
    patterns.add_argument("--min-declarations", type=int, default=2)
    patterns.add_argument("--limit", type=int, default=20)
    patterns.add_argument("--max-unique-patterns", type=int, default=100_000)
    _json(patterns)

    compare = sub.add_parser("term-compare", help="Compare recorded expression structure of two declarations")
    compare.add_argument("database", type=Path)
    compare.add_argument("left")
    compare.add_argument("right")
    _field(compare)
    _json(compare)
    for parser in (graph, overlap, bottlenecks, terms, patterns, compare):
        _selection(parser)


def _info(corpus, operation: str) -> dict:
    metadata = corpus.metadata
    if type(metadata.get("declarations")) is int and type(metadata.get("references")) is int:
        counts = {"declarations": metadata["declarations"], "references": metadata["references"]}
    else:
        # A conservative interface-level fallback for other Corpus adapters.
        counts = {"declarations": sum(1 for _ in corpus.iter_declarations(include_expressions=False)),
                  "references": sum(1 for _ in corpus.iter_references())}
    return {"schema": "lpaf-analysis-v0.1", "operation": operation,
            "not_proof_check": True, "provenance": metadata,
            "coverage": {"scope": "recorded-corpus", "selection_complete": metadata.get("selection_complete")},
            "data": {"database": str(corpus.path), "counts": counts}}


def run_analysis_command(args: argparse.Namespace) -> dict:
    """Dispatch a parsed scientific-analysis command and close the corpus handle."""
    if args.command not in ANALYSIS_COMMANDS:
        raise ValueError(f"Unknown scientific-analysis command: {args.command}")
    if args.command == "export":
        runner = (str(args.lean.expanduser().resolve()),) if args.lean else ("lake", "env", "lean")
        return export_lean(args.project, args.out, modules=args.module, prefixes=args.prefix,
                           names=args.name, runner=runner, max_declarations=args.max_declarations,
                           max_nodes=args.max_nodes, timeout=args.timeout, lean_path=args.lean_path)
    if args.command == "corpus":
        if args.corpus_command == "import":
            importer = import_corpus if args.format == "jsonl" else import_source_report
            with importer(args.input, args.db) as corpus:
                return _info(corpus, "import_corpus")
        with open_corpus(args.database) as corpus:
            return _info(corpus, "corpus_info")
    with open_corpus(args.database) as corpus:
        kinds, modules, prefix = (getattr(args, "kind", None), getattr(args, "module", None),
                                  getattr(args, "prefix", None))
        selected = corpus.select(kinds=kinds, modules=modules, name_prefix=prefix) \
            if kinds is not None or modules is not None or prefix is not None else corpus
        if args.command == "graph":
            return analyze_dependencies(selected, role=args.role, roots=args.root, top_k=args.top_k)
        if args.command == "overlap":
            return dependency_overlap(selected, args.left, args.right, role=args.role, limit=args.limit)
        if args.command == "bottlenecks":
            return dependency_bottlenecks(selected, args.root, role=args.role, top_k=args.top_k, max_work=args.max_work)
        from .term_analysis import compare_term_structure, find_repeated_subterms, profile_terms
        if args.command == "terms":
            return profile_terms(selected, field=args.field, top_k=args.top_k)
        if args.command == "patterns":
            return find_repeated_subterms(selected, field=args.field, min_nodes=args.min_nodes,
                                          min_declarations=args.min_declarations, limit=args.limit,
                                          max_unique_patterns=args.max_unique_patterns)
        return compare_term_structure(selected, args.left, args.right, field=args.field)
