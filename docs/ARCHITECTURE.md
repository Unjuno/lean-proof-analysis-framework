# Architecture and evidence model

## Two inputs, shared analysis interfaces

| Input | Extraction and persistence | Available analyses |
|---|---|---|
| Built Lean modules under the target project's toolchain | `export_lean` → versioned JSONL → `import_corpus` → SQLite | Graph and expression analyses |
| Lean source text | `analyze_project` → source report; optionally `import_source_report` → SQLite | Source reading and lexical-candidate graph analyses; no expressions are invented |

The adapters report what was observed. Scientific analyses consume the corpus interface, and the CLI calls those same functions. Reading queries continue to consume saved source reports. A future MCP adapter can wrap these interfaces; no MCP server is included.

## Evidence classes

| Evidence | Meaning | Support |
|---|---|---|
| Source observations | Captured characters, hashes, imports, and heuristic declaration spans | Source scanner; not a full Lean lexer |
| `lexical_candidate` | Source-name reference candidates, including adapted source reports | Implemented; kept separate from elaborated edges |
| `lean_elaborated` | Declarations, expressions, and direct constant references obtained from a loaded Lean environment | Implemented; tested with Lean 4.33.1 |
| Literature annotations and human interpretation | Externally grounded theorem/method links or reviewer explanations | Future annotation layer |

An elaborated reference is an observed constant occurrence in an expression. It does not by itself establish a minimal premise set, transitive axiom inventory, theorem equivalence, or proof correctness. Graph analyses produce a separate result for each reference evidence layer and never silently combine candidate and elaborated edges.

## Semantic extraction

`lpaf export PROJECT` requires the target's `lean-toolchain` and already built modules. Its default runner is `lake env lean`; callers can explicitly supply a Lean binary and module search path. No project build, dependency download, or toolchain installation is initiated. Loading modules is intentional code execution, distinct from the source scanner.

The bundled adapter reads `Environment`, `ConstantInfo`, and `Expr`. It exports declaration identities, kinds, known origin modules, types, available proof/body values, and direct references separated into `type` and `value`. Selection can name exact declarations or namespaces. References to declarations outside that selection are retained. The exporter currently does not provide source line locations: `source_url` is null unless separately supplied by another adapter.

The wrapper records the toolchain value/hash, available dependency-manifest hash and Git state, actual Lean version, and exporter hash. It checks recognized release-version pins against the running compiler; the result records when a toolchain tag cannot be parsed for that check. This metadata does not authenticate compiled artifacts or prove that they were built from a particular clean revision.

Output is published to a new path only after process success and JSONL transport validation. Timeout, malformed output, or a missing footer does not publish a successful artifact. See [the extractor contract](../lean/README.md) and [analysis API](ANALYSIS_API.md).

## Schemas and storage

| Representation | Schema | Purpose |
|---|---|---|
| Export descriptor | `lpaf-export-v0.1` | Output identity, limits, selection completeness, runner provenance |
| Corpus JSONL | `lpaf-corpus-v0.1` | Header, declaration records, mandatory footer |
| SQLite store | `lpaf-sqlite-v0.1` | Indexed declarations, separate expression fields, typed/evidence-labeled references, metadata |
| Scientific results | `lpaf-analysis-v0.1` | Operation, algorithm, options, provenance, coverage, data |
| Source reports | `lean-atlas-v0.2` | Captured text, lexical candidates, links, and source-analysis findings |
| Reading results | `lpaf-reading-v0.1` | Bounded source queries, text comparisons, and candidate graph navigation |

JSONL import validates one declaration record at a time and atomically publishes a new SQLite database. Per-record byte and expression-node limits apply. Existing databases are not overwritten, and opened corpora are read-only. The legacy single-JSON source adapter loads its report into memory.

Expressions are serialized as child-first DAGs. Nodes retain constructor tags, ordered child indices, and encoded data such as constant names, bound-variable indices, universe strings, literals, and binder information. Binder display names are separate. Structural analysis ignores those display names, performs no unfolding or reduction, and does not test Lean definitional equality.

`ProofCorpus.select` returns a lightweight `CorpusView` sharing the open database connection. Kinds and modules are exact matches, with a union within each repeated filter and an intersection across filter categories. A namespace prefix matches itself and descendants separated by a dot. The view filters reference **sources**, preserving references to excluded or absent targets. It records its filters and counts without modifying the stored corpus. A theorem-only view can still contain generated equation theorems.

## Analysis boundaries and resource limits

| Component | Behavior and bound |
|---|---|
| Export | Streams JSONL records, but holds the imported Lean environment and declaration inventory; declaration and per-expression node caps are separate |
| Graph summaries | Load selected declarations/references into memory; iterative graph passes avoid recursive stack limits; component examples and root queries are bounded |
| Overlap | Compares the direct recorded reference sets of two named declarations; result lists have an output cap |
| Bottlenecks | Computes graph dominators in the root-reachable internal graph with a work budget; exhausted budgets do not produce partial dominator claims |
| Term profile | Processes recorded expression DAGs without expanding shared subtrees into an exponentially large tree; occurrence counts can saturate with explicit lower-bound status |
| Repeated subterms | Retains a capped index of structural fingerprints; incomplete indexes and iteration-order effects are reported |
| Term comparison | Compares encoded structure and returns a bounded difference path; missing expressions remain unavailable |

The graph edge direction is consumer → reference. Internal connectivity and condensation depth refer to recorded declarations. Boundary targets are counted separately; their unknown outgoing references are not treated as known empty adjacency. Module coupling and direct-reference rankings must be interpreted within this scope. A cycle is a graph observation, not a proof-flaw diagnosis.

Repeated subterms can overlap, so their occurrence counts cannot be added as independent compression savings. Fingerprint matches describe the recorded structural encoding; they do not identify mathematical strategies or novelty. Type expressions and proof/body expressions are separate fields and should be compared under matching options.

## Completeness has several meanings

- **Transport:** Header, records, and footer must form a valid completed stream. A missing footer is an interrupted export.
- **Declaration selection:** Footer `complete` states whether the selected declaration set was capped. A valid bounded export may have `complete=false`.
- **Expression availability:** Each field is `available`, `node_limit`, `unavailable`, or, for values, `no_value`. A capped expression is omitted in full. Native direct-reference extraction still examines the full expression.
- **Corpus view and graph boundary:** Filtering can remove declarations without removing edges to them. Selection completeness does not imply graph closure.
- **Analysis and display:** Work/index budgets, saturated counts, and output-list caps are distinct from input completeness. Preserve the relevant flags rather than assigning one universal “complete” label.

## Public library boundary

Corpus creation/opening and views live in `corpus.py`; explicit Lean execution lives in `extraction.py`. `graph_analysis.py` provides graph summaries, overlap, and dominators. `term_analysis.py` provides profiles, repeated subterms, and structural comparisons. Public functions are re-exported from `lean_proof_analysis`, and `analysis_cli.py` only adapts arguments/results.

The source API (`analyze_project`, `load_report`) and five reading functions remain public. Their source-report and reading-result schemas are separate from the corpus and scientific-result schemas. See [analysis API](ANALYSIS_API.md) and [reading API](READING_API.md).

## Retained source-reading behavior

Source scanning remains heuristic and text-only. It can miss Lean declarations, notation, macro expansions, enclosing context, and implicit dependencies. Its statement-role references become `type`-role **lexical candidates** when adapted; this is not an elaborated Lean type.

`analysis.json` stores captured statements, bodies, and original source spans. CSV files retain capped previews with truncation columns; Markdown and DOT provide navigation views. A complete captured span is not a complete elaborated theorem type. `imports_outside_sample` means that no corresponding input module was observed, not that a file is missing from the upstream repository.

Reading queries distinguish stored-text completeness from display truncation. `inspect --full-text` removes only the display cap. Legacy `lean-atlas-v0.1` reports lack reliable completeness flags; queries label that state unknown, and comparisons do not claim equality of complete text. Re-analyze the source to recover full fields. Source fingerprints retain internal whitespace after comment masking, so formatting changes can change them.
