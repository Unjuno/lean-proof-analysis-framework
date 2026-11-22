# Validation protocol

The framework outputs research navigation aids. Evaluation must not be described as mathematical verification of the analyzed theorem.

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
