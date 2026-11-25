# Roadmap

Prioritize reproducible analysis of Lean proof corpora, explicit evidence, and useful corpus questions. Reading/navigation is one application; adding more algorithm names alone is not the goal.

## Delivered foundation: source analysis and reading

- [x] Public Unlicense repository, installable Python library, CLI, and machine-readable results.
- [x] Text-only source analysis with provenance, complete-manifest checks, and a pinned 10-file RH pilot.
- [x] Search, inspection, captured-text comparison, bounded candidate-reference slices, and stored similarity retrieval.
- [x] Shared reading API/CLI, full captured source fields, and explicit legacy/truncation behavior.

The [reading API](READING_API.md) and [reading validation](READING_VALIDATION.md) remain the record for this subset.

## Delivered v0.3: scientific analysis baseline

- [x] Actual Lean environment/`Expr` exporter for built modules, tested with Lean 4.33.1.
- [x] Explicit execution wrapper using the project's toolchain, output validation, time limits, and new-file publication.
- [x] Versioned JSONL and SQLite corpus formats, per-field expression availability, provenance, and read-only queries.
- [x] Separate type/value references, retained outside targets, and independent evidence layers.
- [x] Kind/module/namespace views shared by all six analyses.
- [x] Graph degrees, connectivity, condensation depth, selected-root reachability, and module coupling.
- [x] Direct-reference overlap and budgeted graph dominators.
- [x] Expression DAG profiling, bounded repeated-subterm mining, and pairwise encoded-structure comparison.
- [x] Shared Python/CLI operations with deterministic fixtures and optional native Lean integration checks.

These checkmarks describe implementations, not universal compatibility, mathematical correctness, or measured human benefit. See [analysis validation](ANALYSIS_VALIDATION.md) for what was actually executed.

## Next: extraction fidelity and corpus scope

- [ ] Test a declared compatibility matrix beyond Lean 4.33.1, preserving each target project's own pin.
- [ ] Join semantic declarations to validated source locations without fabricating line anchors.
- [ ] Distinguish generated auxiliaries/equation theorems from authored declarations using explicit, validated metadata.
- [ ] Measure extraction coverage against a manually checked sample, including namespaces, opaque values, inductive declarations, and boundary references.
- [ ] Run elaborated extraction on a pinned RH project environment and an unrelated Lean project. The existing RH pilot is source-only.
- [ ] Record reproducible build/artifact provenance beyond the current toolchain, manifest hash, and observed Git state.

## Next: scaling and scientific comparisons

- [ ] Benchmark extraction, import, graph analysis, and term analysis separately, recording hardware, versions, sample selection, memory, and repeated-run timings.
- [ ] Add incremental imports/reuse and graph implementations that avoid holding the full working graph in memory where justified by measured bottlenecks.
- [ ] Evaluate sensitivity to declaration-kind/module filters, generated code, expression normalization, and boundary coverage.
- [ ] Add retrieval or grouping methods only with a specified analysis question and a lexical/structural baseline.
- [ ] Evaluate cross-corpus comparisons under matching extraction and selection policies before interpreting metric changes.

## Next: human and agent applications

- [ ] Ground premise/binder cards and selective definition expansion in extracted expressions.
- [ ] Provide navigable representations of repeated structures with representative examples and explicit differences.
- [ ] Evaluate analysis-task accuracy for humans and LLM callers using the same tool results.
- [ ] Run a separate reading/navigation study if claiming reduced human effort; specify tasks, answer keys, baselines, and unresolved cases.
- [ ] Add an optional MCP adapter over the existing API when a concrete client requires it.

## Immediate research sequence

1. Reproduce the native fixture and standard-library experiments described in the validation record.
2. Choose one corpus question, for example which repeated subterms remain common after separating definitions, theorems, and generated declarations.
3. Freeze the corpus revision, toolchain, selection, expression field, evidence policy, and analysis limits; record boundary and missing-expression counts.
4. Check representative outputs against the actual exported expressions, then repeat under a relevant alternate selection.
5. Replicate on an unrelated project before making a general claim. Evaluate human or model performance separately from structural measurements.

The framework currently supports these experiments; their scientific conclusions and practical benefits still require evidence.
