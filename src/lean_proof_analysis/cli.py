"""CLI for people, scripts, and tool-using agents."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .api import analyze_project


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lpaf", description="Lean source navigation (not a proof checker)")
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
    args = p.parse_args(argv)
    if args.command == "analyze":
        try:
            result = analyze_project(
                args.source, args.out, repository=args.repo, commit=args.commit,
                expected_blobs=args.expected_manifest, entry_points=args.entry, source_prefix=args.source_prefix,
                max_pairs=args.max_pairs, min_similarity=args.min_similarity,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"lpaf: {exc}", file=sys.stderr)
            return 2
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
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
