# Reading API and CLI (v0.2)

The reading functions query a saved `analysis.json`. They are read-only, use the
Python standard library, do not call an LLM or access the network, and do not run
Lean. Python 3.10 or newer is required. The source extractor remains heuristic.

## Public operations

Import these functions from `lean_proof_analysis`:

| Python function | CLI | Purpose |
|---|---|---|
| `list_declarations(report, *, query="", kind=None, offset=0, limit=50)` | `lpaf search REPORT [QUERY]` | Search names, paths and captured statements |
| `get_declaration(report, selector, *, max_chars=12000, include_source=False)` | `lpaf inspect REPORT SELECTOR` | Retrieve captured text and source evidence |
| `compare_declarations(report, left, right, *, max_changes=100, max_chars=12000)` | `lpaf compare REPORT LEFT RIGHT` | Compare statement/body separately and show candidate-reference overlap |
| `dependency_slice(report, selector, *, direction="dependencies", role="all", max_depth=2, max_nodes=50)` | `lpaf slice REPORT SELECTOR` | Follow forward or reverse candidate links with explicit limits |
| `find_similar(report, selector, *, limit=20, offset=0)` | `lpaf similar REPORT SELECTOR` | Page through the stored similarity candidates |

`report` is the object returned by `analyze_project` or `load_report`. Supported
input schemas are `lean-atlas-v0.1` and `lean-atlas-v0.2`. Query results use the
separate schema `lpaf-reading-v0.1`. These versions identify different contracts.

Every CLI operation supports `--json`. Without it, the same result object is
rendered as Markdown. No independent human-only analysis path exists.

## Selection and search

A selector is resolved in this order: exact ID, exact full name, unique short
name. Identity lookup is case-sensitive. Duplicate full names and duplicate
short names return `ambiguous_selector` with candidate IDs and source locations.
At most 50 ambiguity candidates are included, with a total and truncation flag.

`search` uses case-insensitive substring matching on name, path or captured
statement. It does not search bodies and does not perform semantic retrieval.
`--kind` is an exact declaration-kind filter. Results are sorted by path, line,
then ID; `total` and `next_offset` describe pagination.

## Bounds and units

| Parameter | Meaning | Unit | Type and allowed range |
|---|---|---|---|
| `offset` | Skip this many matching records | Record count, dimensionless | Integer, at least 0 |
| `limit` | Maximum records on a search/similarity page | Record count, dimensionless | Integer, 1–1000 |
| `max_chars` | Maximum returned captured text; see per-operation scope below | Unicode code-point count, dimensionless | Positive integer; inspection also accepts `None` |
| `max_changes` | Maximum diff changes per field and references per comparison bucket | Item count, dimensionless | Integer, 1–1000 |
| `max_depth` | Candidate-link hops from the selected declaration | Hop count, dimensionless | Integer, 0–1000 |
| `max_nodes` | Maximum declarations in a graph slice, including the root | Record count, dimensionless | Integer, 1–1000 |
| `direction` | Follow references or their consumers | Not applicable | `dependencies` or `dependents` |
| `role` | Traverse statement references, body references, or both | Not applicable | `statement`, `body`, or `all` |

These limits count records or Unicode code points. They are not SI durations,
byte limits, or LLM token budgets. No runtime or model-cost bound is inferred
from them.

**Inspection:** `max_chars` applies independently to statement, body and optional
source span. `--full-text` passes `None`, removing the character cap. Add
`--source-text` to include the exact captured span, including comments.

**Comparison:** `max_chars` is a total character budget across both sides of
each field's diff. Statement and body each have that budget. `max_changes`
applies to each field independently. Detailed comparison stops before computing
a diff when either field has more than 4000 lines; exact full-text equality or
difference remains available, with `status=skipped_size_limit` when different.
There is no semantic normalization. Text diffs preserve operators, literals and
internal whitespace. Line anchors are relative to the captured field; empty
sides have null endpoints, `line_count=0`, and `insertion_after_line`.

**Slices:** a deterministic breadth-first traversal applies node and depth
bounds. Edges retain their original consumer-to-reference direction even in
reverse traversal. The result includes node depths and one predecessor per
node, making the displayed route traceable. Returned edges are limited to
20 times `max_nodes`; `edges_total` and `edges_truncated` expose that bound.
The frontier records omitted neighbors and the limiting reason. The displayed
frontier is capped at `max_nodes`, with a separate total and truncation flag.

`traversal_complete=true` only means that traversal bounds excluded no neighbor
in the recorded candidate graph. It does not establish semantic completeness,
that all edges were displayed, or a minimal/sufficient set of lemmas to read.

**Similar candidates:** the operation retrieves the saved ranking and does not
rerun or expand it. `search_coverage.exhaustive` is always false. The analyzer's
pair cap and other saved search metadata remain visible.

## Common result contract

Each successful query returns:

- `schema`, `operation`, `mode`, and `not_proof_check`.
- `provenance`: repository, asserted revision, manifest-check flags and file
  records for returned declarations. Hash agreement is with the supplied
  manifest; the manifest's origin is not independently authenticated.
- `coverage`: input schema, source-sample scope, declaration count, and explicit
  lack of enclosing-context and semantic-dependency completeness.
- `data`: the operation-specific results and bounds.

Declaration summaries contain ID, name, kind, path, source line anchors,
`source_url`, `source_file_url`, and the available Git blob hash. Unknown hashes
are null rather than fabricated.

Captured text fields contain `text`, `available`, `available_characters`,
`returned_characters`, `truncated`, and `input_completeness`. The latter is
`complete_capture`, `truncated_input`, or `unknown`. A complete capture refers
to the stored heuristic span, not a complete theorem signature after Lean
elaboration. Section variables and notation may live elsewhere in the file.

Comparison results contain separate `statement` and `body` records, plus
candidate-reference intersections/differences separated by those same roles.
`equal` means exact equality of complete captured text. It is null when input
completeness is unknown. It never means theorem equivalence or implication.

## Errors and recovery

Python raises `ReadingError`, a `ValueError` subclass, with `code`, `details`,
and `as_dict()`. The CLI returns exit code 2 and one JSON error object on stdout
when `--json` is present. Human-readable errors go to stderr.

| Error code | Meaning | Recovery |
|---|---|---|
| `ambiguous_selector` | More than one declaration matches | Select a returned exact ID |
| `declaration_not_found` | No identity match in the sample | Search the inventory or expand the analyzed source scope |
| `invalid_selector` | Blank or non-string selector | Supply a declaration ID/name |
| `invalid_argument` | Reading API bounds or options are invalid | Use the documented domains above |
| `invalid_report` | Required report structure or linked identities are invalid | Regenerate the report; do not guess missing records |
| `unsupported_report` | Unsupported schema or evidence mode | Use a supported source-only report |
| `invalid_arguments` | CLI argument parsing failed | Correct command syntax |
| `invalid_json` / `io_error` | CLI could not read the report | Check the file and its format |
| `invalid_input` | Analyzer rejected input/configuration | Correct the input described in the error |

## Try a mathematical reading task

After installing the repository at the revision being analyzed:

```bash
lpaf analyze examples/reading --out reports/generated/reading \
  --repo Unjuno/lean-proof-analysis-framework \
  --commit "$(git rev-parse HEAD)" --source-prefix examples/reading --json
lpaf search reports/generated/reading/analysis.json positive
lpaf inspect reports/generated/reading/analysis.json Reading.Positive --full-text
lpaf compare reports/generated/reading/analysis.json Reading.Positive Reading.Nonnegative
lpaf slice reports/generated/reading/analysis.json Reading.forward_positive --max-depth 2
lpaf slice reports/generated/reading/analysis.json Reading.Positive --direction dependents
lpaf similar reports/generated/reading/analysis.json Reading.keep_positive --json
```

This fixture includes a strict/non-strict inequality comparison, a chain of
candidate references, strings differing only in internal whitespace, and a
duplicate short name. `inspect ... forward_positive --json` intentionally returns
ambiguity; select `Reading.forward_positive` or `Other.forward_positive`.

For the RH pilot, `riemannHypothesis` also names more than one captured
declaration in the chosen sample. Use `search` to obtain IDs rather than
silently treating files from different roles as a single theorem environment.

## Migration from v0.1 and extensions

Re-run `analyze` to obtain `lean-atlas-v0.2` full captured fields. Old reports
can still be searched and navigated, but their previews cannot establish text
equality; comparison returns `input_incomplete`. Do not add false completeness
flags to a legacy file as a substitute for re-extraction.

The source query envelope is the first implementation boundary, not the final
common schema for future elaborated and annotated evidence. Future MCP wrappers
should call these functions and preserve their errors/coverage, rather than
reimplementing the operations. Resolved assumptions, notation expansion and
proof-step relationships require the pinned Lean extractor planned in the
[roadmap](ROADMAP.md).
