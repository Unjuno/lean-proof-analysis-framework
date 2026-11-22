# Roadmap

Priority is based on reliable evidence and human usefulness, **not** the number of analysis algorithms.

## Milestone 0 — repository foundation (current)

- [x] Public Unlicense repository structure.
- [x] Installable Python package with CLI/JSON and Python API.
- [x] Source-level analysis baseline and deterministic unit tests.
- [x] Pinned RH 10-file example and expected-hash manifest.
- [x] Agent usage contract and limitations.
- [ ] Demonstrate reproducibility on a fresh clone in CI with a pinned upstream download (network-gated).

## Milestone 1 — trustworthy Lean data extraction

- [ ] Use the Lean project's pinned `lean-toolchain` / `lake-manifest.json`.
- [ ] Add an elaborator-backed extractor for declaration names, types, `Expr`, and reference edges.
- [ ] Preserve declaration origin, namespaces, implicit arguments and source locations.
- [ ] Persist unknown/unresolved entities and per-stage errors rather than dropping them.
- [ ] Benchmark extraction against a manually checked sample.

## Milestone 2 — analysis library

- [ ] Common typed data schema with provenance and evidence types.
- [ ] Graph algorithms (reachable roots, modules, shared dependencies, centrality).
- [ ] Structural similarity on elaborated types; distinguish type similarity from proof-step similarity.
- [ ] Lexical and structural retrieval as independently measurable baselines.
- [ ] Control computational costs through SQLite indexes, incremental runs and capped candidate retrieval.

## Milestone 3 — human/agent workflows

- [ ] Minimal review pages with premises, source locations and differences.
- [ ] Selectable scope and expandable abstractions with transparent omissions.
- [ ] Optional model-generated explanations tied to source evidence.
- [ ] Optional MCP tools wrapping the same API; security and test plan required.

## Milestone 4 — evaluation

- [ ] Compare search-only, graph-only, and combined interfaces.
- [ ] Run a small human pilot on navigation/compare tasks with source-grounded answer keys.
- [ ] Evaluate correctness of retrieved information, unresolved cases, time, and subjective burden.
- [ ] Replicate on at least one unrelated Lean project.

## First work items

1. Fix the source-only baseline and manifest completeness regression tests.
2. Implement elaborated Lean reference extraction on a small, pinned fixture.
3. Define an explicit JSON schema for typed evidence records.
4. Decide which reviewer tasks the interface must optimize before adding more statistics.
