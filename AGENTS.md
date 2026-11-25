# Repository guidance for coding agents

This public Unlicense project is a library for **scientific analysis of Lean proof corpora**. Dependency graphs, expression structure, repeated subterms, and reproducible comparisons are the primary objects of analysis. Human reading/navigation tools are one supported subset; do not redefine the project as only a proof-reading assistant or a correctness checker.

## Evidence and execution boundaries

- Preserve schema, provenance, selection, coverage, evidence, and limit metadata. Never merge `lexical_candidate` edges into `lean_elaborated` evidence.
- The source-only analyzer is heuristic and must remain text-only. Do not execute analyzed Lean code merely to scan source or resolve a failed text query.
- Intentionally requested semantic extraction may invoke `export_lean` / `lpaf export` on built modules. Use the target project's pinned toolchain; no automatic builds, dependency downloads, toolchain installation, or silent version substitution. Loading compiled Lean modules can execute their initializers.
- The native exporter has been tested with Lean 4.33.1. Other versions require explicit compatibility testing. Exported references are observations of the loaded environment, not an authentication of compiled artifacts or a proof-correctness certificate.
- Preserve references outside the selected corpus. Missing expressions, capped counts, and incomplete selections must not become empty proofs, exact counts, or complete graphs.
- Structural fingerprints, overlap, centrality, and graph dominators do not establish theorem equivalence, mathematical necessity, novelty, or correctness. Do not claim measured human benefits without an evaluation.
- Semantic export currently has no source line locations. Never fabricate them; retain declaration/module identities and artifact provenance. Source-derived statements should retain their existing source anchors.

## Interfaces and development

Public interfaces include `export_lean`, `ProofCorpus` / `CorpusView`, corpus import/open functions, the six graph/term analyses, the source-reading API, and the `lpaf` CLI. Keep Python and CLI behavior aligned; CLI formatting must not introduce a second analysis implementation. See `docs/ANALYSIS_API.md` and `docs/READING_API.md`.

Use `python -m unittest discover -s tests -v` after behavior changes. Compiler-dependent cases are optional by default; `LPAF_LEAN=/absolute/path/to/lean-4.33.1-linux/bin/lean` enables native checks with the supplied binary. Report skipped cases and tested toolchain versions accurately. The SQLite store does not make graph analysis disk-bounded; preserve resource caps and explicit incompleteness.

All input files with a supplied manifest must be present and hash-matched. Keep unverified external source trees and generated experimental data out of Git; use `work/`. Follow `docs/ROADMAP.md` for priorities and `docs/ARCHITECTURE.md` for evidence and scope.
