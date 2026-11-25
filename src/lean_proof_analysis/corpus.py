"""Validated, disk-backed proof corpora for reusable scientific analyses.

The SQLite store separates declarations, expression DAGs and reference edges.
JSONL ingestion holds one declaration at a time; graph and term analyzers choose
their own working sets. Stored evidence labels describe the supplied extractor,
not an independent proof-correctness or artifact-authenticity certificate.
"""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any

CORPUS_SCHEMA = "lpaf-corpus-v0.1"
STORE_SCHEMA = "lpaf-sqlite-v0.1"
EVIDENCE = {"lean_elaborated", "lexical_candidate"}
ARITIES = {"bvar": 0, "fvar": 0, "mvar": 0, "sort": 0, "const": 0,
           "app": 2, "lam": 2, "forallE": 2, "letE": 3, "lit": 0, "mdata": 1, "proj": 1}


class CorpusError(ValueError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": deepcopy(self.details)}


def _decode(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CorpusError("invalid_corpus", "Duplicate JSON key", key=key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise CorpusError("invalid_corpus", "Non-finite JSON constant", value=value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_expression(expr: Any, *, max_nodes: int = 1_000_000) -> None:
    """Check the transport DAG, including child order; do not type-check it."""
    if not isinstance(expr, dict) or expr.get("truncated") is not False:
        raise CorpusError("invalid_expression", "An available expression must be a complete transport DAG")
    nodes, root = expr.get("nodes"), expr.get("root")
    if not isinstance(nodes, list) or not nodes or len(nodes) > max_nodes:
        raise CorpusError("invalid_expression", "Invalid expression node list or node limit", max_nodes=max_nodes)
    if type(root) is not int or not 0 <= root < len(nodes):
        raise CorpusError("invalid_expression", "Invalid expression root index")
    for pos, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("tag"), str) or node["tag"] not in ARITIES:
            raise CorpusError("invalid_expression", "Unsupported expression constructor", node=pos)
        tag, data, children = node["tag"], node.get("data"), node.get("children")
        if not isinstance(data, list) or any(not isinstance(x, str) for x in data):
            raise CorpusError("invalid_expression", "Expression constructor data must be strings", node=pos)
        if (not isinstance(children, list) or len(children) != ARITIES[tag]
                or any(type(x) is not int or not 0 <= x < pos for x in children)):
            raise CorpusError("invalid_expression", "Children must precede their parent and match constructor arity", node=pos)
        if "binder_name" in node and not isinstance(node["binder_name"], str):
            raise CorpusError("invalid_expression", "Invalid binder display name", node=pos)
        if tag in {"bvar", "fvar", "mvar", "sort", "lam", "forallE", "letE"} and len(data) != 1:
            raise CorpusError("invalid_expression", "Invalid expression constructor payload", node=pos)
        if tag == "bvar" and re.fullmatch(r"0|[1-9][0-9]*", data[0]) is None:
            raise CorpusError("invalid_expression", "Bound-variable index must be a nonnegative integer string", node=pos)
        if tag == "const" and (not data or not data[0]):
            raise CorpusError("invalid_expression", "Missing constant name", node=pos)
        if tag == "app" and data:
            raise CorpusError("invalid_expression", "Application payload must be empty", node=pos)
        if tag == "lit" and (len(data) != 2 or data[0] not in {"nat", "str"}):
            raise CorpusError("invalid_expression", "Literal needs its kind and exact value", node=pos)
        if tag == "lit" and data[0] == "nat" and re.fullmatch(r"0|[1-9][0-9]*", data[1]) is None:
            raise CorpusError("invalid_expression", "Natural literals must contain canonical nonnegative decimal digits", node=pos)
        if tag == "proj" and (len(data) != 2 or re.fullmatch(r"0|[1-9][0-9]*", data[1]) is None):
            raise CorpusError("invalid_expression", "Projection needs type name and field index", node=pos)


def _validate_declaration(record: Any, max_nodes: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise CorpusError("invalid_corpus", "Declaration must be an object")
    for field in ("id", "name", "kind", "evidence"):
        if not isinstance(record.get(field), str) or not record[field]:
            raise CorpusError("invalid_corpus", "Missing declaration identity or evidence", field=field)
    if record["evidence"] not in EVIDENCE:
        raise CorpusError("invalid_corpus", "Unknown declaration evidence", declaration=record["id"])
    for field in ("module", "source_url"):
        if record.get(field) is not None and not isinstance(record[field], str):
            raise CorpusError("invalid_corpus", "Invalid optional declaration field", field=field)
    statuses = record.get("expression_status")
    references = record.get("references")
    if not isinstance(statuses, dict) or not isinstance(references, dict):
        raise CorpusError("invalid_corpus", "Expression status and role-separated references are required")
    for field in ("type", "value"):
        status, expr = statuses.get(field), record.get(field + "_expr")
        if not isinstance(status, str) or status not in {"available", "node_limit", "unavailable", "no_value"}:
            raise CorpusError("invalid_corpus", "Invalid expression availability status", field=field)
        if field == "type" and status == "no_value":
            raise CorpusError("invalid_corpus", "Every declaration has a type; no_value applies only to values")
        if expr is None:
            if status == "available":
                raise CorpusError("invalid_corpus", "Available expression is absent", field=field)
        else:
            if status != "available" or record["evidence"] != "lean_elaborated":
                raise CorpusError("invalid_corpus", "Only elaborated, available expressions may carry an Expr DAG", field=field)
            validate_expression(expr, max_nodes=max_nodes)
        refs = references.get(field)
        if not isinstance(refs, list) or any(not isinstance(x, str) or not x for x in refs):
            raise CorpusError("invalid_corpus", "References must be nonempty string identities", field=field)
        if status == "no_value" and refs:
            raise CorpusError("invalid_corpus", "An absent value cannot supply value references", field=field)
    return record


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE declarations (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
            module TEXT, evidence TEXT NOT NULL, data_json TEXT NOT NULL,
            type_expr TEXT, value_expr TEXT
        );
        CREATE TABLE refs (
            src TEXT NOT NULL REFERENCES declarations(id), dst TEXT NOT NULL,
            role TEXT NOT NULL, evidence TEXT NOT NULL,
            PRIMARY KEY(src,dst,role,evidence)
        );
        CREATE INDEX refs_dst ON refs(dst);
        CREATE INDEX declarations_name ON declarations(name);
        CREATE INDEX declarations_kind ON declarations(kind);
    """)


def _insert(connection: sqlite3.Connection, record: dict[str, Any], max_nodes: int) -> None:
    _validate_declaration(record, max_nodes)
    rest = {k: v for k, v in record.items() if k not in {"type_expr", "value_expr", "references", "record"}}
    try:
        connection.execute("INSERT INTO declarations VALUES (?,?,?,?,?,?,?,?)", (
            record["id"], record["name"], record["kind"], record.get("module"), record["evidence"], _encode(rest),
            _encode(record["type_expr"]) if record.get("type_expr") is not None else None,
            _encode(record["value_expr"]) if record.get("value_expr") is not None else None,
        ))
    except sqlite3.IntegrityError as exc:
        raise CorpusError("duplicate_declaration", "Duplicate declaration ID", declaration=record["id"]) from exc
    for role in ("type", "value"):
        connection.executemany("INSERT OR IGNORE INTO refs VALUES (?,?,?,?)",
                               ((record["id"], target, role, record["evidence"])
                                for target in record["references"][role]))


def _temporary_database(destination: Path) -> tuple[Path, sqlite3.Connection]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise CorpusError("destination_exists", "Choose a new database path; existing corpora are not overwritten",
                          path=str(destination))
    fd, name = tempfile.mkstemp(prefix=".lpaf-import-", suffix=".sqlite", dir=destination.parent)
    os.close(fd)
    path = Path(name)
    connection = sqlite3.connect(path)
    _schema(connection)
    return path, connection


def _finish_database(connection: sqlite3.Connection, temporary: Path, destination: Path,
                     metadata: dict[str, Any]) -> "ProofCorpus":
    metadata["store_schema"] = STORE_SCHEMA
    metadata["declarations"] = connection.execute("SELECT COUNT(*) FROM declarations").fetchone()[0]
    metadata["references"] = connection.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
    connection.executemany("INSERT INTO metadata VALUES (?,?)", ((k, _encode(v)) for k, v in metadata.items()))
    connection.commit()
    connection.close()
    # A hard link atomically installs the completed database and refuses to
    # replace a destination created by another process during ingestion.
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise CorpusError("destination_exists", "Destination appeared during import", path=str(destination)) from exc
    temporary.unlink()
    return ProofCorpus(destination)


def import_corpus(jsonl_path: str | Path, database_path: str | Path, *,
                  max_record_bytes: int = 64 * 1024 * 1024,
                  max_expression_nodes: int = 1_000_000) -> "ProofCorpus":
    """Stream a complete exporter JSONL file into a new SQLite corpus.

    A header and footer are mandatory. A footer can report a bounded selection,
    but an interrupted export without a footer is rejected atomically.
    """
    for name, limit in (("max_record_bytes", max_record_bytes), ("max_expression_nodes", max_expression_nodes)):
        if type(limit) is not int or limit < 1:
            raise CorpusError("invalid_argument", "Import limits must be positive integers", argument=name)
    source, destination = Path(jsonl_path), Path(database_path)
    temporary, connection = _temporary_database(destination)
    header = footer = None
    count = 0
    digest = hashlib.sha256()
    try:
        with source.open("rb") as stream:
            line_number = 0
            while True:
                raw = stream.readline(max_record_bytes + 1)
                if not raw:
                    break
                line_number += 1
                if len(raw) > max_record_bytes:
                    raise CorpusError("record_limit", "JSONL record exceeds the byte budget", line=line_number)
                digest.update(raw)
                if not raw.strip():
                    continue
                try:
                    record = _decode(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise CorpusError("invalid_corpus", "Invalid UTF-8 JSONL record", line=line_number) from exc
                if not isinstance(record, dict):
                    raise CorpusError("invalid_corpus", "JSONL records must be objects", line=line_number)
                if footer is not None:
                    raise CorpusError("invalid_corpus", "Nonempty record after export footer", line=line_number)
                if header is None:
                    if record.get("record") != "header" or record.get("schema") != CORPUS_SCHEMA:
                        raise CorpusError("unsupported_corpus", "Expected LPAF corpus header", line=line_number)
                    header = record
                elif record.get("record") == "declaration":
                    _insert(connection, record, max_expression_nodes)
                    count += 1
                elif record.get("record") == "footer":
                    footer = record
                else:
                    raise CorpusError("invalid_corpus", "Unexpected JSONL record kind", line=line_number)
        if header is None or footer is None:
            raise CorpusError("incomplete_export", "Both header and final footer are required")
        if type(footer.get("declarations")) is not int or footer["declarations"] != count:
            raise CorpusError("invalid_corpus", "Footer declaration count does not match the stream")
        if type(footer.get("complete")) is not bool:
            raise CorpusError("invalid_corpus", "Footer must state selection completeness")
        metadata = {"schema": CORPUS_SCHEMA, "header": header, "footer": footer,
                    "input": {"format": "jsonl", "sha256": digest.hexdigest()},
                    "not_proof_check": True, "selection_complete": footer["complete"],
                    "ingestion_limits": {"max_record_bytes": max_record_bytes,
                                         "max_expression_nodes": max_expression_nodes}}
        return _finish_database(connection, temporary, destination, metadata)
    finally:
        connection.close()
        if temporary.exists():
            temporary.unlink()


def import_source_report(report_path: str | Path, database_path: str | Path) -> "ProofCorpus":
    """Adapt an existing source-only report, without inventing Lean expressions.

    This legacy input is a single JSON document and is loaded in memory. Use
    JSONL for streaming elaborated corpora. Edges remain lexical candidates.
    """
    from .reading import _Index

    source, destination = Path(report_path), Path(database_path)
    raw = source.read_bytes()
    report = _decode(raw.decode("utf-8"))
    index = _Index(report)
    by_source: dict[str, dict[str, list[str]]] = {}
    for edge in index.edges:
        refs = by_source.setdefault(edge["from"], {"type": [], "value": []})
        refs["type" if edge["role"] == "statement" else "value"].append(edge["to"])
    temporary, connection = _temporary_database(destination)
    try:
        for d in index.records:
            _insert(connection, {
                "id": d["id"], "name": d["name"], "kind": d["kind"],
                "module": d["path"].removesuffix(".lean").replace("/", "."),
                "evidence": "lexical_candidate", "source_url": d["source_url"],
                "source_location": {"path": d["path"], "line": d["line"], "end_line": d["end_line"]},
                "type_expr": None, "value_expr": None,
                "expression_status": {"type": "unavailable", "value": "unavailable"},
                "references": by_source.get(d["id"], {"type": [], "value": []}),
            }, 1)
        metadata = {
            "schema": CORPUS_SCHEMA, "input": {"format": report["schema"], "sha256": hashlib.sha256(raw).hexdigest()},
            "header": {"record": "header", "schema": CORPUS_SCHEMA, "adapter": "source-report",
                       "evidence": "lexical_candidate", "provenance": deepcopy(report["provenance"])},
            "footer": {"record": "footer", "declarations": len(index.records), "complete": True},
            "not_proof_check": True, "selection_complete": True,
            "limitations": ["All recorded source candidates imported; extraction and semantic coverage remain incomplete.",
                            "The role 'type' represents source statement tokens, not an elaborated Lean type."],
        }
        return _finish_database(connection, temporary, destination, metadata)
    finally:
        connection.close()
        if temporary.exists():
            temporary.unlink()


class ProofCorpus:
    """A read-only SQLite-backed corpus; supports use as a context manager."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).resolve()
        try:
            self._connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            self._connection.row_factory = sqlite3.Row
            self._metadata = {row["key"]: _decode(row["value"])
                              for row in self._connection.execute("SELECT key,value FROM metadata")}
            if self._metadata.get("store_schema") != STORE_SCHEMA:
                raise CorpusError("unsupported_corpus", "Unsupported SQLite corpus schema")
        except (sqlite3.Error, CorpusError):
            if hasattr(self, "_connection"):
                self._connection.close()
            raise

    @property
    def metadata(self) -> dict[str, Any]:
        return deepcopy(self._metadata)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ProofCorpus":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @staticmethod
    def _record(row: sqlite3.Row, include_expressions: bool) -> dict[str, Any]:
        result = _decode(row["data_json"])
        if include_expressions:
            result["type_expr"] = _decode(row["type_expr"]) if row["type_expr"] is not None else None
            result["value_expr"] = _decode(row["value_expr"]) if row["value_expr"] is not None else None
        return result

    def iter_declarations(self, include_expressions: bool = False) -> Iterator[dict[str, Any]]:
        columns = "data_json,type_expr,value_expr" if include_expressions else "data_json"
        for row in self._connection.execute(f"SELECT {columns} FROM declarations ORDER BY id"):
            yield self._record(row, include_expressions)

    def get_declaration(self, selector: str, include_expressions: bool = True) -> dict[str, Any]:
        if not isinstance(selector, str) or not selector:
            raise CorpusError("invalid_argument", "An exact ID or full name is required")
        columns = "data_json,type_expr,value_expr" if include_expressions else "data_json"
        rows = self._connection.execute(f"SELECT {columns} FROM declarations WHERE id=?", (selector,)).fetchall()
        if not rows:
            rows = self._connection.execute(f"SELECT {columns} FROM declarations WHERE name=? ORDER BY id LIMIT 51", (selector,)).fetchall()
        if not rows:
            raise CorpusError("declaration_not_found", "Declaration is outside this corpus", selector=selector)
        if len(rows) > 1:
            raise CorpusError("ambiguous_selector", "Use an exact declaration ID", selector=selector,
                              candidates=[_decode(r["data_json"])["id"] for r in rows[:50]],
                              candidates_truncated=len(rows) > 50)
        return self._record(rows[0], include_expressions)

    def iter_references(self, role: str = "all") -> Iterator[dict[str, str]]:
        if not isinstance(role, str) or role not in {"all", "type", "value"}:
            raise CorpusError("invalid_argument", "role must be all, type or value")
        where, parameters = ("", ()) if role == "all" else (" WHERE role=?", (role,))
        for row in self._connection.execute("SELECT src,dst,role,evidence FROM refs" + where +
                                             " ORDER BY src,dst,role,evidence", parameters):
            yield {"from": row["src"], "to": row["dst"], "role": row["role"], "evidence": row["evidence"]}

    def select(self, *, kinds=None, modules=None, name_prefix: str | None = None) -> "CorpusView":
        """Select declaration sources; retain references to excluded targets.

        The view shares this read-only connection and must be used before the
        parent corpus is closed. Filters do not rewrite the stored export.
        """
        return CorpusView(self, kinds=kinds, modules=modules, name_prefix=name_prefix)


class CorpusView:
    """A composable input to every analyzer, with explicit selection metadata."""

    def __init__(self, corpus: ProofCorpus, *, kinds=None, modules=None, name_prefix=None):
        self._corpus = corpus
        self._clauses: list[str] = []
        self._parameters: list[Any] = []
        self._filters = {}
        for field, values in (("kind", kinds), ("module", modules)):
            if values is None:
                self._filters[field] = None
                continue
            if not isinstance(values, (list, tuple, set, frozenset)) or any(not isinstance(v, str) or not v for v in values):
                raise CorpusError("invalid_argument", "Selection filters must be collections of nonempty strings", field=field)
            values = sorted(set(values))
            self._filters[field] = values
            if not values:
                self._clauses.append("0")
            else:
                self._clauses.append(f"d.{field} IN ({','.join('?' for _ in values)})")
                self._parameters.extend(values)
        if name_prefix is not None:
            if not isinstance(name_prefix, str) or not name_prefix:
                raise CorpusError("invalid_argument", "Name prefix must be a nonempty string")
            self._clauses.append("(d.name=? OR substr(d.name,1,?)=?)")
            self._parameters.extend((name_prefix, len(name_prefix) + 1, name_prefix + "."))
        self._filters["name_prefix"] = name_prefix

    def _where(self, extra: str = "") -> str:
        clauses = self._clauses + ([extra] if extra else [])
        return " WHERE " + " AND ".join(clauses) if clauses else ""

    @property
    def metadata(self) -> dict[str, Any]:
        result = self._corpus.metadata
        connection = self._corpus._connection
        result["unfiltered_counts"] = {k: result.get(k) for k in ("declarations", "references")}
        result["declarations"] = connection.execute(
            "SELECT COUNT(*) FROM declarations d" + self._where(), self._parameters).fetchone()[0]
        result["references"] = connection.execute(
            "SELECT COUNT(*) FROM refs r JOIN declarations d ON r.src=d.id" + self._where(), self._parameters).fetchone()[0]
        result["view"] = {"filters": deepcopy(self._filters),
                          "reference_policy": "retain edges from selected sources, including excluded or absent targets",
                          "automatic_generated_code_detection": False}
        return result

    def iter_declarations(self, include_expressions: bool = False) -> Iterator[dict[str, Any]]:
        columns = "d.data_json,d.type_expr,d.value_expr" if include_expressions else "d.data_json"
        for row in self._corpus._connection.execute(
                f"SELECT {columns} FROM declarations d" + self._where() + " ORDER BY d.id", self._parameters):
            yield ProofCorpus._record(row, include_expressions)

    def get_declaration(self, selector: str, include_expressions: bool = True) -> dict[str, Any]:
        if not isinstance(selector, str) or not selector:
            raise CorpusError("invalid_argument", "An exact ID or full name is required")
        columns = "d.data_json,d.type_expr,d.value_expr" if include_expressions else "d.data_json"
        rows = []
        for field in ("id", "name"):
            rows = self._corpus._connection.execute(
                f"SELECT {columns} FROM declarations d" + self._where(f"d.{field}=?") + " ORDER BY d.id LIMIT 51",
                self._parameters + [selector]).fetchall()
            if rows:
                break
        if not rows:
            raise CorpusError("declaration_not_found", "Declaration is outside the selected corpus view", selector=selector)
        if len(rows) > 1:
            raise CorpusError("ambiguous_selector", "Use an exact declaration ID within this view", selector=selector,
                              candidates=[_decode(row["data_json"])["id"] for row in rows[:50]],
                              candidates_truncated=len(rows) > 50)
        return ProofCorpus._record(rows[0], include_expressions)

    def iter_references(self, role: str = "all") -> Iterator[dict[str, str]]:
        if not isinstance(role, str) or role not in {"all", "type", "value"}:
            raise CorpusError("invalid_argument", "role must be all, type or value")
        extra, parameters = ("", self._parameters) if role == "all" else ("r.role=?", self._parameters + [role])
        for row in self._corpus._connection.execute(
                "SELECT r.src,r.dst,r.role,r.evidence FROM refs r JOIN declarations d ON r.src=d.id" +
                self._where(extra) + " ORDER BY r.src,r.dst,r.role,r.evidence", parameters):
            yield {"from": row["src"], "to": row["dst"], "role": row["role"], "evidence": row["evidence"]}


def open_corpus(database_path: str | Path) -> ProofCorpus:
    return ProofCorpus(database_path)
