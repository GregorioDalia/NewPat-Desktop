"""Explicit, cancellable installation of pinned UCSC human reference FASTAs."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import gzip
import hashlib
from pathlib import Path
import shutil
import threading
from urllib.request import urlopen

from nipat.errors import ValidationError
from nipat.preferences import settings_file_lock


@dataclass(frozen=True)
class ReferenceSource:
    name: str
    packed_size: int
    packed_sha256: str
    fasta_size: int
    fasta_sha256: str
    index_sha256: str

    @property
    def url(self):
        return f"https://hgdownload.soe.ucsc.edu/goldenPath/{self.name}/bigZips/initial/{self.name}.fa.gz"


# Whole archival files from UCSC bigZips/initial. Both compressed files were
# checked against md5sum.txt there. FAI digests come from samtools faidx on those FASTAs.
SOURCES = {
    "grch37": ReferenceSource(
        "hg19", 948731419, "ac73947d38df63ccb00724520a5c31d880c1ca423702ca7ccb7e6c2182a362d9",
        3199905909, "92b96d16b307d824f3b6b9dc63feb237a75226f82ca2166d51ecec039bee4449",
        "63689f241ff7c9e8364142f4b519dcd6d208e51d85f1ce5e906dff9c10358491"),
    "grch38": ReferenceSource(
        "hg38", 983659424, "c1dd87068c254eb53d944f71e51d1311964fce8de24d6fc0effc9c61c01527d4",
        3273481150, "5be01555d98347fdb3714dc84c6f77c9d8bc774adcf32c6f7a8fa06f5baf5e51",
        "3b425de206296a5c8053023fa5ca61da43cfe78c1737c12e58c83367c7e83c21"),
}
CHUNK = 1024 * 1024
ACTIVE = {"downloading", "unpacking", "indexing"}


class _Cancelled(Exception):
    pass


def _verified_copy(source, destination, expected_size, expected_digest, check_cancel, progress):
    size = 0
    digest = hashlib.sha256()
    while True:
        check_cancel()
        block = source.read(CHUNK)
        if not block:
            break
        size += len(block)
        if size > expected_size:
            raise ValueError("The reference is larger than its UCSC record.")
        if destination:
            destination.write(block)
        digest.update(block)
        progress(size)
    if size != expected_size or digest.hexdigest() != expected_digest:
        raise ValueError("The reference does not match its UCSC size and SHA-256.")


def _install(catalog, build, source, cancel, update, language):
    from .references import build_fasta_index

    def check_cancel():
        if cancel.is_set():
            raise _Cancelled()

    def phase_progress(size):
        update(phase_bytes=size)

    def ensure_index(fasta):
        update(status="indexing", phase_bytes=0, phase_total_bytes=source.fasta_size)
        index = build_fasta_index(fasta, check_cancel=check_cancel, progress=phase_progress, language=language)
        with index.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source.index_sha256:
                raise ValueError("Unexpected FASTA index for the UCSC reference.")
        check_cancel()

    root = catalog.path.parent / "reference-genomes"
    root.mkdir(parents=True, exist_ok=True)
    final = root / source.name
    name = source.name + ".fa"
    with settings_file_lock(root / source.name):
        check_cancel()
        if final.exists():
            # A previous process may have published the completed directory
            # immediately before exiting, without registering it with the UI.
            update(status="unpacking", received_bytes=source.packed_size, phase_bytes=0, phase_total_bytes=source.fasta_size)
            try:
                with (final / name).open("rb") as fasta:
                    _verified_copy(fasta, None, source.fasta_size, source.fasta_sha256,
                                   check_cancel, phase_progress)
                ensure_index(final / name)
            except (ValueError, FileNotFoundError) as exc:
                message = (f"The installed reference changed. Move {final} and retry the download."
                           if language == "en" else
                           f"Il riferimento installato è cambiato. Sposta {final} e riprova il download.")
                raise ValidationError(message) from exc
            return catalog.register(build, final / name)

        temporary = root / (source.name + ".partial")
        # A stopped process leaves no valid catalog entry. The per-build OS
        # lock permits the next process to recover its private staging area.
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            required = source.packed_size + source.fasta_size + 16 * 1024 * 1024
            if shutil.disk_usage(root).free < required:
                gib = required / (1024 ** 3)
                message = (f"At least {gib:.2f} GiB of disk space is required." if language == "en"
                           else f"Servono almeno {gib:.2f} GiB di spazio libero sul disco.")
                raise ValidationError(message)
            archive = temporary / (name + ".gz")
            with closing(urlopen(source.url, timeout=30)) as incoming, archive.open("xb") as output:
                _verified_copy(incoming, output, source.packed_size, source.packed_sha256,
                               check_cancel, lambda n: update(received_bytes=n))
            update(status="unpacking", phase_bytes=0, phase_total_bytes=source.fasta_size)
            with gzip.open(archive, "rb") as packed, (temporary / name).open("xb") as output:
                _verified_copy(packed, output, source.fasta_size, source.fasta_sha256,
                               check_cancel, phase_progress)
            archive.unlink()
            ensure_index(temporary / name)
            temporary.rename(final)
            return catalog.register(build, final / name)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


class ReferenceDownloads:
    def __init__(self, catalog):
        self._catalog = catalog
        self._lock = threading.RLock()
        self._states = {}
        self._cancellations = {}

    def call(self, action, params):
        build = params.get("build")
        language = params.get("language", "it")
        if (set(params) - {"build", "language"} or not isinstance(build, str)
                or build not in SOURCES or language not in ("it", "en")):
            raise ValidationError("Seleziona GRCh37 o GRCh38. / Select GRCh37 or GRCh38.")
        with self._lock:
            state = self._states.setdefault(build, {
                "build": build, "status": "idle", "received_bytes": 0,
                "total_bytes": SOURCES[build].packed_size, "entry": None, "error": None,
            })
            if action == "cancel" and state["status"] in ACTIVE:
                self._cancellations[build].set()
            elif action == "start" and state["status"] not in ACTIVE:
                cancel = threading.Event()
                self._cancellations[build] = cancel
                state.update(status="downloading", received_bytes=0, phase_bytes=0, phase_total_bytes=0, entry=None, error=None)
                threading.Thread(target=self._run, args=(build, language, cancel),
                                 name=f"NewPat-{build}", daemon=False).start()
            return state.copy()

    def _run(self, build, language, cancel):
        def update(**fields):
            with self._lock:
                self._states[build].update(fields)
        try:
            entry = _install(self._catalog(language), build, SOURCES[build], cancel, update, language)
        except _Cancelled:
            update(status="cancelled")
        except Exception as exc:
            # A worker must always publish a terminal status to the desktop,
            # including on HTTP, gzip, catalog or filesystem failures.
            message = "Unable to install the reference" if language == "en" else "Impossibile installare il riferimento"
            update(status="failed", error=f"{message}: {exc}")
        else:
            update(status="ready", entry=entry)

    def close(self):
        with self._lock:
            for cancel in self._cancellations.values():
                cancel.set()
