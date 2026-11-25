# Elaborated Lean exporter

The bundled `src/lean_proof_analysis/lean/Export.lean` exports the actual `ConstantInfo` types, available values/proof
terms, and direct constant references from an existing Lean environment.
It does not recheck the mathematical correctness of the declarations.

The adapter is compiled and integration-tested with **Lean 4.33.1**. The
fixture pin is in `lean-toolchain`. Other versions must be tested explicitly;
Lean's metaprogramming APIs and compiled module formats are version-dependent.

## Use with a target project

Build the target project's modules using its own `lean-toolchain` and dependency
lockfile. From that project's root, run its own Lake/Lean environment:

```bash
lake env lean --run /absolute/path/to/lpaf/src/lean_proof_analysis/lean/Export.lean \
  --module MyProject.Main --prefix MyProject \
  --max-declarations 10000 --max-nodes 100000 > corpus.jsonl
```

Replace the absolute adapter path and module/namespace names with your actual
ones. The adapter does not download dependencies, change the project's toolchain,
or substitute the fixture toolchain for the target project's pin. Importing an
environment is an explicit execution step; use it with projects you intend to
load, rather than as a text-only parser.

`--module`, `--prefix`, and `--name` are repeatable. Exact names and namespace
prefixes form a union; a prefix matches itself and descendants separated by a
dot. Without name filters, the selected set includes all imported declarations.
The declaration limit defaults to 1000; the per-expression node limit defaults
to 100000. Selected declarations are emitted in deterministic name order.

When invoking a Lean binary by absolute path, also place its `bin` directory on
the task-local `PATH`: Lean's `findSysroot` invokes `lean --print-prefix`.
The validation script below handles this automatically.

## JSONL contract

The first record is a `lpaf-corpus-v0.1` header with the Lean version, selection
options, extractor identity and normalization policy. Each subsequent declaration
record includes its full name, kind, origin module when known, separate
`type_expr` and `value_expr`, and separate direct `references.type` and
`references.value`. The final footer records counts and selection completeness.
A missing footer is not a complete export.

Expression values are DAGs with child-first node order. Each node has `tag`,
`data` (lossless string values), and ordered `children` indices. Binder display
names are separate from structural data. Bound variables use de Bruijn indices.
Universe-level strings, literal type/value, binder information, let-expression
flags, projection identifiers, and metadata are retained. No definitions are
unfolded and no reduction is performed. This is structural evidence, not a
definitional-equality or theorem-equivalence certificate.

`ConstantInfo.value? true` is used deliberately: its default `false` omits
theorem and opaque bodies. An unavailable value is reported as null. Explicit
`expression_status` distinguishes `available`, `node_limit`, and `no_value`.
A node-limited expression is omitted in full, never presented as a complete
partial tree. Direct references are still obtained from the full expression.

Footer `complete` refers to selected declaration coverage, not expression
availability; inspect `expression_status` for every field. References outside
the selected declaration set remain in the data. The exporter does not provide
source line locations, so `source_url` is null rather than invented. A consumer
can attach separately validated source metadata.

The adapter streams records rather than retaining the whole JSON corpus. Lean
still loads the imported environment and sorts selected declaration names in
memory; this does not claim an out-of-core Lean compiler or measured full-Mathlib
scaling.

## Compiler-backed checks

```bash
python scripts/check_lean_export.py --lean /path/to/lean/bin/lean \
  --out work/fixture-corpus.jsonl
LPAF_LEAN=/path/to/lean/bin/lean python -m unittest discover -s tests -p test_lean_export.py -v
```

The script builds the original `Fixture.lean` in a temporary module directory.
Tests inspect actual exported proof terms, type/body references, shared syntax,
alpha-renamed binders, universe/literal preservation, a dependency diamond,
and explicit limits. Tests are skipped when `LPAF_LEAN` is absent; a skipped test
is not evidence of compiler compatibility.

## Primary API references

- [Lean 4.33.1 ConstantInfo and value?](https://github.com/leanprover/lean4/blob/v4.33.1/src/Lean/Declaration.lean)
- [Lean 4.33.1 environment imports and module attribution](https://github.com/leanprover/lean4/blob/v4.33.1/src/Lean/Environment.lean)
- [Lean 4.33.1 used-constant traversal](https://github.com/leanprover/lean4/blob/v4.33.1/src/Lean/Util/FoldConsts.lean)
- [Lean Expr reference](https://lean-lang.org/doc/api/Lean/Expr.html)
