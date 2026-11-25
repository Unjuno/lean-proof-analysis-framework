#!/usr/bin/env python3
"""Compile the original fixture and check real Lean Expr extraction.

No toolchain is installed automatically. Supply --lean or LPAF_LEAN with the
target executable. The fixture's own supported version is pinned in lean/.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "src" / "lean_proof_analysis" / "lean" / "Export.lean"


def lean_path(value: str | None) -> Path:
    candidate = value or os.environ.get("LPAF_LEAN") or shutil.which("lean")
    if not candidate:
        raise ValueError("Supply --lean or LPAF_LEAN; no Lean executable was found")
    resolved = Path(candidate).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Lean executable does not exist: {resolved}")
    return resolved


def run_fixture(binary: Path, extra_args: list[str] | None = None) -> tuple[str, list[dict]]:
    """Build with this binary; isolate module artifacts and export the fixture."""
    with tempfile.TemporaryDirectory(prefix="lpaf-lean-fixture-") as directory:
        environment = dict(os.environ)
        environment["PATH"] = str(binary.parent) + os.pathsep + environment.get("PATH", "")
        environment["LEAN_PATH"] = directory + (os.pathsep + environment["LEAN_PATH"]
                                                if environment.get("LEAN_PATH") else "")
        subprocess.run(
            [str(binary), "-o", str(Path(directory) / "Fixture.olean"), "Fixture.lean"],
            cwd=ROOT / "lean", env=environment, check=True,
            text=True, capture_output=True, timeout=120,
        )
        result = subprocess.run(
            [str(binary), "--run", str(EXPORTER),
             "--module", "Fixture", "--prefix", "LPAF.Fixture", *(extra_args or [])],
            cwd=ROOT, env=environment, check=True,
            text=True, capture_output=True, timeout=120,
        )
        records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        return result.stdout, records


def check_records(records: list[dict]) -> dict:
    if len(records) < 2 or records[0].get("record") != "header" or records[-1].get("record") != "footer":
        raise ValueError("Export is missing its header or completion footer")
    if records[0].get("schema") != "lpaf-corpus-v0.1":
        raise ValueError("Unexpected corpus schema")
    declarations = records[1:-1]
    if len(declarations) != records[-1]["declarations"]:
        raise ValueError("Footer declaration count disagrees with export")
    for record in declarations:
        if record.get("record") != "declaration" or record.get("evidence") != "lean_elaborated":
            raise ValueError("Invalid declaration record")
        for field in ("type_expr", "value_expr"):
            expression = record[field]
            status = record["expression_status"][field.removesuffix("_expr")]
            if expression is None:
                if status == "available":
                    raise ValueError("Null expression mislabeled available")
                continue
            nodes = expression["nodes"]
            if expression.get("truncated") is not False or not 0 <= expression["root"] < len(nodes):
                raise ValueError("Expression is truncated or has an invalid root")
            for index, node in enumerate(nodes):
                if not all(type(child) is int and 0 <= child < index for child in node["children"]):
                    raise ValueError("Expression DAG is not in postorder")
                if not all(isinstance(item, str) for item in node["data"]):
                    raise ValueError("Constructor data must be lossless strings")
    return {
        "lean_version": records[0]["lean_version"],
        "declarations": len(declarations),
        "complete": records[-1]["complete"],
        "expr_nodes": sum(len(d[field]["nodes"]) for d in declarations
                          for field in ("type_expr", "value_expr") if d[field] is not None),
        "not_proof_check": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean", help="Explicit Lean executable; otherwise LPAF_LEAN or PATH")
    parser.add_argument("--out", type=Path, help="Write checked fixture JSONL to this path")
    args = parser.parse_args()
    try:
        text, records = run_fixture(lean_path(args.lean))
        summary = check_records(records)
        if not summary["complete"]:
            raise ValueError("Default fixture export unexpectedly truncated")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Lean export check failed: {error}")
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stdout)
            print(error.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
