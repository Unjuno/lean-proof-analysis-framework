# Architecture and evidence model

## Flow

```text
Lean project + immutable revision + input manifest
  -> source adapter (implemented; source-only heuristics)
  -> elaborated Lean adapter (planned; Environment, Expr, ConstantInfo)
  -> common records (declarations, references, evidence, provenance)
  -> analysis plugins (graph, similarity, pattern, statistics)
  -> shared report builder
  -> human Markdown/CSV/DOT | Python API/JSON CLI | future MCP adapter
```

The adapters must report **what data was actually observed**, and must never silently upgrade heuristic results into verified Lean facts.

## Evidence levels

| Level | Meaning | Current support |
|---|---|---|
| `source_observed` | Characters, declaration candidates, imports and hashes seen in files | Partial: heuristics; not a Lean lexer |
| `lexical_candidate` | A name match or a source-syntax similarity suggestion | Implemented |
| `lean_elaborated` | A declaration, type, expression or reference resolved by the real Lean environment | **Not yet implemented** |
| `literature_annotated` | A link to an externally published theorem/method with human-checked source | Planned |
| `human_interpretation` | Reviewer's explanation or manual categorization | Planned |

No output represents proof correctness. A candidate link is not an authoritative edge of the elaborated proof dependency DAG.

## Current data and files

- `analysis.json`: version marker (`schema`), source-only `mode`, `not_proof_check`, provenance and derived findings.
- `index.csv`: declaration candidates and source line references.
- `candidate_links.csv`: lexical matches (the only supported dependency candidate at this stage).
- `similarity.csv`: text-based TF-IDF and normalized source-syntax candidate comparisons.
- `OVERVIEW.md`, `REPORT.md`: human navigation materials.
- `candidate_deps.dot`: graphical representation of *candidate* edges (can be rendered by Graphviz).

## Stable API boundary

`analyze_project(source_dir, output_dir, *, repository, commit, expected_blobs=None, entry_points=(), source_prefix="", ...)` writes the same data the CLI uses. `load_report` reads previous JSON data. Consumers should check `schema`, `mode`, and evidence labels before using any result.

## Known limitations (must be resolved before scaling)

1. Regex-based declaration scanning is incomplete for Lean syntax, macros, attributes, tactics, and overloaded names.
2. String-similarity and shared-name heuristics do not establish definitional or mathematical equivalence.
3. Extraction may omit declarations and cross-file references; import resolution is only partial.
4. No streaming database or complexity control beyond file and pair limits for very large source trees.
5. Markdown summaries may not faithfully describe theorem methods until a grounded semantic layer is available.

## Future elaborated adapter

Build with the **target repository's own pinned Lean toolchain and Mathlib revision**. Read Lean `Environment` and `Expr`/`ConstantInfo` to obtain authoritative declaration types, expression references, name resolution, and a richer provenance tree. Preserve both source-level and elaborated representations; they answer different questions.

## Output truncation

Human-facing JSON/CSV previews may shorten source excerpts for readability and redistribution hygiene. The comparison algorithm uses the untruncated in-memory statement/body; a shortened preview must **never** be presented as a complete Lean statement. Always follow the exact pinned source URL before drawing a mathematical conclusion.
