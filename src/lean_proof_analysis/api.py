"""Public Python interface for source-level Lean navigation.

The current backend does not run Lean or validate proof correctness.
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Iterable
from .source_atlas import analyze


def analyze_project(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    repository: str,
    commit: str,
    expected_blobs: str | Path | None = None,
    entry_points: Iterable[str] = (),
    source_prefix: str = "",
    max_pairs: int = 100_000,
    min_similarity: float = .78,
) -> dict[str, Any]:
    """Analyze a local tree of Lean files and write JSON, CSV, DOT, and Markdown.

    `repository` and `commit` are caller-supplied provenance. They are not
    validated against the local checkout unless `expected_blobs` is provided.
    All dependency and similarity results are candidates, not Lean facts.
    """
    manifest = None
    if expected_blobs is not None:
        manifest = json.loads(Path(expected_blobs).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) == 40
            for k, v in manifest.items()
        ):
            raise ValueError("expected_blobs must map .lean paths to Git blob SHA-1 hex values")
    return analyze(
        Path(source_dir), Path(output_dir), repository, commit,
        expected=manifest, max_pairs=max_pairs, min_score=min_similarity,
        entry_names=list(entry_points), source_prefix=source_prefix,
    )


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a previous analysis.json (read-only)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
