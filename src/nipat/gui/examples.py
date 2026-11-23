"""Copy the verified synthetic trio supplied with the desktop distribution."""
from __future__ import annotations

from contextlib import ExitStack, suppress
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from nipat.errors import ValidationError


ARCHIVE_NAME = "newpat-synthetic-trio.zip"
FOLDER_NAME = "synthetic-trio"


def _remove_empty(path: Path) -> None:
    with suppress(OSError):
        path.rmdir()


def save_example_data(project: Path, parent: Path, language: str) -> Path:
    en = language == "en"
    target = parent / FOLDER_NAME
    archive = project / "examples" / ARCHIVE_NAME
    invalid = ("The example data could not be verified." if en else
               "Impossibile verificare i dati di esempio.")
    try:
        recorded = archive.with_suffix(".zip.sha256").read_text(encoding="ascii").split()
        with archive.open("rb") as stream:
            if recorded != [hashlib.file_digest(stream, "sha256").hexdigest(), ARCHIVE_NAME]:
                raise ValidationError(invalid)
            stream.seek(0)
            with zipfile.ZipFile(stream) as bundle, ExitStack() as rollback:
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
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        detail = "Unable to save example data" if en else "Impossibile salvare i dati di esempio"
        raise ValidationError(f"{detail}: {exc}") from exc
    return target
