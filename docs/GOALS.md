# Goals and non-goals

## Research question

Can reusable, traceable analyses of large Lean proofs reduce the effort required for a human reader to **find premises**, **compare related declarations**, and **navigate proof structure**, without concealing conditions and provenance?

## Target users

1. Mathematicians following an argument to its definitions and references.
2. Lean formalizers inspecting a library and comparing lemmas.
3. LLM/AI agents that call deterministic tools and cite precise extracted evidence.

## Requirements

- A reusable library first, never a case-study-specific script as the only interface.
- Same underlying analysis for people and machines.
- Evidence type attached to all claims: source text vs elaborated Lean fact vs heuristic inference vs human annotation.
- Reproducible analysis with explicit source commit, manifest verification status, input scope, options, and tool version.
- All summarization must link back to an exact source location.
- Unknown dependencies and missing files must remain visible, not silently treated as absent.

## Non-goals

- Deciding whether a proof is mathematically true or false.
- Replacing the Lean kernel or a human mathematical interpretation.
- Treating similarity scores as probabilities of equivalence or validity.
- Claiming that one RH case study establishes broad applicability.

## Deliverables

- Versioned Python package, documented Python API, CLI and machine-readable output.
- Reproducible, pinned RH pilot using upstream sources.
- An elaborated Lean 4 extractor (future release) for actual declaration/type dependencies.
- Comparisons against source-only baselines and human navigation tasks.
- A validated second Lean project to test generalization.
