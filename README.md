# Lean Proof Analysis Framework (LPAF)

**A reusable library for scientific analysis of Lean proof corpora, usable by humans and AI/LLM agents.**

**日本語:** 大量のLean形式的証明を分析対象として、依存関係、証明項の構造、反復する部分構造を測定・比較するフレームワークです。人間の読解・探索支援はその応用の一つです。公開リーマン予想形式化を初期のケーススタディとし、他のLeanプロジェクトにも同じ分析を適用できる設計を目指します。

> **Status: experimental scientific analysis toolkit (v0.3).** Includes actual Lean expression export, a SQLite corpus store, and six graph/term analyses through one Python/CLI interface. The separate source-reading tools remain available. The semantic exporter has been tested with **Lean 4.33.1**; compatibility with other versions is unestablished.

## What can be analyzed

| CLI operation | Python function | Recorded evidence it summarizes |
|---|---|---|
| `graph` | `analyze_dependencies` | Reference degrees, weak/strong components, condensation depth, module coupling, selected-root reachability |
| `overlap` | `dependency_overlap` | Shared and distinct direct references of two declarations |
| `bottlenecks` | `dependency_bottlenecks` | Dominators in the recorded graph reachable from a selected root |
| `terms` | `profile_terms` | Expression DAG size, depth, constructor counts, and bounded expanded-occurrence counts |
| `patterns` | `find_repeated_subterms` | Repeated encoded subterms supported by multiple declarations |
| `term-compare` | `compare_term_structure` | Structural fingerprints and a bounded first-difference report for two expression roots |

These operations measure the supplied corpus. Reference overlap does not establish theorem equivalence; graph dominance does not establish mathematical necessity; recurring syntax does not by itself identify a mathematical method. Proof correctness, novelty, and measured reductions in human review time are not claimed.

The library also provides `export_lean`, `import_corpus`, `open_corpus`, and `ProofCorpus.select`. Source-level `analyze_project` and the five reading operations are a supported subset, documented below. A hosted MCP service is not included.

## Quickstart: analyze actual Lean expressions

Requirements: **Python 3.10+** and an existing **Lean 4.33.1** compiler for this example. Python runtime dependencies are from the standard library. Lean is needed for extraction; analysis of a previously exported corpus does not invoke Lean or an LLM.

From this repository's root, use the supplied `lean/lean-toolchain` pin and point `--lean` to the installed compiler executable:

```bash
python -m pip install -e .
lpaf export lean --lean /absolute/path/to/lean-4.33.1-linux/bin/lean \
  --module Init.Data.List.Basic --prefix List \
  --max-declarations 2000 --out work/list.jsonl --json
lpaf corpus import work/list.jsonl --db work/list.sqlite --json
lpaf corpus info work/list.sqlite --json
lpaf graph work/list.sqlite --kind theorem --role value --json
lpaf terms work/list.sqlite --kind theorem --field value --json
lpaf patterns work/list.sqlite --kind theorem --field value \
  --min-nodes 3 --min-declarations 2 --limit 20 --json
```

Exports and imports require **new output paths** and refuse to overwrite existing artifacts. Inspect selection completeness and expression availability before interpreting the results. The declaration cap may bound the selected sample, and an expression may be omitted because of its node cap.

`--kind theorem` helps separate theorems from definitions and other declarations, but can still include compiler-generated equation theorems. All six analyses also accept repeatable `--kind` and `--module` filters, plus `--prefix` for a namespace and its descendants. References to unselected targets are retained and reported as corpus boundaries. Filter options and counts remain in the result provenance.

Scientific commands return JSON: indented by default and compact with `--json`. See the [analysis API](docs/ANALYSIS_API.md) for all options, result contracts, selection semantics, and limits; see the [validation record](docs/ANALYSIS_VALIDATION.md) for executed checks and observed data.

### Analyze a built Lean project

The project must already have its modules and dependencies built with its own `lean-toolchain`. The default runner uses that project's `lake env lean`:

```bash
lpaf export /path/to/LeanProject --module MyProject.Main --prefix MyProject \
  --max-declarations 1000 --max-nodes 100000 --timeout 300 \
  --out work/project.jsonl --json
lpaf corpus import work/project.jsonl --db work/project.sqlite --json
```

Replace the project/module names with real ones. Export does not build the project, install a toolchain, or fetch dependencies. `--module`, `--prefix`, and `--name` are repeatable during export; `--lean` selects an explicit binary, and `--lean-path` supplies its module search path when needed. Importing built Lean modules is an explicit code-execution step, unlike source-only scanning. Other Lean versions need separate compatibility testing. The [extractor documentation](lean/README.md) describes the serialized expressions and direct references.

### Use the same analyses from Python

```python
from lean_proof_analysis import (
    open_corpus, analyze_dependencies, profile_terms, find_repeated_subterms,
)

with open_corpus("work/list.sqlite") as corpus:
    theorems = corpus.select(kinds=["theorem"], name_prefix="List")
    graph = analyze_dependencies(theorems, role="value", top_k=20)
    sizes = profile_terms(theorems, field="value", top_k=20)
    repeats = find_repeated_subterms(theorems, field="value", limit=20)
    print(graph["coverage"])
    print(repeats["data"])
```

`CorpusView` shares the parent connection and must be used before it closes. Each scientific result records its operation, method, options, provenance, coverage, and data. Graph analyses keep elaborated references and lexical candidate references in separate evidence layers.

## Scope and computational limits

- **Storage:** JSONL ingestion streams declaration records into SQLite. The graph algorithms still load their working graph into memory; SQLite does not make every analysis disk-bounded.
- **Expressions:** Measurements distinguish DAG nodes from expanded tree occurrences. Saturated counts, unavailable expressions, and bounded pattern indexes are explicit in the output.
- **Interpretation:** Structural comparison preserves the encoded binding/universe/literal information and ignores binder display names. It does not unfold definitions or test definitional equality.
- **Coverage:** Imported modules, selected declarations, expression availability, and graph boundaries are separate questions. An unselected target is not a known leaf, and an omitted expression is not an empty proof.
- **Provenance:** Semantic export records the toolchain, selection, and available project metadata, but does not authenticate compiled artifacts or provide source line locations. Cite the module/declaration and export identity when no source URL is available.

The [architecture](docs/ARCHITECTURE.md) specifies these boundaries. The [goals](docs/GOALS.md) and [roadmap](docs/ROADMAP.md) distinguish implemented analyses from research still to be evaluated.

## Source reading and the RH pilot

The text-only layer supports projects without a running Lean toolchain. It captures source spans and **lexical candidate** references; it does not resolve actual Lean references.

```bash
lpaf analyze examples/demo --out reports/generated/demo \
  --repo Unjuno/lean-proof-analysis-framework \
  --commit "$(git rev-parse HEAD)" --source-prefix examples/demo --entry Demo.true_two --json
lpaf search reports/generated/demo/analysis.json true
lpaf inspect reports/generated/demo/analysis.json Demo.true_two --full-text
lpaf compare reports/generated/demo/analysis.json Demo.labelA Demo.labelB
lpaf slice reports/generated/demo/analysis.json Demo.true_two --max-depth 2
lpaf similar reports/generated/demo/analysis.json Demo.true_one --json
```

On Windows PowerShell, replace the commit expression with the actual full commit ID. `--repo` and `--commit` are claimed provenance unless a complete `--expected-manifest` is supplied. Reading commands render Markdown by default or the same result as JSON with `--json`. Publishing a source report also publishes its captured excerpts; upstream licensing still applies.

Existing reports can be adapted for graph analysis without inventing expressions:

```bash
lpaf corpus import reports/generated/demo/analysis.json \
  --format source --db work/demo-source.sqlite --json
lpaf graph work/demo-source.sqlite --json
```

Term tools report unavailable expressions for this source-only corpus. See the [reading design](docs/READING_TOOLS.md), [reading API](docs/READING_API.md), and [reading validation](docs/READING_VALIDATION.md) for the retained v0.2 workflow.

The RH case study remains a **10-file source pilot**, pinned to an immutable upstream commit and a complete SHA-1 manifest:

```bash
python examples/riemann/fetch_pilot.py \
  --manifest examples/riemann/expected_blobs.json --out work/rh-pilot
lpaf analyze work/rh-pilot --out reports/generated/rh-pilot \
  --repo leanprover-community/riemann-hypothesis \
  --commit aa01316131472849f8e3b5b3e49f04d0a06c983f \
  --expected-manifest examples/riemann/expected_blobs.json \
  --entry riemannHypothesis --json
```

This pilot does not establish elaborated extraction over the full RH project or generalization to other corpora.

## Development and documentation

```bash
python -m unittest discover -s tests -v
LPAF_LEAN=/absolute/path/to/lean-4.33.1-linux/bin/lean python -m unittest discover -s tests -v
```

The first command skips compiler-dependent cases unless `LPAF_LEAN` is set. The second enables them with the supplied compiler; it does not install one.

| Location | Purpose |
|---|---|
| `src/lean_proof_analysis/` | Export wrapper, corpus store, graph/term analyses, source-reading tools, CLI |
| `src/lean_proof_analysis/lean/Export.lean` | Bundled Lean expression exporter |
| `lean/` | Compiler pin, native fixture, and extraction instructions |
| `tests/` | Deterministic fixtures and optional native Lean integration tests |
| `examples/` | Synthetic source example and pinned RH pilot |
| [Analysis API](docs/ANALYSIS_API.md) | Scientific library/CLI contracts and resource limits |
| [Architecture](docs/ARCHITECTURE.md) | Adapters, evidence, schemas, and completeness |
| [Agent guide](docs/AGENTS.md) | Using results as grounded tool evidence |
| [Research](docs/RESEARCH.md) | Related work and positioning |

## License and upstream materials

**The Unlicense** applies to code and documentation authored for this repository. It does not relicense Lean, Mathlib, publications, or analyzed repositories. RH source files remain referenced by hash/URL and downloaded locally. Contributions should preserve evidence labels and report what was actually tested.
