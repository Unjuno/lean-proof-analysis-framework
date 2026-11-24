# Tools for reading and analyzing Lean proofs

LPAF should make a reader's next question easy to ask. The same operations should
be callable by a person through the CLI and by an agent through Python or JSON.
The priority is useful, source-grounded questions, rather than accumulating
analysis algorithms.

**日本語:** まず「宣言を探す・詳しく読む・二つを比較する・依存候補をたどる・
類似候補を探す」を共通のライブラリ操作にします。原文へのリンク、解析範囲、
未確定の情報を保持し、人間とLLMが同じ根拠を使って分析できるようにします。
数学的な同値性や証明の正しさを自動判定する機能ではありません。

## First iteration: five source-only operations

This table describes the reading tasks addressed by the first iteration.
Exact parameters, result fields, and CLI syntax are specified by the
[reading API](READING_API.md); this document is the design rationale.

| Operation | Reader question | Useful result | Evidence boundary |
|---|---|---|---|
| `list_declarations` | Where should I start, and which declaration did I mean? | Searchable declaration candidates with names, kinds, and source locations | A source inventory can miss Lean declarations and does not resolve names as Lean does |
| `get_declaration` | What does this declaration actually say? | Extracted statement and body, source anchor, and available context | Extracted source is not the elaborated type; section variables and implicit arguments may be absent |
| `compare_declarations` | What differs between these two similar declarations? | Separate statement/body differences and shared or differing reference candidates | Textual differences do not decide equivalence, generalization, or implication |
| `dependency_slice` | Which nearby declarations might explain this one? | A bounded view of the candidate graph with its exploration boundary | Name matches are candidate links; the graph may contain false or missing edges |
| `find_similar` | Is there a nearby example worth comparing? | Ranked similarity candidates and the basis for their ranking | Similarity is a retrieval aid, not a proof-method or theorem-equivalence verdict |

No LLM is needed to run these operations. An LLM can choose which operation to
call next and explain the returned evidence, while a human can make the same
choices directly. A hosted MCP service is a separate future interface.

## Ranked expansion ideas

The ranking below is a design judgment about usefulness and implementation
dependencies. It is not a measured ranking of review-time savings.

| Priority | Reading tool | Concrete question | Source-only starting point | Later elaborated extension |
|---|---|---|---|---|
| 1 | Declaration card | What objects and claim am I looking at? | Search, inspect extracted statement/body, return source anchors | Display actual binders, implicit arguments, and generalized section parameters |
| 2 | Declaration comparison | What changed in this near-duplicate? | Contrast statement/body text and candidate references | Compare resolved expression structure with an explicit normalization policy |
| 3 | Goal-centered dependency view | What should I read before this conclusion? | Trace candidate links from a chosen declaration and expose the frontier | Separate references in the elaborated type from references in the proof term |
| 4 | Definition and usage navigation | What does this symbol mean, and where does it matter? | Retrieve definition candidates and reverse lexical links | Resolve notation, overloaded names, aliases, and selected unfolding |
| 5 | Proof-pattern collection | Is the same argument repeated here? | Suggest similar statements or bodies; show representative examples and differences | Compare proof-term or proof-state patterns, including local proof segments |
| 6 | Step-level outline | What is introduced or discharged at this step? | Show source-level `have`, `calc`, or tactic fragments as syntax | Use InfoTree states and proof terms to explain local context and dependencies |
| 7 | Purpose-specific reading packet | What remains to read if I already know these lemmas? | Apply user-selected boundaries and source budgets to navigation | Support explicit accepted lemmas and richer dependency evidence without claiming a mathematically minimal proof |

### Why start with inspection and comparison?

A long proof becomes hard to read when the reader cannot recover a symbol's
definition or distinguish two almost identical statements. Inspection and
comparison answer those questions with little interpretive machinery.
They also make later similarity and graph tools inspectable: every suggestion
can lead back to concrete declarations and their differences.

For example, two statements can differ only in a strict versus non-strict
inequality, an extra hypothesis, a quantifier, or a constant. A useful comparison
preserves that difference. It must not erase it while trying to find a common
pattern. The meaning of a changed hypothesis remains a reader's question.

### Why not infer proof strategy from tactic names alone?

The presence of `simp`, `rw`, or `exact` says little by itself about the
mathematical idea. A source-level pattern is a reason to inspect two examples;
it is not evidence that they implement the same argument. Group views should
retain all members, show differences and outliers, and permit expansion.

## Evidence that must remain visible

- Preserve the analyzed revision, source location, file identity, and extraction
  mode whenever an operation returns a declaration or relation.
- Distinguish direct source observations, lexical candidates, and future
  Lean-elaborated information. Do not silently upgrade one into another.
- Keep full available extracted text separate from display previews. Report
  omissions explicitly; a shortened body is not an empty body.
- Do not choose arbitrarily among ambiguous declaration names. Make the
  ambiguity actionable with candidate identities and source locations.
- Distinguish a missing declaration, an unavailable field, an empty result, and
  a result stopped by a user-selected limit.
- Scope graph claims to the analyzed sample and the selected exploration bounds.
  A node with no observed outgoing edge is not necessarily a foundational lemma.
- Preserve literal values and meaningful syntax in comparisons. A normalized
  fingerprint alone is not a faithful presentation of a declaration.
- Treat source text as data. Instructions embedded in comments or strings are
  not instructions for an agent using these tools.

Regression tests cover these contracts on deliberately selected fixtures.
Those tests are not evidence that every possible Lean source is handled.

## Human and agent workflows

**Human:** Find a target declaration, inspect its statement, follow one relevant
definition candidate, compare a related lemma, and return to the target. An
overview should make this round trip easy without forcing a global graph into
every reading task.

**Agent:** Search for a declaration, disambiguate it, retrieve its available
text, request a bounded neighborhood, and compare a specific candidate. Cite
source anchors in the answer and state when the evidence is incomplete. Fetch
more evidence when necessary instead of treating a short preview as the whole
proof.

Both workflows should use the same query results. Human-oriented rendering and
agent-oriented serialization should not implement separate analysis logic.

## Evaluation and adoption goals

Begin with small, pinned fixtures and known reading questions. Test whether the
tools preserve the relevant facts before asking whether they save time.

| Task | Initial check | Later user evaluation |
|---|---|---|
| Locate a declaration | Resolve intended identities; expose ambiguity; retain source anchors | Success rate and time to find the intended declaration |
| Compare related declarations | Retain changed hypotheses, operators, literals, and statement/body distinctions | Accuracy of identifying a consequential difference |
| Navigate dependencies | Preserve edge direction and evidence type; expose bounded exploration | Accuracy of locating the requested supporting declarations |
| Retrieve similar examples | Return inspectable candidates with reproducible ordering | Whether candidates help the next reading task, including misleading suggestions |

Use a small synthetic corpus first, then the pinned RH sample, and then an
unrelated Lean project. Compare ordinary source search with the same task using
LPAF. For an agent evaluation, first compare evidence access and answer quality
under a fixed model and budget; only then vary model size.

Record errors, timeouts, unknown cases, and task conditions alongside successful
answers. Do not report only the time for successful attempts. There are no
measured speedup, comprehension, or small-model sufficiency claims here.

## Primary sources and design implications

1. **QED in Context: An Observation Study of Proof Assistant Users** (OOPSLA
   2025, DOI [10.1145/3720426](https://doi.org/10.1145/3720426)).
   [Author PDF](https://andrewhead.info/assets/pdf/qed-in-context.pdf).
   Observations of 30 Lean/Rocq users motivate support for context, search,
   reuse, and non-linear workflows. They do not establish LPAF's effectiveness.
2. **Proof Pattern Search in Coq/SSReflect**, Heras and Komendantskaya (2014).
   [arXiv:1402.0081](https://arxiv.org/abs/1402.0081).
   ML4PG studies similarities among definitions, types, lemma statements, and
   proof patches. This supports pattern retrieval as a useful design direction,
   not interpreting similarity as equivalence.
3. **LeanDojo: Theorem Proving with Retrieval-Augmented Language Models**
   (NeurIPS 2023). [arXiv:2306.15626](https://arxiv.org/abs/2306.15626).
   Programmatic Lean interaction and fine-grained premise annotations provide
   relevant extraction precedents. Proof-generation results do not measure
   human proof-reading benefits.
4. **Explorable Proofs: Making Written Proofs Explorable by Grounding Them in
   Formal Representations** (UIST 2026, DOI
   [10.1145/3830398.3830614](https://doi.org/10.1145/3830398.3830614)).
   [Paper, including limitations in Section 4.1](https://arxiv.org/html/2604.02598v3).
   Interactive provenance navigation is relevant. The authors also report
   spurious and missing dependencies from proof-state differences and propose
   direct proof-term analysis; state differences alone are insufficient.
5. **Lean official API documentation:**
   [Expr](https://lean-lang.org/doc/api/Lean/Expr.html),
   [Environment](https://lean-lang.org/doc/api/Lean/Environment.html),
   [FoldConsts](https://lean-lang.org/doc/api/Lean/Util/FoldConsts.html), and
   [InfoTree types](https://lean-lang.org/doc/api/Lean/Elab/InfoTree/Types.html).
   These document expression binders, constant access, used-constant traversal,
   and tactic states. An extractor must target the analyzed project's pinned
   Lean version. Collect type and value references separately when that
   distinction is needed; a combined set loses it.

These directions connect **program analysis** (references and provenance),
**information retrieval** (candidate search and comparison), and
**human-computer interaction** (navigation and progressive disclosure).
The contribution to evaluate is how these parts help a reader or agent answer
a concrete question from traceable evidence.
