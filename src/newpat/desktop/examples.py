"""Copy the verified synthetic trio supplied with the desktop distribution."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, suppress
import hashlib
from itertools import count
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from newpat.errors import ValidationError
from newpat.experiments.options import ExecutionOptions
from newpat.paths import ProjectLayout
from newpat.preferences import settings_file_lock
from newpat.scientific_options import WORKFLOWS
from newpat_scientific.settings import defaults


ARCHIVE_NAME = "newpat-synthetic-trio.zip"
FOLDER_NAME = "synthetic-trio"
DEMO_SAMPLES = ("mother", "father", "child")
DEMO_INPUTS = (
    *(f"alignments/{sample}.{extension}" for sample in DEMO_SAMPLES for extension in ("bam", "bam.bai")),
    "reference/synthetic.fa", "reference/synthetic.fa.fai", "panels/dnp.tsv", "panels/snp.tsv",
)


def _remove_empty(path: Path) -> None:
    with suppress(OSError):
        path.rmdir()


@contextmanager
def _verified_bundle(project: Path, language: str):
    archive = project / "examples" / ARCHIVE_NAME
    invalid = ("The example data could not be verified." if language == "en" else
               "Impossibile verificare i dati di esempio.")
    try:
        recorded = archive.with_suffix(".zip.sha256").read_text(encoding="ascii").split()
        with archive.open("rb") as stream:
            if recorded != [hashlib.file_digest(stream, "sha256").hexdigest(), ARCHIVE_NAME]:
                raise ValidationError(invalid)
            stream.seek(0)
            with zipfile.ZipFile(stream) as bundle:
                yield bundle
    except (OSError, UnicodeError, KeyError, zipfile.BadZipFile) as exc:
        detail = "Unable to open or copy example data" if language == "en" else "Impossibile aprire o copiare i dati di esempio"
        raise ValidationError(f"{detail}: {exc}") from exc


def save_example_data(project: Path, parent: Path, language: str) -> Path:
    en = language == "en"
    target = parent / FOLDER_NAME
    invalid = ("The example data could not be verified." if en else
               "Impossibile verificare i dati di esempio.")
    with _verified_bundle(project, language) as bundle, ExitStack() as rollback:
        files = {}
        for entry in bundle.infolist():
            path = PurePosixPath(entry.filename)
            if (path.parts[:1] != (FOLDER_NAME,) or len(path.parts) < 2
                    or set(path.parts) & {".", ".."} or path.as_posix() != entry.filename
                    or "\\" in entry.filename or ":" in entry.filename or entry.is_dir()):
                raise ValidationError(invalid)
            relative = Path(*path.parts[1:])
            if relative in files:
                raise ValidationError(invalid)
            files[relative] = entry
        if Path("SHA256SUMS") not in files:
            raise ValidationError(invalid)
        try:
            target.mkdir()
        except FileExistsError as exc:
            conflict = (f"{target} already exists. Select a different folder." if en else
                        f"{target} esiste già. Scegli un’altra cartella.")
            raise ValidationError(conflict) from exc
        rollback.callback(_remove_empty, target)
        directories = {directory for path in files for directory in path.parents if directory.parts}
        for directory in sorted(directories, key=lambda item: len(item.parts)):
            destination = target / directory
            destination.mkdir()
            rollback.callback(_remove_empty, destination)
        for path, entry in files.items():
            destination = target / path
            with bundle.open(entry) as source, destination.open("xb") as copy:
                rollback.callback(destination.unlink, missing_ok=True)
                shutil.copyfileobj(source, copy)
        rollback.pop_all()
    return target


def _demo_directory(workspace: Path, inputs: dict[str, bytes], language: str) -> Path:
    # The ten small files form a complete set (including the only admissible indices).
    cache = workspace.resolve() / "demo-inputs"
    if cache.is_symlink() or cache.is_junction():
        raise ValidationError("The demo folder cannot be a link." if language == "en" else
                              "La cartella della demo non può essere un collegamento.")
    with settings_file_lock(cache / "synthetic-trio"):
        for number in count(1):
            target = cache / f"trio-{number}"
            try:
                target.mkdir()
            except FileExistsError:
                # Preserve edits and avoid ambiguous alternate indices in older copies.
                if _matches_inputs(target, inputs):
                    return target
            else:
                with ExitStack() as rollback:
                    rollback.callback(_remove_empty, target)
                    for name, data in inputs.items():
                        path = target / name
                        with path.open("xb") as stream:
                            rollback.callback(path.unlink, missing_ok=True)
                            stream.write(data)
                    rollback.pop_all()
                return target


def _matches_inputs(target: Path, inputs: dict[str, bytes]) -> bool:
    try:
        if target.is_symlink() or target.is_junction() or not target.is_dir():
            return False
        entries = list(target.iterdir())
        return ({p.name for p in entries} == inputs.keys()
                and all(not p.is_symlink() and p.is_file() and p.stat().st_size == len(inputs[p.name])
                        and p.read_bytes() == inputs[p.name] for p in entries))
    except OSError:
        return False


def demo_draft(layout: ProjectLayout, language: str) -> dict:
    with _verified_bundle(layout.project_dir, language) as bundle:
        inputs = {Path(name).name: bundle.read(f"{FOLDER_NAME}/{name}") for name in DEMO_INPUTS}
    target = _demo_directory(layout.workspace_dir, inputs, language)
    return {
        "name": "DNP and SNP demo" if language == "en" else "Demo DNP e SNP",
        "caller": "both",
        "samples": [{"id": sample, "kind": "bam", "path": str(target / f"{sample}.bam")} for sample in DEMO_SAMPLES],
        "reference": str(target / "synthetic.fa"),
        "resources": {marker.upper(): {"panel": str(target / f"{marker}.tsv")} for marker in ("dnp", "snp")},
        "branches": {"DNP": [], "SNP": []},
        "families": {"cpi": [], "cpin": []},
        "scientific_settings": {module: defaults(module) for module in WORKFLOWS},
        "execution": ExecutionOptions().as_dict(),
    }
