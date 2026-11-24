# Reading tools: validation record

Date: 2026-11-25. Package: v0.2.0. Local runtime: Python 3.12.14.
This record describes functional checks, not a performance benchmark or a
mathematical review of the analyzed corpus.

## Local regression checks

`python -m unittest discover -s tests -v` passed 48 tests. The suite covers
source extraction, manifest failures, full captured text, literal differences,
declaration ambiguity, query bounds, legacy reports, graph cycles/direction,
structured errors, and equality of Python/CLI JSON results. Markdown tests check
that truncation and unknown input are visible. `git diff --check` passed.

Editable package installation completed with no runtime dependencies. The
repository CI also exercises Python 3.10 and 3.12; its result is recorded by
GitHub Actions for the commit, rather than inferred from the local run.

## Pinned RH pilot

- Repository: `leanprover-community/riemann-hypothesis`.
- Source revision: `aa01316131472849f8e3b5b3e49f04d0a06c983f`.
- Input manifest: [`examples/riemann/expected_blobs.json`](../examples/riemann/expected_blobs.json).
- Source files: 10. Every file matched its expected Git blob hash.
- Source lines: 230. Captured declaration candidates: 46.
- Candidate declaration links: 46. Stored similarity candidates: 36.
- Similarity options: pair cap 100000, minimum score 0.78; 261 pairs examined.
- Analysis output schema: `lean-atlas-v0.2`.

These counts describe this selected sample only. No Lean compilation,
elaboration, theorem-equivalence test or proof-correctness assessment was run.

## Reading operations observed on that sample

| Operation | Input | Observed behavior |
|---|---|---|
| Search | `riemannHypothesis` | Five matches across documented search fields; this is not five identical names |
| Inspect ambiguous name | `riemannHypothesis` | `ambiguous_selector`, with two exact-full-name candidates |
| Inspect by ID | `src/Main.lean:4:riemannHypothesis` | Captured statement/body/source available; enclosing-context completeness remains false |
| Compare | Main entry vs `src/Challenge.lean:19:riemannHypothesis` | Same captured statement text, different captured body text, both diffs complete |
| Slice | Main entry, depth 3, node cap 20 | Six nodes returned, one frontier relation omitted at the bound; traversal incomplete |
| Similar | Main entry | Three stored candidates, with non-exhaustive search coverage |

The Main/Challenge comparison describes text in two source files. It does not
combine their environments or judge either proof. The name ambiguity is useful
evidence that selecting declarations by exact ID matters in a real sample.

Reproduce the source run with the commands in the [README](../README.md), then
use [the reading API](READING_API.md). Full generated reports stay under the
ignored `reports/generated/` directory; this record contains only counts and
navigation observations.

## H / T / D / C / U

- **H:** The five operations preserve source evidence and expose omissions on
  their tested inputs, enabling readers and agents to perform specific queries.
- **T:** Run the regression suite plus all five operations on the pinned pilot;
  use explicit IDs for ambiguous names and inspect all bounds/completeness flags.
- **D:** Technical checks pass when expected identities, literal differences,
  bounds, failures and provenance are retained. Human effort reduction remains
  **UNCERTAIN**, because no controlled reader study has been conducted.
- **C:** Source parsing can miss declarations, misidentify scope, confuse a local
  binder with a global name, or omit references introduced through notation.
  Good results on this sample do not establish general extraction completeness.
- **U:** No human timing distribution, model comparison, combined measurement
  uncertainty, or coverage factor is estimated. The remaining uncertainty is
  described by the limitations and future evaluation protocol, not a fabricated
  precision figure.
