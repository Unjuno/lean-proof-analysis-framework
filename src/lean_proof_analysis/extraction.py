"""Explicit execution of the bundled Lean exporter under a project toolchain.

No source build or toolchain installation is initiated by this module. Loading
compiled Lean modules is code execution and can run their initializers; use a
project the caller intentionally wants to load. Transport validation does not
certify mathematical correctness or authenticate compiled artifacts.
"""
from __future__ import annotations

import hashlib
from importlib import resources
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
from typing import Any, Iterable

from .corpus import CORPUS_SCHEMA, CorpusError, _decode, _validate_declaration

EXPORT_SCHEMA = "lpaf-export-v0.1"
MAX_RECORD_BYTES = 64 * 1024 * 1024
STDERR_TAIL_BYTES = 8192


class ExportError(CorpusError):
    """Structured extraction failure; a failed run never publishes its output."""


def _strings(value: Iterable[str], name: str, *, required: bool = False) -> list[str]:
    if isinstance(value, (str, bytes)):
        raise ExportError("invalid_argument", f"{name} must be an iterable of strings", argument=name)
    try:
        result = list(value)
    except TypeError as exc:
        raise ExportError("invalid_argument", f"Invalid {name}", argument=name) from exc
    if (required and not result) or any(not isinstance(x, str) or not x.strip() or "\0" in x for x in result):
        raise ExportError("invalid_argument", f"{name} requires nonempty strings", argument=name)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state(project: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"head": None, "dirty": None}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True,
                              text=True, timeout=5, check=True).stdout.strip()
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
            result["head"] = head
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                                cwd=project, capture_output=True, text=True, timeout=5, check=True)
        result["dirty"] = bool(status.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def _stderr_tail(path: Path, *, label: str = "stderr") -> str:
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        length = stream.tell()
        stream.seek(max(0, length - STDERR_TAIL_BYTES))
        text = stream.read(STDERR_TAIL_BYTES).decode("utf-8", errors="replace")
    return (f"[earlier {label} omitted]\n" if length > STDERR_TAIL_BYTES else "") + text


def _kill_group(process: subprocess.Popen) -> None:
    """Terminate the POSIX session, including descendants, then reap the leader."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def _check_and_copy(raw_path: Path, final_path: Path, provenance: dict[str, Any], *,
                    modules: list[str], prefixes: list[str], names: list[str],
                    max_declarations: int, max_nodes: int,
                    expected_version: str | None) -> tuple[int, bool, str]:
    """Validate one record at a time, attach actual runner provenance, and hash."""
    header = footer = None
    count = 0
    identities: set[str] = set()
    digest = hashlib.sha256()
    with raw_path.open("rb") as source, final_path.open("wb") as destination:
        line_number = 0
        while True:
            raw = source.readline(MAX_RECORD_BYTES + 1)
            if not raw:
                break
            line_number += 1
            if len(raw) > MAX_RECORD_BYTES:
                raise ExportError("record_limit", "Export record exceeds the validation byte limit", line=line_number)
            if not raw.strip():
                continue
            try:
                record = _decode(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ExportError("invalid_export", "Exporter did not produce UTF-8 JSONL", line=line_number) from exc
            if not isinstance(record, dict) or footer is not None:
                raise ExportError("invalid_export", "Invalid record or data after footer", line=line_number)
            if header is None:
                if record.get("record") != "header" or record.get("schema") != CORPUS_SCHEMA:
                    raise ExportError("invalid_export", "Missing supported corpus header")
                if record.get("evidence") != "lean_elaborated" or record.get("not_proof_check") is not True:
                    raise ExportError("invalid_export", "Missing elaborated evidence metadata")
                version = record.get("lean_version")
                if not isinstance(version, str) or not version:
                    raise ExportError("invalid_export", "Missing actual Lean version")
                if expected_version is not None and version != expected_version:
                    raise ExportError("toolchain_mismatch", "Exporter Lean version disagrees with lean-toolchain",
                                      expected=expected_version, actual=version)
                for key, expected in (("modules", modules), ("prefixes", prefixes), ("names", names)):
                    if record.get(key) != expected:
                        raise ExportError("invalid_export", "Exporter selection disagrees with request", field=key)
                header = record
                provenance["lean_version"] = version
                provenance["toolchain_version_check"] = "matched" if expected_version is not None else "unparsed_toolchain_tag"
                record["provenance"] = provenance
                raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            elif record.get("record") == "declaration":
                _validate_declaration(record, max_nodes)
                if record["evidence"] != "lean_elaborated":
                    raise ExportError("invalid_export", "Exporter produced non-elaborated declaration evidence")
                if record["id"] in identities:
                    raise ExportError("duplicate_declaration", "Exporter repeated a declaration identity", declaration=record["id"])
                identities.add(record["id"])
                count += 1
                if count > max_declarations:
                    raise ExportError("invalid_export", "Exporter exceeded the declaration limit")
            elif record.get("record") == "footer":
                footer = record
            else:
                raise ExportError("invalid_export", "Unexpected record kind", line=line_number)
            if not raw.endswith(b"\n"):
                raw += b"\n"
            destination.write(raw)
            digest.update(raw)
        if header is None or footer is None:
            raise ExportError("incomplete_export", "Successful process did not provide a complete JSONL envelope")
        if type(footer.get("declarations")) is not int or footer["declarations"] != count:
            raise ExportError("invalid_export", "Footer declaration count disagrees with records")
        if type(footer.get("complete")) is not bool:
            raise ExportError("invalid_export", "Footer must state selection completeness")
        matched = footer.get("matched_declarations")
        if type(matched) is not int or matched < count or footer["complete"] != (matched <= max_declarations):
            raise ExportError("invalid_export", "Invalid matched declaration count or completeness flag")
        if count != min(matched, max_declarations):
            raise ExportError("invalid_export", "Export stopped before the selected declaration limit")
        if footer.get("limits") != {"max_declarations": max_declarations, "max_nodes_per_expression": max_nodes}:
            raise ExportError("invalid_export", "Exporter limits disagree with the request")
        destination.flush()
        os.fsync(destination.fileno())
    return count, footer["complete"], digest.hexdigest()


def export_lean(project_dir: str | Path, output_path: str | Path, *, modules: Iterable[str],
                prefixes: Iterable[str] = (), names: Iterable[str] = (),
                runner: Iterable[str] = ("lake", "env", "lean"),
                max_declarations: int = 1000, max_nodes: int = 100000,
                timeout: float = 300, lean_path: str | Path | None = None) -> dict[str, Any]:
    """Export built modules under an explicitly pinned project's Lean environment.

    The output path must be new. A temporary file is published atomically only
    after process success, version agreement and complete transport validation.
    `complete=false` in a valid footer is an intentional bounded selection.
    `lean_path` only affects the child's LEAN_PATH. On POSIX, timeout cleanup
    kills the process group; other platforms can only guarantee leader cleanup.
    """
    selected_modules = _strings(modules, "modules", required=True)
    selected_prefixes = _strings(prefixes, "prefixes")
    selected_names = _strings(names, "names")
    command = _strings(runner, "runner", required=True)
    for key, value in (("max_declarations", max_declarations), ("max_nodes", max_nodes)):
        if type(value) is not int or value < 1:
            raise ExportError("invalid_argument", "Limits must be positive integers", argument=key)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ExportError("invalid_argument", "timeout must be a finite positive duration in seconds")
    project = Path(project_dir).expanduser().resolve()
    destination = Path(output_path).expanduser().absolute()
    if not project.is_dir():
        raise ExportError("invalid_project", "Project directory does not exist", path=str(project))
    if destination.exists() or destination.is_symlink():
        raise ExportError("destination_exists", "Choose a new output path; existing exports are not overwritten", path=str(destination))
    toolchain = project / "lean-toolchain"
    if not toolchain.is_file():
        raise ExportError("missing_toolchain", "The analyzed project must provide lean-toolchain")
    try:
        toolchain_text = toolchain.read_text(encoding="utf-8").strip()
    except UnicodeError as exc:
        raise ExportError("invalid_toolchain", "lean-toolchain is not UTF-8") from exc
    if not toolchain_text:
        raise ExportError("invalid_toolchain", "lean-toolchain is empty")
    version_match = re.fullmatch(r"(?:leanprover/lean4:)?v?(\d+\.\d+\.\d+(?:-rc\d+)?)", toolchain_text)
    expected_version = version_match.group(1) if version_match else None
    manifest = project / "lake-manifest.json"
    provenance: dict[str, Any] = {
        "lean_toolchain": {"value": toolchain_text, "sha256": _sha256(toolchain)},
        "lake_manifest_sha256": _sha256(manifest) if manifest.is_file() else None,
        "git_before_export": _git_state(project),
        "compiled_artifact_authentication": "not_performed",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaries: list[Path] = []
    process = None
    try:
        for label in ("stdout", "stderr", "checked"):
            fd, temporary = tempfile.mkstemp(prefix=f".lpaf-export-{label}-", dir=destination.parent)
            os.close(fd)
            temporaries.append(Path(temporary))
        raw_path, stderr_path, checked_path = temporaries
        resource = resources.files("lean_proof_analysis").joinpath("lean/Export.lean")
        with resources.as_file(resource) as exporter:
            provenance["exporter_sha256"] = _sha256(exporter)
            environment = dict(os.environ)
            executable = Path(command[0]).expanduser()
            if executable.is_absolute():
                environment["PATH"] = str(executable.parent) + os.pathsep + environment.get("PATH", "")
            if lean_path is not None:
                environment["LEAN_PATH"] = str(Path(lean_path).expanduser().absolute())
            argv = [*command, "--run", str(exporter)]
            for flag, values in (("--module", selected_modules), ("--prefix", selected_prefixes), ("--name", selected_names)):
                for value in values:
                    argv.extend([flag, value])
            argv.extend(["--max-declarations", str(max_declarations), "--max-nodes", str(max_nodes)])
            with raw_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(argv, cwd=project, env=environment, stdout=stdout, stderr=stderr,
                                           start_new_session=os.name == "posix")
                try:
                    returncode = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired as exc:
                    _kill_group(process)
                    raise ExportError("export_timeout", "Lean export exceeded its time budget", timeout_seconds=timeout,
                                      stderr_tail=_stderr_tail(stderr_path), stdout_tail=_stderr_tail(raw_path, label="stdout")) from exc
                if returncode != 0:
                    raise ExportError("export_process_failed", "Lean exporter exited unsuccessfully", returncode=returncode,
                                      stderr_tail=_stderr_tail(stderr_path), stdout_tail=_stderr_tail(raw_path, label="stdout"))
        if _sha256(toolchain) != provenance["lean_toolchain"]["sha256"]:
            raise ExportError("project_changed", "lean-toolchain changed during export")
        final_manifest = _sha256(manifest) if manifest.is_file() else None
        if final_manifest != provenance["lake_manifest_sha256"]:
            raise ExportError("project_changed", "lake-manifest.json changed during export")
        count, complete, digest = _check_and_copy(
            raw_path, checked_path, provenance, modules=selected_modules, prefixes=selected_prefixes,
            names=selected_names, max_declarations=max_declarations, max_nodes=max_nodes,
            expected_version=expected_version,
        )
        try:
            os.link(checked_path, destination)
        except FileExistsError as exc:
            raise ExportError("destination_exists", "Output path appeared during export", path=str(destination)) from exc
        return {"schema": EXPORT_SCHEMA, "operation": "export_lean", "output": str(destination),
                "sha256": digest, "declarations": count, "selection_complete": complete,
                "not_proof_check": True, "provenance": provenance,
                "limits": {"max_declarations": max_declarations, "max_nodes": max_nodes,
                           "timeout_seconds": timeout, "max_record_bytes": MAX_RECORD_BYTES}}
    except OSError as exc:
        raise ExportError("export_io_error", str(exc)) from exc
    finally:
        if process is not None and process.poll() is None:
            _kill_group(process)
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
