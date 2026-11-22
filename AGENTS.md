# Repository guidance for coding agents

This is a public Unlicense toolkit for human/agent navigation of Lean formal proofs. The source-only analyzer is **heuristic**: do not describe its results as a formal verification of dependencies or theorem equivalence. Keep `mode` and provenance metadata intact. Do not execute analyzed Lean code just to parse text.

Use `python -m unittest discover -s tests -v` after changes. Public interface: `lean_proof_analysis.analyze_project` and the `lpaf` CLI. All input files with a supplied manifest must be present and SHA-matched. Keep unverified external source trees out of Git; use `work/`.

Next priorities are in `docs/ROADMAP.md`; evidence levels are documented in `docs/ARCHITECTURE.md`.
