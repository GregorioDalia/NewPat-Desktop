"""Bounded, explicit support bundles, never a recursive copy of genomic data.

Logs and provenance may contain local paths and sample names. Their inclusion is
intentional after the user's native Save dialog; this is not anonymisation.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import islice
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile
import zipfile

from nipat import __version__
from nipat.branding import PRODUCT_NAME
from nipat.distribution import UNIX_DIRECTORY
from nipat.errors import ValidationError
from .results import _is_link, _scoped


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES = 128
MAX_STEPS = 32
WORKSPACE_FILES = (
    "logs/gui.log", ".runtime/macos/setup.log", ".runtime/macos/runtime.json",
    ".runtime/linux/setup.log", ".runtime/linux/state.json",
    ".runtime/windows/setup.log", ".runtime/windows/runtime.json",
)
RUN_FILES = (
    "run.json", "execution.log", "performance/summary.json",
    "performance/engine/summary.json", "performance/engine/phases.jsonl",
    "output/workflow/workflow-state.json", "work/input-validation.json",
    "work/dnp-blocks.json", "work/dnp-pileup.json", "work/dnp-acquisition-budget.json",
)
STEP_FILES = (
    "command.log", "work/input-validation.json", "work/dnp-blocks.json",
    "work/dnp-pileup.json", "work/dnp-acquisition-budget.json",
)


@contextmanager
def _regular_stream(path: Path):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("not a regular diagnostic file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def _snapshot_json(path: Path, limit: int) -> bytes:
    """Reject oversized/non-object JSON instead of cutting a document mid-value."""
    with _regular_stream(path) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("document exceeds diagnostic size limit")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("diagnostic metadata must be a JSON object")
    # Workflow aggregation is a result, not needed to diagnose the execution.
    if path.name == "workflow-state.json":
        value.pop("snp_summary", None)
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def write_bundle(destination: Path, layout, *, resources: dict, run_dir: Path | None = None) -> dict:
    """Write one atomic ZIP, using only allowlisted metadata and log paths."""
    destination = Path(destination).expanduser()
    if _is_link(destination):
        raise ValidationError("L’archivio diagnostico non può sostituire un collegamento.")
    destination = destination.resolve()
    if destination.suffix.lower() != ".zip":
        raise ValidationError("Salva la diagnostica in un archivio .zip.")
    protected = [layout.project_dir, layout.data_dir, layout.runs_dir]
    if run_dir is not None:
        protected.append(run_dir)
    if any(destination.is_relative_to(Path(root).resolve()) for root in protected):
        raise ValidationError("Salva la diagnostica fuori dalle cartelle dell’applicazione, dei dati e dei risultati.")

    files: list[tuple[str, bytes]] = []
    observations: list[dict] = []
    total = 0

    def collect(root: Path, relative: str, prefix: str):
        nonlocal total
        entry = {"path": prefix + "/" + relative}
        try:
            root = Path(root).absolute()
            if _is_link(root) or root.resolve() != root:
                raise ValueError("linked diagnostic root")
            path = _scoped(root, relative)
            if not path.exists():
                return
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("not a regular file")
            remaining = MAX_TOTAL_BYTES - total
            limit = min(MAX_FILE_BYTES, remaining)
            if len(files) >= MAX_FILES or limit <= 0:
                raise ValueError("bundle size or file count limit reached")
            if path.suffix == ".json":
                raw = _snapshot_json(path, limit)
                if len(raw) > limit:
                    raise ValueError("formatted metadata exceeds diagnostic size limit")
                entry["truncated"] = False
            else:
                # Keep the latest evidence if setup/gui/execution logs are large.
                with _regular_stream(path) as stream:
                    size = os.fstat(stream.fileno()).st_size
                    start = max(0, size - limit)
                    stream.seek(start)
                    raw = stream.read(limit)
                entry["truncated"] = start > 0
            if _is_link(path) or path.resolve() != path:
                raise ValueError("diagnostic path changed to a link")
            files.append((entry["path"], raw))
            total += len(raw)
            entry.update(status="included", bytes=len(raw))
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            entry.update(status="omitted", reason=str(exc))
        observations.append(entry)

    workspace = Path(layout.workspace_dir)
    for relative in WORKSPACE_FILES:
        collect(workspace, relative, "application")
    project = Path(layout.project_dir)
    for relative in (".distribution/macos-manifest.json", ".distribution/installer-manifest.json",
                     ".runtime/installer/setup.log"):
        collect(project, relative, "installation")
    # The packaged Linux launcher uses the standard per-user XDG state root.
    # Its suffix and filenames are fixed; no frontend-controlled path is read.
    if sys.platform == "linux":
        state_home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
        if state_home.is_absolute():
            for relative in ("setup.log", "state.json"):
                collect(state_home / UNIX_DIRECTORY, relative, "runtime/linux")
    if run_dir is not None:
        run_dir = Path(run_dir).absolute()
        for relative in RUN_FILES:
            collect(run_dir, relative, "experiment")
        try:
            steps = _scoped(run_dir, "output/workflow/steps")
            if steps.is_dir():
                with os.scandir(steps) as stream:
                    candidates = list(islice(stream, MAX_STEPS + 1))
                for entry in sorted(candidates[:MAX_STEPS], key=lambda item: item.name):
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    for relative in STEP_FILES:
                        collect(run_dir, "output/workflow/steps/" + entry.name + "/" + relative, "experiment")
                if len(candidates) > MAX_STEPS:
                    observations.append({"path": "experiment/output/workflow/steps", "status": "omitted",
                                         "reason": "additional workflow steps exceed diagnostic count limit"})
        except (OSError, ValueError) as exc:
            observations.append({"path": "experiment/output/workflow/steps", "status": "omitted", "reason": str(exc)})

    manifest = {
        "schema_version": 1, "product": PRODUCT_NAME, "version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "system": {"platform": sys.platform, "release": platform.release(),
                   "machine": platform.machine(), "python": platform.python_version()},
        "installation": {"project_dir": str(layout.project_dir), "workspace_dir": str(workspace)},
        "resources": resources, "experiment": run_dir.name if run_dir else None,
        "scope": "Allowlisted logs and metadata only; no input BAM/FASTA or scientific result tables. Logs may contain local paths and sample names.",
        "limits": {"file_bytes": MAX_FILE_BYTES, "total_file_bytes": MAX_TOTAL_BYTES,
                   "files": MAX_FILES, "workflow_steps": MAX_STEPS},
        "files": observations,
    }
    encoded_manifest = (json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if len(encoded_manifest) > MAX_FILE_BYTES:
        raise ValidationError("Il riepilogo diagnostico supera il limite di dimensione.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("diagnostics.json", encoded_manifest)
            for name, raw in files:
                archive.writestr(name, raw)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(destination), "files": len(files) + 1,
            "omitted": sum(item["status"] == "omitted" for item in observations)}


def open_directory(path: Path) -> None:
    """Open a validated directory in the native file manager, without a shell."""
    import subprocess

    path = Path(path)
    if not path.is_dir() or _is_link(path) or path.resolve() != path:
        raise ValidationError("La cartella dell’esperimento non è disponibile.")
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.run(["/usr/bin/open", str(path)], check=True, timeout=15)
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(path)], check=True, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        else:
            raise ValidationError("Apertura della cartella non disponibile su questo sistema.")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValidationError(f"Impossibile aprire la cartella dell’esperimento: {path}") from exc
