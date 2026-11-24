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
- [x] Versioned source-reading query envelope, structured errors, and explicit bounds.
- [x] Declaration search/inspection and statement/body text comparison.
- [x] Bounded forward/reverse candidate-reference slices and stored similarity retrieval.
- [ ] Graph algorithms (reachable roots, modules, shared dependencies, centrality).
- [ ] Structural similarity on elaborated types; distinguish type similarity from proof-step similarity.
- [ ] Lexical and structural retrieval as independently measurable baselines.
- [ ] Control computational costs through SQLite indexes, incremental runs and capped candidate retrieval.

## Milestone 3 — human/agent workflows

- [x] CLI Markdown and JSON over the same reading functions and source locations.
- [x] Explicit text caps, pagination and candidate-graph exploration frontiers.
- [ ] Full elaborated premises and actual reference information in reading cards.
- [ ] Expandable groups, representative examples with differences, and accepted-lemma reading boundaries.
- [ ] Optional model-generated explanations tied to source evidence.
- [ ] Optional MCP tools wrapping the same API; security and test plan required.

## Milestone 4 — evaluation

- [ ] Compare search-only, graph-only, and combined interfaces.
- [ ] Run a small human pilot on navigation/compare tasks with source-grounded answer keys.
- [ ] Evaluate correctness of retrieved information, unresolved cases, time, and subjective burden.
- [ ] Replicate on at least one unrelated Lean project.

## First work items

1. Use the v0.2 reading workflow on concrete declaration lookup, comparison and reference-navigation questions; see [reading tools](READING_TOOLS.md).
2. Extend the query envelope into the common typed extraction/evidence schema tracked in issue #2; the v0.2 source contract does not complete that milestone.
3. Implement elaborated Lean reference extraction on a small, pinned fixture (issue #1), separating type references from proof/body references.
4. Add resolved binder/assumption cards and selective definition expansion using that extractor.
5. Evaluate task accuracy and effort on the RH sample and an unrelated project (issue #3). Pattern grouping and reading packets follow the evidence requirements in the design document.

Manifest completeness tests and preservation of full captured text are already
implemented. Adding more statistical scores is secondary to making specific
reading questions answerable with adequate evidence.
