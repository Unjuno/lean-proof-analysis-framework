# Validation protocol

LPAF measures recorded Lean declarations, expression structures, and reference
graphs. Evaluation first checks whether those measurements have the stated
meaning. Scientific usefulness, scalability, and reader benefit are separate
questions. No milestone is a correctness verdict on an analyzed proof.

Completed observations are in the [v0.3 analysis record](ANALYSIS_VALIDATION.md).
The [v0.2 reading record](READING_VALIDATION.md) remains a historical record for
the source-navigation subset.

## H — falsifiable hypotheses

1. **Transport and measurement:** In the pinned Lean 4.33.1 fixtures, references,
   literals, binding indices, and expression availability survive import; graph
   and term measurements agree with independently specified cases. The threshold
   is no unexpected mismatch in the versioned regression suite.
2. **Composable analysis:** CLI JSON and Python functions return the same payload
   for the same corpus, selection, and parameters. Filtering declarations keeps
   references to excluded targets visible as a boundary.
3. **Practical usefulness, untested:** Structural patterns and graph summaries
   may help researchers investigate proof corpora. Task-specific experiments
   are required; implementation tests cannot establish this benefit.

These hypotheses concern the tested implementation and environment, without
implying complete extraction for every Lean version.

## T — minimum technical checks

Run the full suite with `LPAF_LEAN` pointing to the pinned compiler. The current
minimum includes real Lean declarations with proof values, an axiom without a
value, binder-label renaming, universe parameters, exact literals, and bounded
exports. Negative cases include interrupted JSONL, malformed expression DAGs,
duplicate identities, existing destinations, process failure, timeout, and
toolchain mismatch.

Graph cases include chains, diamonds, cycles, disconnected nodes, mixed evidence,
excluded targets, and computation limits. Dominators are checked against a
separate vertex-removal oracle on 40 deterministic generated graphs. Deep graph
and term cases cover 2,500 levels. Term cases include DAG sharing, occurrence
counts versus declaration support, binding context, count saturation, and
pattern-index limits. Real inputs include a standard-library corpus and a
separately labeled source-only RH sample.

These are functional cases, not a statistically sampled population. Stop on an
unexplained mismatch before publishing a measurement as valid. Once required
cases pass, further testing needs a specific unresolved risk.

## D — decision rules

| Claim | PASS | FAIL | UNCERTAIN |
|---|---|---|---|
| Transport / functional behavior | Required cases pass; actual Lean cases run | A required case fails, evidence is promoted, or omitted data is hidden | Native cases skipped or a required environment is unavailable |
| Scope-preserving analysis | Counts, boundaries, limits, and layers match their contract | Candidate edges become elaborated facts, or excluded targets disappear | Relevant input coverage is unknown |
| Whole-corpus scalability | A specified corpus completes within a predeclared resource budget | That budget is exceeded | No such measurement has run |
| Human or LLM usefulness | A preregistered task evaluation meets its accuracy and effort thresholds | Thresholds are missed or interpretation errors are systematic | No adequate controlled task data |

The default test invocation may skip native Lean tests. That alone cannot
establish a PASS for extraction; the native CI job enables those tests.

## C — alternative explanations and failure modes

Compiler-generated code can dominate repeated patterns. Basic logical plumbing
can be highly referenced without being mathematically informative. Scope changes
can alter graph depth and centrality while the project stays unchanged. Identical
open subterms can occur under different binding contexts. Short encoded terms
need not express easy arguments. These are reasons to stratify and inspect the
data, rather than reinterpret measurements as mathematical judgments.

For future user studies, hold tasks, corpus, model version, and model budget
fixed while comparing tool access. Compare raw source/search baselines before
attributing benefit to generated explanations. Small-model sufficiency remains
unmeasured.

## U — uncertainty and measurement conditions

Counts are deterministic observations of a recorded representation. Principal
uncertainties are corpus selection, toolchain changes, incomplete export,
generated declarations, normalization, unknown external adjacency, and lexical
mis-resolution. SHA-256 fingerprints are not formal collision-free certificates.
Lower bounds and omitted data must remain explicit.

No combined standard uncertainty or coverage factor is estimated for these
discrete functional checks. Future performance measurements must record hardware,
OS, compiler, corpus revision, batch/parallelism settings, cache conditions,
repetitions, and a distribution such as median and range. One local test duration
is not a performance benchmark.
