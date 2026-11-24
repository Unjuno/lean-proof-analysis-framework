# Validation protocol

The framework outputs research navigation aids. Evaluation must not be described as mathematical verification of the analyzed theorem.

See the [v0.2 reading-tools validation record](READING_VALIDATION.md) for the
completed fixture and pinned-pilot checks.

## H — falsifiable hypothesis

A combined interface (source references + dependency navigation + explicit similarity candidates) helps people find and compare relevant statements with less task time than reading the original Lean files alone, while not reducing answer accuracy. A **30% time reduction** is a *proposed target*, not a measured result.

## T — initial experiment

- Materials: fixed source revision for two Lean projects; one is the RH pilot, the other is unrelated.
- Tasks: locate the declaration for a stated claim; recover its premises and source links; compare two similar statements without losing distinct hypotheses.
- Baselines: raw source navigation; plain text search; graph/retrieval interface.
- Participants: exploratory pilot of 6–8 Lean-literate people (recruitment and task protocol must be reviewed before a confirmatory study).
- Record response accuracy, time, unresolved cases, feedback, errors, model version and command parameters.
- Stop for any systematic missing-hypothesis problem; correct the extractor before further human evaluation.

## D — decision rules

- **PASS for technical milestone:** Tests pass on the pinned fixtures; every declared source file in a manifest is present and hash-matched; all candidate outputs are explicitly labeled non-authoritative.
- **FAIL for technical milestone:** A missing input file passes provenance validation, a source anchor is wrong, or a heuristic is reported as an elaborated fact.
- **UNCERTAIN for human-benefit claim:** Until a controlled experiment has enough observations, randomization/counterbalancing, and pre-registered decision thresholds.

## C — alternatives and ways to fail

- Familiarity with the Lean proof, not the interface, may explain any speedup.
- A condensed view may hide distinct assumptions or introduce false equivalence.
- An agent's natural-language explanation may not reflect the exact formal statement.
- Apparent graph centrality may be an artifact of incomplete source coverage.

## U — uncertainty and limits

Main uncertainties: participant expertise, question difficulty, imbalanced baselines, missing imports, lexical mis-resolution, and generated text variability. Quantitative standard uncertainty and coverage factors are **not yet estimated** because no human task dataset has been collected. Report confidence intervals and uncertainty only after measurements exist.

## Technical tests already possible

- Correct stable output schema, deterministic ordering and provenance hashes.
- Negative tests for missing manifest files and wrong hashes.
- Distinguish differently-valued string literals in source comparisons.
- Explicitly label dependencies and similarity as candidate-only.
- Preserve full captured text and signal every display omission.
- Resolve ambiguous names only through explicit IDs; reject dangling references.
- Compare statement and body independently, retaining operators, numerals and string whitespace.
- Respect forward/reverse graph orientation, cycles, depth/node bounds and frontier reporting.
- Return identical query payloads through the Python API and CLI JSON.
- Preserve unknown text completeness for legacy reports and structured failures for invalid inputs.

## Reading-workflow evaluation sequence

First evaluate declaration lookup, difference identification, and reference
navigation on known fixtures. Evaluate the same source questions with ordinary
search and LPAF before introducing generated explanations. An agent experiment
should hold the model and budget fixed while varying access to the reading tools;
only then compare model sizes on the same evidence and tasks.

The technical regression suite is an implementation check. It does not measure
human comprehension, prove the extraction complete for all Lean syntax, or
establish the proposed time-reduction target. A small pilot is exploratory, and
the human-benefit decision remains UNCERTAIN until an appropriate study exists.
