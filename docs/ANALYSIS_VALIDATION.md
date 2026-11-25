# Scientific analysis: validation record

Date: 2026-11-25. Package: v0.3.0. Local runtime: Python 3.12.14,
Linux x86-64; compiler: Lean 4.33.1. These are functional observations and corpus
counts, not runtime benchmarks or a review of mathematical correctness.

## 1. Implementation checks

The full local suite passed **119 tests with no skips**, including actual Lean
execution, using:

```bash
LPAF_LEAN=/absolute/path/to/lean-4.33.1-linux/bin/lean \
  python -m unittest discover -s tests -v
```

Coverage includes the original reading APIs, persisted corpus validation,
selection boundaries, the six scientific analyzers, CLI/library parity, process
cleanup, atomic output publication, and native extraction. The native fixture
contains 12 declarations, including an axiom whose absent value is distinct from
a capped expression. Graph dominators are checked against a separate
vertex-removal oracle on 40 deterministic generated graphs. Deep cases cover
2,500 graph/term levels without Python-recursive traversal.

A v0.3.0 wheel was built and installed into an isolated directory. The installed
package exposes `export_lean` and contains the bundled `lean/Export.lean` resource
with the same bytes as the source asset. CI retains Python 3.10 and 3.12 jobs and
adds a full-suite Lean integration job. Remote job outcomes belong to the
corresponding GitHub Actions run, rather than being inferred from this record.

## 2. Real Lean standard-library corpus

Input: the official Lean 4.33.1 Linux release, importing `Init.Data.List.Basic`,
then selecting names in the `List` namespace across the imported environment.
This includes declarations originating in imported modules; it is not an
inventory of only `Init.Data.List.Basic`.

Extraction limits were 2,000 declarations and 100,000 serialized nodes per
expression. The export selected all 824 matching declarations. A subsequent
`kind=theorem` view selected 298 declarations. That kind can include generated
equation theorems and auxiliary theorems as well as handwritten declarations.

| Observation | Value | Unit / scope |
|---|---:|---|
| Exported declarations | 824 | Count, all selected kinds |
| Stored reference records | 10,585 | Count, type/value roles kept separate |
| Theorem view | 298 | Count, exact `theorem` kind |
| Available theorem value expressions | 298 | Count; no capped/missing value in this view |
| Reachable serialized expression nodes | 28,818 | Count, summed over theorem values |
| Expanded expression occurrences | 111,410 | Count, exact below the configured cap |
| Expression depth | 4–62 | Node levels, theorem values |
| Theorem value reference edges | 2,657 | Unique consumer/reference pairs |
| Internal edges in theorem view | 63 | Both endpoints in selected view |
| Boundary edges | 2,594 | Selected consumer, excluded target |
| Distinct boundary targets | 332 | Count; their outgoing adjacency is unknown |
| Repeated patterns meeting thresholds | 465 | Encoded substructures, at least 5 expanded nodes and 3 distinct declarations |

Counts are dimensionless nonnegative integers; depth is measured in node levels.
Serialized nodes and expanded occurrences are different counting units and are
not interchangeable. Reference records can differ from unique edge counts when
roles are combined. The 63 internal and 2,594 boundary edges account for all 2,657
value-reference edges without discarding excluded declarations.

Pattern indexing retained 16,620 qualifying-size fingerprints without reaching
the 100,000-pattern cap. Output was limited to five patterns; their distinct
declaration supports were 25, 24, 24, 21, and 21. The first pattern requires five
enclosing binders, so its occurrences cannot be interpreted as interchangeable
standalone proofs. Patterns overlap and are not additive compression savings.
These observations concern encoded substructures, not 465 identified
mathematical proof strategies.

All six analyzers ran on this view. `List.append_assoc` and `List.append_nil`
shared 15 recorded direct value references; the latter had two additional
references. Their encoded proof terms differed. A dominator query for
`List.append_assoc` found no other reachable internal theorem: all 15 direct
targets were outside the theorem view. This describes the restricted graph,
not an absence of mathematical dependencies.

Reproduce the pipeline with new output paths:

```bash
lpaf export lean --lean /absolute/path/to/lean-4.33.1-linux/bin/lean \
  --module Init.Data.List.Basic --prefix List \
  --max-declarations 2000 --max-nodes 100000 \
  --out work/list.jsonl --json
lpaf corpus import work/list.jsonl --db work/list.sqlite --json
lpaf terms work/list.sqlite --kind theorem --json
lpaf graph work/list.sqlite --kind theorem --role value --json
lpaf patterns work/list.sqlite --kind theorem \
  --min-nodes 5 --min-declarations 3 --limit 5 --json
lpaf overlap work/list.sqlite List.append_assoc List.append_nil \
  --kind theorem --role value --json
lpaf bottlenecks work/list.sqlite List.append_assoc \
  --kind theorem --role value --json
lpaf term-compare work/list.sqlite List.append_assoc List.append_nil \
  --kind theorem --json
```

## 3. Source-only RH pilot through the same corpus API

The ten files in the [pinned manifest](../examples/riemann/expected_blobs.json)
were downloaded again and every Git blob hash matched. Source revision:
`aa01316131472849f8e3b5b3e49f04d0a06c983f` in
`leanprover-community/riemann-hypothesis`.

The source analyzer recorded 46 declaration candidates and 46 role-specific
reference candidates. Importing the report into SQLite and combining roles
produced 44 unique edges, all in the `lexical_candidate` layer. This adapter only
supplies candidate links resolved within the sample; zero stored boundary links
is not evidence that the proof has no external dependencies.

`profile_terms` returned 46 `unavailable` expressions and zero analyzed
expressions. It did not manufacture proof terms or silently treat missing terms
as empty proofs. A semantic export of the full RH project was **not performed**
in this milestone.

After the pinned source run described in the README:

```bash
lpaf corpus import reports/generated/rh-pilot/analysis.json \
  --format source --db work/rh-source.sqlite --json
lpaf graph work/rh-source.sqlite --json
lpaf terms work/rh-source.sqlite --json
```

## 4. Provenance and practical limits

Observed export hashes and compact counts are in
[`data/analysis-v0.3.json`](data/analysis-v0.3.json). The export came from the v0.3
working tree before publication; its header records the base Git revision and
dirty state, plus exporter and toolchain hashes. Re-running after a commit can
change the whole-file hash through changed provenance while leaving structural
counts unchanged.

Only Lean 4.33.1 compatibility has been exercised. Graph operations load the
selected graph into memory. No whole-Mathlib memory/throughput benchmark, full-RH
semantic extraction, model-size comparison, or controlled human-benefit study
has been completed. Structural fingerprints use SHA-256 with binder display
labels omitted; they do not unfold definitions or certify theorem equivalence.
Exported source positions are currently unavailable.

Under the [H/T/D/C/U protocol](VALIDATION.md), the tested technical milestone is
PASS. Scalability beyond the observed corpus and task-level usefulness remain
UNCERTAIN. Principal interpretation risks are scope, generated declarations,
representation dependence, and binding context. No statistical precision or
coverage factor has been fabricated for these deterministic checks.
