# Goals and non-goals

## Primary research question

Which reproducible measurements and comparisons help characterize the structure of large Lean proof corpora: their recorded dependencies, expression sizes and shapes, repeated subterms, and variation across declarations and modules?

The framework makes **the proofs and their formal representations the objects of analysis**. Human reading and navigation are downstream applications. A useful measurement need not immediately produce a shorter reading packet; its interpretation must remain tied to the data and extraction method.

## Target users

1. Lean formalizers and library maintainers comparing proof structures and reference relationships.
2. Researchers studying proof corpora, structural repetition, retrieval, or representation choices.
3. Mathematicians following selected arguments to their definitions and references.
4. LLM/AI agents that call the same deterministic tools and cite the resulting evidence.

## Requirements

- A reusable library with independently callable analyses, not only a case-study script or report generator.
- The same underlying operations for Python callers, command-line users, and future agent adapters.
- Evidence labels that distinguish observed source text, lexical candidates, elaborated expressions/references, and human interpretation.
- Reproducible inputs and options: toolchain, corpus hash, available revision/manifest metadata, selected declarations, role/field, limits, and tool version.
- Traceability to declaration/module identities and input artifacts. Retain source locations when available; explicitly report their absence for semantic exports.
- Separate selection completeness, expression availability, graph boundaries, and output limits. Unknown or omitted data must remain visible.
- Explicit computational costs and resource bounds. Disk-backed persistence alone is not evidence of bounded-memory analysis.

## Implemented baseline: v0.3

The scientific pipeline exports actual Lean `ConstantInfo`/`Expr` data from built modules, imports JSONL into a read-only SQLite corpus, selects declaration views, and provides six operations: graph summaries, direct reference overlap, graph dominators, expression profiling, repeated subterms, and pairwise structural comparison. Python and CLI share the implementations. Native extraction is tested with Lean 4.33.1.

Source scanning and the v0.2 reading tools remain useful when a project cannot be elaborated in the current environment. Their lexical candidates can enter the same graph API with their original evidence label; they cannot supply fabricated Lean expressions.

## What success means

| Stage | Required evidence | Current position |
|---|---|---|
| Data extraction | A repeatable export whose selection, references, missing fields, and toolchain are visible | Native fixture and standard-library cases; see [analysis validation](ANALYSIS_VALIDATION.md) |
| Analysis correctness | Defined metrics, hand-checkable fixtures, boundary cases, and Python/CLI agreement | Implemented tests; this concerns the analyses, not proof validity |
| Corpus characterization | Reproducible findings over declared samples, robust to relevant selection and normalization choices | Initial experiments; broader corpus evaluation remains open |
| Practical utility | Accurate answers to specified analysis or reading tasks, with comparison baselines | Human effort and small-model sufficiency have not been measured |
| Generalization | Replication on projects with different proof styles, sizes, and supported toolchains | Open; the RH source pilot alone is insufficient |

## Methods and related disciplines

| Discipline | Contribution to this framework | Interpretation boundary |
|---|---|---|
| Compiler and program analysis | Extracted intermediate expressions, structural hashes, dependency graphs, dominators | An expression property is not automatically a mathematical property |
| Network analysis | Degree distributions, connected components, module coupling, reachability | Results describe the recorded and selected graph |
| Data mining and corpus analysis | Repeated subterms, stratified comparisons, coverage and sampling checks | Frequency is not evidence of novelty, usefulness, or shared mathematical meaning |

Future methods should answer a concrete corpus question and provide a validation baseline. Additional scores alone do not establish a useful research result.

## Non-goals and unestablished claims

- Deciding whether a proof or an RH claim is mathematically true or false, or replacing the Lean kernel.
- Treating structural similarity as definitional equality, theorem equivalence, or a probability of validity.
- Treating graph bottlenecks as logically indispensable lemmas, or frequent syntax as a recognized proof method.
- Claiming universal Lean-version compatibility, complete source locations, or authenticated compiled artifacts.
- Claiming novelty, human review-time improvements, or small-model adequacy before testing those claims.

The [roadmap](ROADMAP.md) separates these existing capabilities from the next extraction, scaling, and evaluation work.
