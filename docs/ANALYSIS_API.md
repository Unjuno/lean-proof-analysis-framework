# Scientific analysis API — v0.3

LPAF provides a reusable Python library and a CLI for measuring Lean declaration
corpora. The six analysis operations examine reference graphs and exported
expression structure. People, scripts, notebooks, and LLM tool adapters call the
same functions. No model, API key, hosted service, or MCP server is required.

This document specifies the implemented v0.3 interface. Structural measurements
describe the recorded corpus; they do not establish proof correctness,
definitional equality, theorem equivalence, or mathematical difficulty. The
older source-reading API remains documented in [READING_API.md](READING_API.md).

## 1. Install and run a first analysis

Python 3.10 or newer is required. The Python package has no third-party runtime
dependencies. Lean is needed for an elaborated export, but subsequent import and
analysis use Python and SQLite without starting Lean.

```sh
python -m pip install -e .

lpaf export ./my-lean-project --out work/corpus.jsonl \
  --module MyProject.Main --prefix MyProject \
  --max-declarations 1000 --max-nodes 100000 --timeout 300 --json

lpaf corpus import work/corpus.jsonl --db work/corpus.sqlite --json
lpaf corpus info work/corpus.sqlite --json

lpaf graph work/corpus.sqlite --role value --kind theorem --json
lpaf terms work/corpus.sqlite --field value --kind theorem --json
lpaf patterns work/corpus.sqlite --field value --kind theorem \
  --min-nodes 3 --min-declarations 2 --limit 20 --json
```

Replace `./my-lean-project`, `MyProject.Main`, and `MyProject` with an existing
project, a compiled module, and the intended declaration namespace. Prepare its
toolchain and compiled dependencies before exporting. Export and database paths
must be new: these commands do not overwrite existing artifacts.

Scientific commands print the library result as JSON. Without `--json`, success
output is indented JSON; with it, success output is compact and failures also
have a JSON envelope. A handled error exits with status 2. A successfully
reported coverage limit, such as `selection_complete: false` or a dominator
`work_limit`, is data in a successful result, not a process failure.

## 2. Export elaborated Lean data

```python
from lean_proof_analysis import export_lean

descriptor = export_lean(
    "./my-lean-project",
    "work/corpus.jsonl",
    modules=["MyProject.Main"],
    prefixes=["MyProject"],
    names=[],
    runner=("lake", "env", "lean"),
    max_declarations=1000,
    max_nodes=100000,
    timeout=300,
    lean_path=None,
)
```

### Project and runner contract

The project directory must contain a nonempty UTF-8 `lean-toolchain` file. The
default command is `lake env lean --run <bundled-exporter> ...`, run with the
project as its working directory. LPAF does not invoke a build or implement a
toolchain installer. An externally configured runner or toolchain manager can
have its own behavior; use an already prepared environment for a reproducible
run. Loading Lean modules executes their initializers, so export is an explicit
execution operation, separate from importing a saved corpus.

The bundled exporter and fixture are developed against the version pinned in
[`lean/lean-toolchain`](../lean/lean-toolchain). A different project's pin must be
used as that project's pin; exporter compatibility with a different Lean
release is not inferred from a successful run on the bundled fixture.

`modules` must be a nonempty iterable of module-name strings. `prefixes` and
`names` are optional iterables, not single strings. Modules are imported first;
selection applies to declarations in that imported environment, including
transitively imported declarations. A prefix matches the name itself or a
dot-separated descendant. Exact-name and prefix selectors form a union. With
neither selector, all declarations in the imported environment are candidates.
Candidates are sorted by name before the declaration limit is applied.
An empty matching selection is valid; inspect the emitted count rather than
assuming that a requested name existed.

Importing a module does not restrict results to declarations originally defined
in that module. Use the recorded origin `module` and a corpus view when that is
the population you need.

The CLI supports a single explicit Lean binary and an optional child-process
search path:

```sh
lpaf export ./my-lean-project --out work/selected.jsonl \
  --module MyProject.Main --module MyProject.Other \
  --prefix MyProject.Algebra --name MyProject.mainTheorem \
  --lean /absolute/path/to/lean \
  --lean-path /absolute/path/to/compiled/modules --json
```

`--lean` replaces the default runner with that binary. The Python `runner`
parameter additionally accepts an argument vector for a prepared wrapper.
An absolute executable's directory is added to the child's `PATH`;
`lean_path` overrides the child's `LEAN_PATH` with one path. It is not a list of
search paths. LPAF passes arguments without a shell and does not change the
parent process environment.

### Limits, publication, and provenance

`max_declarations` bounds the selected declaration records. A valid export that
reaches this bound can report `selection_complete: false`; its footer also
records the number of matching declarations. `max_nodes` separately limits each
serialized type or value expression. An over-limit expression is recorded as
`null` with status `node_limit`. Its direct constant references are still
collected from the full expression. Thus complete declaration selection does
not imply that every selected expression was serialized.

`timeout` limits the exporter process wait, in seconds. On POSIX, timeout cleanup
kills its process group; elsewhere only leader cleanup is guaranteed. This is
not an end-to-end wall-time limit on provenance collection, validation, and file
publication. Stdout and stderr are spooled to temporary files. There is no
whole-process RAM or total spool-size limit.

The output is published at its new path only after the process exits
successfully and the JSONL transport passes validation. Validation checks the
header, requested selection, declaration identities and DAGs, limits, and final
footer. An interrupted stream without a footer is rejected. A failed run does
not publish its temporary output.

The export descriptor has schema `lpaf-export-v0.1`, output path, output SHA-256,
declaration count, selection completeness, limits, and provenance. Provenance
also goes into the JSONL header and includes:

- The `lean-toolchain` text and SHA-256, and the actual exporter-reported Lean
  version. Recognized version pins must match; an unparsed tag is explicitly
  reported as `unparsed_toolchain_tag`.
- The optional `lake-manifest.json` SHA-256 and the bundled exporter SHA-256.
- Git HEAD and dirty state before export, when those can be obtained.
- `compiled_artifact_authentication: "not_performed"`.

The toolchain and manifest hashes are checked again after the process. These
records do not constitute a hash inventory of every source or compiled artifact.
The exporter does not supply source line ranges; exported `source_url` is null.

## 3. Import, inspect, and select a corpus

### Import functions

```python
from lean_proof_analysis import (
    import_corpus, import_source_report, open_corpus,
)

# Each import returns an open, read-only ProofCorpus. Use its context manager.
with import_corpus(
    "work/corpus.jsonl",
    "work/corpus.sqlite",
    max_record_bytes=64 * 1024 * 1024,
    max_expression_nodes=1_000_000,
) as corpus:
    print(corpus.metadata["declarations"])

# Alternative input: an existing LPAF source-only analysis.json report.
with import_source_report(
    "reports/latest/analysis.json", "work/source-corpus.sqlite"
) as corpus:
    print(corpus.metadata["limitations"])

# Later sessions reopen the database without executing Lean.
with open_corpus("work/corpus.sqlite") as corpus:
    for declaration in corpus.iter_declarations():
        print(declaration["id"], declaration["kind"], declaration.get("module"))
```

The two import examples are alternative data sources, not a merge operation.
The source-report CLI equivalent is:

```sh
lpaf corpus import reports/latest/analysis.json \
  --format source --db work/source-corpus.sqlite --json
```

`import_corpus` reads one UTF-8 JSONL record at a time into a temporary SQLite
database. It requires schema `lpaf-corpus-v0.1`, a header, a footer with a matching
record count, and a Boolean selection-completeness flag. It validates transport
structure and rejects duplicate declaration IDs, duplicate JSON keys,
non-finite JSON numbers, malformed expressions, and contradictory availability
statuses. The completed database is installed atomically without replacing an
existing destination. Its store schema is `lpaf-sqlite-v0.1`.

`import_source_report` loads the existing source report into memory. It imports
recorded declarations and lexical candidate edges; it does not synthesize Lean
expressions. Source `statement` references become role `type`; `body` references
become role `value`. Here `type` means source statement tokens, not an elaborated
Lean type. All expressions remain unavailable. Its `selection_complete: true`
means all candidates recorded in that report were imported, not that all source
declarations or semantic dependencies were recovered.

Both importers record their input SHA-256. Reference records are deduplicated by
source, target, role, and evidence. References to declarations absent from the
database are retained.

### Read-only handles and views

`ProofCorpus` exposes `metadata`, `iter_declarations(include_expressions=False)`,
`get_declaration(selector, include_expressions=True)`,
`iter_references(role="all")`, `select(...)`, and `close()`. Metadata is returned
as a copy. Declaration iteration is ordered by ID. Leaving expressions out is
useful when inspecting the inventory without loading DAGs.

Selectors resolve an exact ID first, then a unique full name. Unknown selectors
and ambiguous full names raise errors; there is no short-name guessing. Resolve
an ID from the selected inventory before storing an analysis request.

```python
from lean_proof_analysis import open_corpus, profile_terms, analyze_dependencies

with open_corpus("work/corpus.sqlite") as corpus:
    selected = corpus.select(
        kinds=["theorem"],
        modules=["MyProject.Main"],
        name_prefix="MyProject",
    )
    term_result = profile_terms(selected, field="value")
    graph_result = analyze_dependencies(selected, role="value")
    print(selected.metadata["view"])
```

`select` returns a `CorpusView` accepted by all six analyzers. The view shares the
parent's read-only connection; use it inside the parent's context. It is not a
separate database or an independently managed context manager.

Kinds and modules must be lists, tuples, sets, or frozen sets of nonempty exact
strings. Values within either filter are alternatives; different filter fields
are combined. `None` means no restriction, while an empty collection selects no
declarations. `name_prefix` matches the exact name or its dot descendants: `Foo`
includes `Foo.bar` but excludes `Foobar`. A module filter matches the recorded
origin module exactly. For the source-report adapter, that module is derived
from the source path.

Views filter declaration **sources** and retain their outgoing references to
excluded or absent targets. Those targets become graph boundary records; their
outgoing adjacency is unavailable to that analysis. View metadata records the
filters, selected counts, unfiltered counts, and this reference policy. The
original export metadata remains intact.

There is no automatic detection or removal of generated code. In particular,
value expressions include function definitions, generated auxiliaries, and
theorem proofs. A theorem-kind filter is an explicit population choice, not a
claim to identify every proposition-valued declaration.

The six analysis commands accept the same filters:

```sh
lpaf terms work/corpus.sqlite --kind theorem \
  --module MyProject.Main --module MyProject.Other --prefix MyProject --json
```

`--kind` and analysis `--module` are repeatable. Analysis `--prefix` is a single
namespace prefix. Export `--module` instead names modules to load, and export
`--prefix` is repeatable; these are distinct stages of selection.

## 4. Fields, references, evidence, and expressions

| Concept | Meaning | Values and scope |
| --- | --- | --- |
| `field` | Which expression the term tools measure | `type` or `value`; default `value` |
| `role` | Which recorded direct-reference edges the graph tools use | `type`, `value`, or `all`; default `all` |
| `type_expr` | Elaborated declaration type | Complete DAG or null with an availability status |
| `value_expr` | Elaborated declaration body when one exists and is available | Complete DAG or null; theorem and opaque bodies are requested by the exporter |
| `lean_elaborated` | Extractor-supplied evidence for Lean expression/reference data | Stored evidence label; not an independent certificate of correctness or artifact authenticity |
| `lexical_candidate` | Source text supplied a candidate reference | Does not establish Lean name resolution or a semantic dependency |

Graph direction is always **declaration consumer → referenced declaration**.
References are occurrences of constants collected from each expression, stored
as sets of targets for each role. With `role="all"`, the graph unions both
roles' edges within each evidence layer; an edge present in both roles counts
once as a unique graph edge. The separate reference-record counts preserve the
role distinction. Evidence layers are never combined into one inferred graph.

Expressions use a postorder DAG: each node has a `tag`, a list of string `data`,
and ordered `children` indices strictly earlier than the node. The object has a
valid `root` index and `truncated: false`. For example, one natural literal can
be transported as:

```json
{
  "nodes": [{"tag": "lit", "data": ["nat", "7"], "children": []}],
  "root": 0,
  "truncated": false
}
```

The supported constructors are `bvar`, `fvar`, `mvar`, `sort`, `const`, `app`,
`lam`, `forallE`, `letE`, `lit`, `mdata`, and `proj`. Bound-variable indices use
de Bruijn indices. Universes, literals, binder information, let flags,
projections, and metadata are retained in the exported payload. Optional
`binder_name` is descriptive. Transport validation checks the representation;
it does not type-check a term.

Availability has four stored states:

| Status | Interpretation | Term analysis behavior |
| --- | --- | --- |
| `available` | A complete expression DAG was recorded | Analyze it |
| `node_limit` | The export node budget prevented serialization | Count as missing coverage; do not substitute an empty term |
| `no_value` | This declaration has no value expression | Allowed only for `value`; not a failed proof |
| `unavailable` | No expression was supplied | Count as unavailable; typical for source reports |

For custom corpus adapters, the term tools also report and skip a supplied
`truncated: true` object as `truncated_expression`. The SQLite importer requires
complete DAGs for `available` expressions and rejects such partial objects.

## 5. The six analysis operations

All functions below are importable from `lean_proof_analysis`. Their `corpus`
argument accepts an open `ProofCorpus` or its `CorpusView`.

### 5.1 Reference graph profile

```python
analyze_dependencies(corpus, *, role="all", roots=(), top_k=20)
```

Per evidence layer, this returns declaration and edge counts, degree
distributions, weak and strong components, cyclic components, condensation
depth, most-referenced targets, and coupling between known origin modules.
Optional roots add reachable internal counts and observed outside targets.

The node inventory contains every selected declaration, including isolates, in
each evidence layer. Components, internal degree, and condensation depth use
only the induced graph on that inventory. Outside targets have unknown outgoing
adjacency; they are not assumed to be complete leaves. Condensation depth counts
component transitions to an observed internal sink, with depth zero at a sink.
Cycles and self-loops are recorded graph structure, not proof-error findings.

Most-referenced targets can be internal or outside the inventory. Their count is
the number of distinct selected consumers. Module coupling counts known
source/target module pairs, including pairs within the same module; edges with
unknown module information are reported separately. `top_k` bounds examples and
ranked lists, while histograms and aggregate counts retain their full scope.

### 5.2 Direct dependency overlap

```python
dependency_overlap(corpus, left, right, *, role="all", limit=100)
```

This compares the two declarations' **direct** recorded target sets, separately
by evidence layer. Results include shared, left-only, and right-only counts and
bounded target lists; outside targets participate. The Jaccard score is the
fraction of union targets shared by both declarations. It is null when both
sets are empty, with `empty_union: true`. The operation does not compute
transitive assumption sets or infer common proof methods.

### 5.3 Dependency bottlenecks

```python
dependency_bottlenecks(
    corpus, root, *, role="all", top_k=20, max_work=2_000_000
)
```

This computes dominators in the root-reachable internal graph. A dominator lies
on every recorded directed path from the selected root to a node it dominates.
The ranking excludes the root, and each `dominated_nodes` count includes the
ranked node itself. This is a property of recorded paths within the selected
scope, not a claim that a lemma is mathematically indispensable.

Each evidence layer has `status: "complete"` or `status: "work_limit"`.
If the work budget is exhausted, the tool returns no partial dominance ranking.
`computation` reports work, passes, and completeness. `max_work` applies to the
dominator iteration, not initial corpus loading, all traversals, elapsed time,
or memory.

### 5.4 Expression profile

```python
profile_terms(corpus, *, field="value", top_k=20, count_cap=10**12)
```

This reports available-expression counts, serialized-node totals, reachable DAG
node totals, expanded occurrence totals, constructor histograms, size/depth
minima, maxima, and means, and a bounded list of the largest expressions.
`largest_expressions` is ranked by reachable DAG nodes descending, then ID
descending. Missing or capped expressions are excluded from numerical means and
remain visible in coverage. Empty populations have null minima, maxima, and
means, rather than a measured size of zero.

Serialized-node count and reachable-node count differ when an input contains
orphan node records. Reachable nodes count each stored node once. Expanded
occurrences count each use as if DAG sharing were expanded into a tree. Depth
counts nodes on the longest root-to-leaf path, so a leaf has depth one. The
implementation uses iterative DAG computations and does not materialize that
potentially enormous expanded tree.

### 5.5 Repeated encoded subterms

```python
find_repeated_subterms(
    corpus, *, field="value", min_nodes=3, min_declarations=2,
    limit=20, max_unique_patterns=100000, examples_per_pattern=5,
    count_cap=10**12,
)
```

This indexes ordered structural fingerprints of reachable subterms. It returns
patterns meeting the minimum expanded size and distinct-declaration support,
with root previews, sizes, context flags, and bounded examples identifying the
declaration, field, and node index. Use that location with
`get_declaration(..., include_expressions=True)` to inspect the complete DAG.

A declaration contributes at most one to `declaration_support` for a pattern.
`serialized_root_count` counts stored root nodes representing that pattern;
`expanded_occurrences` additionally accounts for DAG reuse. Occurrences and
different patterns can overlap or nest. These counts are not additive storage
savings or a minimum-description-length estimate.

Ranking is by declaration support descending, capped expanded size descending,
then fingerprint ascending. `max_unique_patterns` bounds the global retained
fingerprint index. Once it fills, already admitted patterns continue receiving
counts from later declarations; new patterns are omitted. The retained set is
therefore sensitive to corpus iteration order when capped, though deterministic
for the SQLite ID order. `pattern_index_complete` and
`omitted_new_pattern_observations` expose this limitation. The latter counts
omitted observations, not distinct omitted patterns. `qualifying_patterns`
counts only the retained qualifying patterns; `output_truncated` separately
indicates a short returned list.

### 5.6 Compare two expression structures

```python
compare_term_structure(
    corpus, left, right, *, field="value", count_cap=10**12, max_path=256
)
```

This compares root fingerprints and reports `same_encoded_structure` or
`different_encoded_structure`, with the Boolean `same_structure`. If either
expression is unavailable, the relation is `unavailable` and the Boolean is
null. The selected `ProofCorpus` or view resolves each exact ID or unique full
name; exact IDs are preferable for saved requests.

For different structures, `first_difference` follows the first ordered child
with a differing fingerprint until a local payload differs. It includes the
two node indices, bounded node previews, and a bounded child path. `max_path`
caps only the displayed path; its actual length and truncation flag remain
available. Comparison does not attempt an edit distance, anti-unification,
definition unfolding, or a mathematical equivalence proof.

### Calling all six from Python and CLI

```python
from lean_proof_analysis import (
    open_corpus, analyze_dependencies, dependency_overlap,
    dependency_bottlenecks, profile_terms, find_repeated_subterms,
    compare_term_structure,
)

with open_corpus("work/corpus.sqlite") as corpus:
    selected = corpus.select(kinds=["theorem"])
    graph = analyze_dependencies(selected, role="value")
    terms = profile_terms(selected, field="value")
    patterns = find_repeated_subterms(selected, field="value")

    # Inspect this inventory before choosing scientifically relevant comparisons.
    ids = [record["id"] for record in selected.iter_declarations()]
    if len(ids) >= 2:
        left, right = ids[:2]
        overlap = dependency_overlap(selected, left, right, role="value")
        bottlenecks = dependency_bottlenecks(selected, left, role="value")
        comparison = compare_term_structure(selected, left, right, field="value")
```

For the CLI equivalents, replace the example selectors with full names or IDs
from your selected inventory:

```sh
lpaf graph work/corpus.sqlite --role value --root MyProject.mainTheorem --top-k 20 --json
lpaf overlap work/corpus.sqlite MyProject.theoremA MyProject.theoremB --role value --limit 100 --json
lpaf bottlenecks work/corpus.sqlite MyProject.mainTheorem --role value --max-work 2000000 --json
lpaf terms work/corpus.sqlite --field value --top-k 20 --json
lpaf patterns work/corpus.sqlite --field value --min-nodes 3 --min-declarations 2 --limit 20 --json
lpaf term-compare work/corpus.sqlite MyProject.theoremA MyProject.theoremB --field value --json
```

The `count_cap`, `examples_per_pattern`, and `max_path` controls are Python API
parameters in v0.3. Their default behavior applies in the CLI.

## 6. Fingerprints, context, and count interpretation

Structural SHA-256 fingerprints omit **only binder display names**. They preserve
constructor tags, ordered children, bound-variable indices, binder information,
constant names, universe encodings, literal types and values, and other encoded
payload. Renaming a lambda's display binder while retaining the same binding
structure does not change the fingerprint. Changing a bound-variable index,
literal string, universe encoding, or argument order does. Different DAG
sharing layouts can have the same fingerprint because it describes the
expanded encoded structure. There is no definition unfolding or reduction.

Fingerprint matches are structural comparison evidence, not collision-free
formal certificates. In particular, identical open subterms from different
contexts are not thereby interchangeable. The tools report:

- `required_context_binders`: enclosing binders required for loose bound
  variables, accounting for binders introduced inside the subterm.
- `contains_fvar` and `contains_mvar`: whether free variables or metavariables
  occur anywhere in the subterm.
- `requires_expression_context`: whether any of those three conditions applies.

Even when the last flag is false, constants and universe parameters still need
their environment. None of these flags asserts that a subterm is a standalone
well-typed theorem.

Expanded counts use an explicit saturation object, for example:

```json
{"value": 1000, "exact": false, "cap": 1000, "interpretation": "lower_bound"}
```

Here the count is at least 1000; 1000 is not a recovered exact total. An exact
count that happens to equal the cap remains `exact: true`. Reachable DAG-node
counts, declaration support, and ordinary graph counts are separate integer
counts over the recorded population. Exactness within that population does not
claim coverage of omitted declarations or expressions.

## 7. Result and error contract

Each analytic result has these common fields:

| Field | Contract |
| --- | --- |
| `schema` | `lpaf-analysis-v0.1`; distinct from package version `0.3.0` |
| `operation` | Public function name |
| `algorithm` | Versioned identifier of the implemented computation |
| `options` | Effective parameters affecting that computation |
| `provenance` | Copy of corpus metadata, including view filters when used |
| `coverage` | Scope, evidence, availability, and relevant completeness information |
| `data` | Operation-specific measurements and bounded examples |

Graph results additionally expose `not_proof_check: true`; term results expose
`coverage.proof_correctness_assessed: false`, and stored corpus provenance also
carries `not_proof_check`. Consumers should inspect the documented fields rather
than assume all envelopes have an identical set of extra keys.

Graph `data.layers` separates `lean_elaborated` and `lexical_candidate`
measurements. With no usable evidence label in an empty inventory an
`unspecified` layer can appear. Coverage states the edge direction and that
outside-target adjacency is unknown. Term coverage counts declarations seen,
expression statuses, and evidence labels. `all_selected_expressions_available`
is not a claim that the original export selected the entire project. Always
inspect the original `provenance.selection_complete` as well.

`CorpusError` and `ExportError` provide `code`, `details`, and `as_dict()`;
`ExportError` inherits from `CorpusError`. `TermAnalysisError` has the same
structured interface. All are `ValueError` subclasses. Graph argument and
selection errors are plain `ValueError`. File and database failures may also
raise `OSError` or `sqlite3.Error` at the Python boundary.

Typical structured codes include `invalid_argument`, `declaration_not_found`,
`ambiguous_selector`, `destination_exists`, `invalid_expression`,
`incomplete_export`, `record_limit`, `toolchain_mismatch`,
`export_process_failed`, and `export_timeout`. The CLI converts handled failures
into this shape when `--json` is supplied:

```json
{
  "schema": "lpaf-analysis-v0.1",
  "error": {
    "code": "declaration_not_found",
    "message": "Declaration is outside this corpus",
    "details": {"selector": "Missing.declaration"}
  }
}
```

Plain graph `ValueError` failures are currently labeled `invalid_input` by the
CLI, not a more specific graph error code. Argument-parser errors use
`invalid_arguments`. Check the `error` object and process status before treating
output as measurements. An unavailable expression, empty overlap, capped
pattern index, or work-limit result must retain its coverage/status information
when passed to an LLM or summarized for a person.

## 8. Parameters and metric units

All counts below are dimensionless quantities of explicitly named objects.
Seconds apply only to the exporter process timeout; byte limits apply to the
UTF-8 transport. Graph depth counts component transitions, whereas expression
depth counts nodes, so those two depth measurements must not be combined.

| Parameter | Meaning | Type | Unit | Default and accepted range |
| --- | --- | --- | --- | --- |
| `max_declarations` | Maximum declarations emitted by export | Integer | Declarations | 1000; at least 1 |
| Export `max_nodes` | Maximum serialized nodes per expression | Integer | DAG nodes | 100000; at least 1 |
| `timeout` | Exporter process wait budget | Finite number, excluding Boolean | Seconds | 300; strictly positive |
| `max_record_bytes` | Import byte budget for one JSONL line | Integer | Bytes | 67108864; at least 1; exporter validation uses the same fixed default |
| `max_expression_nodes` | Import validator's maximum nodes per available expression | Integer | DAG nodes | 1000000; at least 1 |
| `top_k` | Returned ranking/example cap | Integer | Result entries | 20; 1 through 1000 |
| `roots` | Optional roots for graph profile | Iterable of selectors, or one selector string | Declarations | Empty; at most 16 requested roots |
| Overlap `limit` | Maximum targets in each shared/left/right list | Integer | Targets per list | 100; 1 through 1000 |
| `max_work` | Dominator iteration work budget per evidence layer | Integer | Instrumented work steps | 2000000; at least 1 |
| `min_nodes` | Minimum expanded size of indexed subterms | Integer | Expanded nodes | 3; 1 through `count_cap` |
| `min_declarations` | Minimum pattern support | Integer | Distinct declarations | 2; at least 1 |
| Pattern `limit` | Maximum returned qualifying patterns | Integer | Patterns | 20; 1 through 1000 |
| `max_unique_patterns` | Global retained pattern-index capacity | Integer | Fingerprints | 100000; 1 through 1000000 |
| `examples_per_pattern` | Stored example locations per pattern | Integer | Declarations | 5; 1 through 100; Python only |
| `count_cap` | Saturation bound for expanded counts | Integer | Occurrences or expanded nodes | 1000000000000; 1 through 1000000000000000000; Python only |
| `max_path` | Maximum displayed mismatch path length | Integer | Child transitions | 256; 0 through 10000; Python only |

| Metric | Meaning | Type and unit | Scope and range |
| --- | --- | --- | --- |
| `nodes` | Selected declaration inventory per graph layer | Nonnegative integer; declarations | Includes isolates |
| `reference_records` | Stored selected reference records | Nonnegative integer; records | Roles retained separately |
| `unique_edges` | Distinct source/target pairs in one graph layer | Nonnegative integer; edges | Roles collapsed when selecting `all` |
| `incoming_internal` / `outgoing_internal` | Degree within selected inventory | Distribution of nonnegative counts; edges per declaration | Includes zero-degree declarations |
| `outgoing_boundary` | Selected sources' references outside inventory | Distribution of nonnegative counts; edges per declaration | Outside adjacency unknown |
| `depth_to_internal_sink` | Longest condensation path to an observed internal sink | Distribution of nonnegative integers; component transitions | Internal graph only; sink depth zero |
| `jaccard` | Shared direct targets as a fraction of the union | Number from 0 through 1, or null; dimensionless | Null for empty union |
| `dominated_nodes` | Nodes dominated by a ranked node | Positive integer; declarations | Includes itself; root excluded from ranking |
| `reachable_dag_nodes` | Stored expression nodes reachable from the root | Positive integer; DAG nodes | No repeated counting for shared uses |
| `expanded_occurrences` | Occurrences after conceptual DAG expansion | Count object; occurrences | Exact or explicitly lower-bound |
| Expression `depth` | Longest root-to-leaf node count | Positive integer; nodes | Leaf depth one; means can be non-integers |
| `declaration_support` | Declarations containing a retained pattern | Positive integer; declarations | Each available selected declaration contributes at most one |
| `serialized_root_count` | Reachable serialized nodes having a pattern fingerprint | Positive integer; DAG root nodes | Counts repeated encodings separately |
| `required_context_binders` | External binder depth needed by a subterm | Nonnegative integer; binders | Zero does not rule out free variables or metavariables |

## 9. Working-set and interpretation boundaries

SQLite keeps the persisted corpus on disk; it does not make every algorithm an
out-of-core algorithm. JSONL import holds one declaration record at a time.
Source-report import loads the source report. Graph analyzers load the selected
declaration metadata and reference edges into memory, and may construct
additional adjacency/component structures. Their `top_k` and `limit` parameters
bound returned lists, not the graph loaded. Histograms are not truncated.

Term profiling streams declarations but holds and analyzes each expression DAG
in memory. Repeated-subterm analysis additionally retains the bounded global
fingerprint index and a per-expression local index; `max_unique_patterns` is not
a hard byte limit. Comparison holds both selected expressions. Iterative
traversals avoid recursion-depth limits and explicit exponential expansion, but
large expressions and input payloads still consume resources.

Lean itself holds its imported environment, and the exporter sorts matching
names before emitting records. Reducing `max_declarations` does not reduce the
imported Lean environment to that number of declarations. For a new large
project, first choose modules and namespace scope deliberately, inspect the
export footer and term availability, then use corpus filters for the intended
comparison population. Preserve those choices with every result.

These tools support program-analysis questions about structure, graph-analysis
questions about recorded dependencies, and mathematical-library studies of
repeated encoded terms. They do not currently identify semantic proof strategies,
compute a verified minimal basis of lemmas, or produce calibrated measures of
human reading time. Such claims require an additional definition and validation
beyond the measurements documented here.

## Implementation references

- [Corpus storage, validation, and views](../src/lean_proof_analysis/corpus.py)
- [Pinned-project export wrapper](../src/lean_proof_analysis/extraction.py)
- [Bundled Lean exporter](../src/lean_proof_analysis/lean/Export.lean)
- [Graph analyses](../src/lean_proof_analysis/graph_analysis.py)
- [Term analyses](../src/lean_proof_analysis/term_analysis.py)
- [Scientific CLI arguments and dispatch](../src/lean_proof_analysis/analysis_cli.py)
- [CLI result/error rendering](../src/lean_proof_analysis/cli.py)
