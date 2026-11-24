# Lean Proof Analysis Framework (LPAF)

**Reusable analysis tools for Lean formal proofs, for both human readers and AI/LLM agents.**

**日本語:** 大規模なLean形式的証明について、定理・依存候補・構造的類似・証明パターンを整理し、人間が原典に戻って内容を検討しやすくするオープンなライブラリです。初期の適用対象は公開リーマン予想形式化です。

> **Status: experimental source-only reading tools (v0.2).** This version scans Lean *text*. It does **not** invoke Lean, elaborate expressions, resolve actual references, establish theorem equivalence, determine mathematical correctness, or certify proofs. See [limits and evidence types](docs/ARCHITECTURE.md).

## Goals

- Analyze Lean projects with reusable, independent analysis components.
- Support **humans** (Markdown, CSV, and graph navigation) and **agents** (Python API, command-line JSON) through the same code path.
- Preserve provenance: source paths, exact repository revisions, file hashes, analysis methods, and what could not be determined.
- Cluster related declarations and recurring patterns **as candidates**, while preserving assumptions and source access.
- Test whether these views help people locate premises, compare theorem statements, and navigate proof structure.

**Not a goal:** Automatically deciding whether the Riemann Hypothesis proof or any other Lean project is mathematically correct.

## What works today

| Interface | Status | Notes |
|---|---|---|
| Python library (`analyze_project`, `load_report`) | Available | Runs source-level heuristic analysis |
| CLI (`lpaf analyze`) | Available | Writes `analysis.json`, CSV, DOT, and Markdown |
| Reading tools: search, inspect, compare, slice, similar | Available in v0.2 | Shared Python functions, CLI Markdown and JSON; see [reading API](docs/READING_API.md) |
| Agent-compatible JSON | Available | Use `--json`, or read the versioned `analysis.json` file |
| Lean 4 elaborated `Expr` / actual declaration references | Planned | Requires project-specific Lean toolchain |
| MCP server for external agents | Planned | No MCP endpoint is shipped in v0.2 |
| Proof checking / correctness determination | Out of scope | Not claimed |

## Getting started

Requirements: **Python 3.10+**. This source-only baseline uses the Python standard library at runtime. **Lean is not needed** for the demo.

```bash
python -m pip install -e .
lpaf analyze examples/demo --out reports/generated/demo \
  --repo Unjuno/lean-proof-analysis-framework \
  --commit "$(git rev-parse HEAD)" --source-prefix examples/demo --entry Demo.true_two --json
python -m unittest discover -s tests -v
```

On Windows PowerShell, replace `$(git rev-parse HEAD)` with the current full commit ID. The `--repo` and `--commit` values establish **claimed provenance**; they are not automatically checked against the checkout unless a complete `--expected-manifest` is supplied.

Inspect `reports/generated/demo/OVERVIEW.md` or query `analysis.json` using the operations below. Since v0.2, the JSON contains full captured source spans; publishing a generated report also publishes those excerpts. Source licensing and access conditions remain separate from the toolkit's license.

### Read, compare, and follow references

```bash
lpaf search reports/generated/demo/analysis.json true
lpaf inspect reports/generated/demo/analysis.json Demo.true_two --full-text
lpaf compare reports/generated/demo/analysis.json Demo.labelA Demo.labelB
lpaf slice reports/generated/demo/analysis.json Demo.true_two --max-depth 2
lpaf similar reports/generated/demo/analysis.json Demo.true_one --json
```

Each command uses the same result as its Python function. Add `--json` for an
agent-readable result, or omit it for Markdown. Same-name ambiguity, pagination,
text limits and graph frontiers are explicit. `--full-text` returns all **captured**
text; enclosing section variables and implicit arguments remain unresolved.

The [reading-tool design](docs/READING_TOOLS.md) explains seven prioritized ideas
and their mathematical reading tasks. The [API reference](docs/READING_API.md)
specifies the five implemented operations, errors, limits and migration from v0.1.
The [validation record](docs/READING_VALIDATION.md) records fixture checks and the
pinned RH pilot without claiming measured human benefits.

### Python API

```python
from lean_proof_analysis import analyze_project

report = analyze_project(
    "examples/demo", "reports/generated/api-demo",
    repository="Unjuno/lean-proof-analysis-framework",
    commit="<full commit SHA>",  # use the actual commit of the analyzed checkout
    entry_points=["Demo.true_two"],
    source_prefix="examples/demo",
)
print(report["summary"])
```

```python
from lean_proof_analysis import (
    load_report, get_declaration, compare_declarations, dependency_slice,
)

report = load_report("reports/generated/demo/analysis.json")
card = get_declaration(report, "Demo.true_two", max_chars=None)
differences = compare_declarations(report, "Demo.labelA", "Demo.labelB")
nearby = dependency_slice(report, "Demo.true_two", max_depth=2, max_nodes=20)
```

### Riemann Hypothesis case study (10-file pilot)

The example has an **immutable upstream commit and a complete, 10-file SHA-1 manifest**. It downloads public text **to a local ignored folder**, verifies hashes, then runs the same library used for the demo.

```bash
python examples/riemann/fetch_pilot.py \
  --manifest examples/riemann/expected_blobs.json --out work/rh-pilot
lpaf analyze work/rh-pilot --out reports/generated/rh-pilot \
  --repo leanprover-community/riemann-hypothesis \
  --commit aa01316131472849f8e3b5b3e49f04d0a06c983f \
  --expected-manifest examples/riemann/expected_blobs.json \
  --entry riemannHypothesis --json
```

This is a **sample**, not a run over the full proof corpus. It is limited to 5,000 local files and may miss Lean-specific declarations, notation, implicit dependencies and macro expansions.

## Repository map

```text
src/lean_proof_analysis/   Python library + CLI (source-only baseline)
tests/                     Standard-library unit tests
examples/demo/             Synthetic fixture
examples/riemann/          Pinned upstream manifest and read-only fetcher
docs/GOALS.md              Scope and success criteria
docs/ARCHITECTURE.md       Evidence levels, data model, interfaces
docs/ROADMAP.md            Phased implementation plan
docs/RESEARCH.md           Related work and positioning
docs/VALIDATION.md         Reproducibility and human-study protocol
docs/AGENTS.md             Safe integration guidance for AI agents
docs/READING_TOOLS.md      Prioritized reading tasks and research rationale
docs/READING_API.md        Five query operations, bounds, errors and examples
```

See [roadmap](docs/ROADMAP.md) for the next implementation tasks and [validation](docs/VALIDATION.md) for explicit test criteria. These tools provide a **reading workflow**; human review-time improvement has not yet been measured.

## License and upstream materials

**The Unlicense** applies to code and documentation authored for this repository. It does **not** relicense Lean, Mathlib, cited publications, or analyzed proof repositories. Consult each upstream source's own license before redistributing it. The RH sources are referenced by hash/URL and are downloaded locally, rather than committed here.

Contributions and issue reports welcome; please keep all automated claims labeled by the evidence actually available.
