"""Persistent selections of local, indexed human and custom reference genomes."""
from __future__ import annotations

from contextlib import nullcontext
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import zlib
from uuid import uuid4

from nipat.errors import ValidationError
from nipat.preferences import settings_file_lock
from .igv import LocalIGV


# Lengths of primary nuclear chromosomes 1..22, X, Y in the UCSC hg19/hg38
# chrom.sizes tables. This identifies the coordinate family, not every sequence
# or distribution within it (decoys, mitochondrial sequences and naming vary).
_PRIMARY = {
    "grch37": (249250621, 243199373, 198022430, 191154276, 180915260, 171115067,
               159138663, 146364022, 141213431, 135534747, 135006516, 133851895,
               115169878, 107349540, 102531392, 90354753, 81195210, 78077248,
               59128983, 63025520, 48129895, 51304566, 155270560, 59373566),
    "grch38": (248956422, 242193529, 198295559, 190214555, 181538259, 170805979,
               159345973, 145138636, 138394717, 133797422, 135086622, 133275309,
               114364328, 107043718, 101991189, 90338345, 83257441, 80373285,
               58617616, 64444167, 46709983, 50818468, 156040895, 57227415),
}
# RefSeq chromosome accession versions from the corresponding UCSC chromAlias tables.
_REFSEQ_VERSIONS = {
    "grch37": (10, 11, 11, 11, 9, 11, 13, 10, 11, 10, 9, 11, 10, 8, 9, 9, 10, 9, 9, 10, 8, 10, 10, 9),
    "grch38": (11, 12, 12, 12, 10, 12, 14, 11, 12, 11, 10, 12, 11, 9, 10, 10, 11, 10, 10, 11, 9, 11, 11, 10),
}
_BUILDS = {"grch37": "GRCh37 / hg19", "grch38": "GRCh38 / hg38", "custom": "Custom FASTA"}
_COMPRESSED = {".gz", ".bgz", ".bgzf"}
_SEQ = re.compile(rb"[A-Za-z.*-]+")
_CONTIG = re.compile(rb"[A-Za-z0-9_.-]+")
_NUCLEAR = re.compile(r"(chr)?([1-9]|1[0-9]|2[0-2]|X|Y)\Z")
_REFSEQ = re.compile(r"NC_0000(0[1-9]|1[0-9]|2[0-4])\.([0-9]+)\Z")
_FULL_PREVIEW_LIMIT = 1024 * 1024


def _text(language, italian, english):
    return english if language == "en" else italian


def _stamp(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def reference_files(fasta):
    yield fasta
    yield Path(str(fasta) + ".fai")
    if fasta.suffix.lower() in _COMPRESSED:
        yield Path(str(fasta) + ".gzi")


def _file_sha256(path, *, preview=False):
    with path.open("rb") as stream:
        if preview and (size := os.fstat(stream.fileno()).st_size) > _FULL_PREVIEW_LIMIT:
            # Listing a human reference should not stream gigabytes. Selection
            # always checks the complete file, including these unsampled spans.
            window = 4096
            digest = hashlib.sha256()
            for offset in (0, (size - window) // 2, size - window):
                stream.seek(offset)
                digest.update(stream.read(window))
            return digest.hexdigest()
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _content_hashes(fasta, *, preview=False):
    return {p.name: _file_sha256(p, preview=preview and p == fasta) for p in reference_files(fasta)}


def _fail_fasta(language):
    return ValidationError(_text(language, "FASTA non indicizzabile. Verifica intestazioni, sequenze e lunghezza delle righe.",
                                 "Cannot index this FASTA. Check the headers, sequences and line lengths."))


def _index_rows(fasta, language, check_cancel, progress):
    """Stream a plain FASTA, allowing CRLF, short last lines and unwrapped contigs."""
    names = set()
    name = None
    bases = width = total = previous_bases = previous_width = 0
    offset = position = 0
    next_report = 0
    ended = False
    with fasta.open("rb") as stream:
        while raw := stream.readline(1024 * 1024):
            if position >= next_report:
                if check_cancel:
                    check_cancel()
                if progress:
                    progress(position)
                next_report = position + 4 * 1024 * 1024
            position += len(raw)
            if raw.startswith(b">"):
                if name is not None:
                    if not total:
                        raise _fail_fasta(language)
                    yield name, total, offset, bases, width
                token = raw[1:].split(maxsplit=1)
                if not token or len(raw) > 8192 or not _CONTIG.fullmatch(token[0]):
                    raise _fail_fasta(language)
                name = token[0].decode("ascii")
                if name in names or len(names) >= 100000:
                    raise _fail_fasta(language)
                names.add(name)
                ended = False
                bases = width = total = 0
                offset = position
                continue
            if raw in (b"\n", b"\r\n") and total:
                ended = True
                continue
            if name is None or ended or (total and (previous_bases, previous_width) != (bases, width)):
                raise _fail_fasta(language)
            line_width = line_bases = 0
            while raw:
                # Continue an unusually long sequence line in bounded pieces.
                part = raw.rstrip(b"\r\n")
                if not _SEQ.fullmatch(part):
                    raise _fail_fasta(language)
                line_bases += len(part)
                line_width += len(raw)
                if raw.endswith(b"\n") or len(raw) < 1024 * 1024:
                    break
                raw = stream.readline(1024 * 1024)
                position += len(raw)
                if raw == b"\n" or raw == b"\r\n":
                    line_width += len(raw)
                    break
            if not total:
                bases, width = line_bases, line_width
            elif line_bases > bases:
                raise _fail_fasta(language)
            previous_bases, previous_width = line_bases, line_width
            total += line_bases
    if name is None or not total:
        raise _fail_fasta(language)
    yield name, total, offset, bases, width
    if check_cancel:
        check_cancel()
    if progress:
        progress(position)


def build_fasta_index(fasta: Path, *, language="it", check_cancel=None, progress=None) -> Path:
    """Create the adjacent FAI on explicit import, without replacing another index."""
    index = Path(str(fasta) + ".fai")
    if index.is_file():
        return index
    start = _stamp(fasta)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=fasta.parent, prefix=".newpat-fai-", delete=False,
                                         mode="w", encoding="ascii", newline="\n") as output:
            temporary = Path(output.name)
            for row in _index_rows(fasta, language, check_cancel, progress):
                output.write("\t".join(map(str, row)) + "\n")
        if start != _stamp(fasta):
            raise ValidationError(_text(language, "Il FASTA è cambiato durante l’indicizzazione.",
                                        "The FASTA changed during indexing."))
        # A competing importer may have completed the same file. Serialize just
        # publication, so neither readers nor concurrent sessions see a partial FAI.
        with settings_file_lock(index):
            if not index.exists():
                os.replace(temporary, index)
        return index
    except PermissionError as exc:
        raise ValidationError(_text(language, "Per creare il .fai usa una cartella scrivibile o affianca al FASTA il suo indice.",
                                    "To create the .fai, use a writable folder or place its index beside the FASTA.")) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class _HashedReader(io.RawIOBase):
    """Hash the on-disk representation while validating the FASTA sequence."""
    def __init__(self, source, digest):
        self.source = source
        self.digest = digest

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.source.readinto(buffer)
        self.digest.update(memoryview(buffer)[:count])
        return count


def _verify_gzi(source, gzi, error):
    # Compare every indexed block with the BGZF block size and gzip ISIZE.
    # Both the first (implicit) record and a terminal empty block need no entry.
    size = os.fstat(source.fileno()).st_size
    compressed = uncompressed = 0
    with gzi.open("rb") as index:
        count = index.read(8)
        if (len(count) != 8 or gzi.stat().st_size > 32 * 1024 * 1024
                or gzi.stat().st_size != 8 + 16 * int.from_bytes(count, "little")):
            raise ValidationError(error)
        while compressed < size:
            source.seek(compressed)
            header = source.read(12)
            if len(header) != 12 or header[:4] != b"\x1f\x8b\x08\x04":
                raise ValidationError(error)
            extra = source.read(int.from_bytes(header[10:12], "little"))
            pos = 0
            while pos + 4 <= len(extra):
                length = int.from_bytes(extra[pos + 2:pos + 4], "little")
                if pos + 4 + length > len(extra):
                    raise ValidationError(error)
                if extra[pos:pos + 4] == b"BC\x02\x00":
                    break
                pos += 4 + length
            else:
                raise ValidationError(error)
            block_size = int.from_bytes(extra[pos + 4:pos + 6], "little") + 1
            end = compressed + block_size
            if block_size < 12 + len(extra) + 8 or end > size:
                raise ValidationError(error)
            source.seek(end - 4)
            length = int.from_bytes(source.read(4), "little")
            if length > 65536:
                raise ValidationError(error)
            if compressed:
                entry = index.read(16)
                # Some encoders include the terminal marker in the directory.
                if (entry or length or end != size) and entry != struct.pack("<QQ", compressed, uncompressed):
                    raise ValidationError(error)
            compressed = end
            uncompressed += length
        if not size or index.read(1):
            raise ValidationError(error)
    source.seek(0)


def _verify_indexed_rows(sequences, index, error):
    """Read regular lines in batches, so a human genome needs no Python loop per line."""
    chunk = 1024 * 1024
    # FAI describes byte geometry. Leave scientific alphabet and IGV locus
    # restrictions to their respective consumers; a SAM contig may include "|".
    symbols = rb"[!-=?-~]"
    symbol_run = re.compile(symbols + b"+")
    names = set()
    position = 0

    def read_bases(count):
        while count:
            length = min(chunk, count)
            data = sequences.read(length)
            if len(data) != length or not symbol_run.fullmatch(data):
                raise ValidationError(error)
            count -= length

    while raw := index.readline(8193):
        row = raw.rstrip(b"\r\n").split(b"\t")
        if len(raw) > 8192 or len(row) != 5 or not all(part.isdigit() for part in row[1:]):
            raise ValidationError(error)
        name = row[0]
        total, offset, bases, width = map(int, row[1:])
        if (not name or name in names or len(names) >= 100_000 or not 1 <= bases <= total
                or width - bases not in (0, 1, 2)):
            raise ValidationError(error)
        header = sequences.readline(8193)
        while names and header in (b"\n", b"\r\n"):
            position += len(header)
            header = sequences.readline(8193)
        position += len(header)
        if (len(header) > 8192 or not header.startswith(b">") or not header.endswith(b"\n")
                or header[1:].split(maxsplit=1)[:1] != [name] or position != offset):
            raise ValidationError(error)
        names.add(name)
        complete, remaining = divmod(total - 1, bases)
        last = remaining + 1
        if complete:
            if width == bases:
                raise ValidationError(error)
            sep = b"\r\n" if width - bases == 2 else b"\n"
            if width <= chunk:
                lines = re.compile(b"(?:" + symbols + b"{%d}" % bases + sep + b")+")
                while complete:
                    count = min(complete, chunk // width)
                    data = sequences.read(count * width)
                    if len(data) != count * width or not lines.fullmatch(data):
                        raise ValidationError(error)
                    complete -= count
            else:
                for _ in range(complete):
                    read_bases(bases)
                    if sequences.read(len(sep)) != sep:
                        raise ValidationError(error)
        read_bases(last)
        ending = sequences.readline(3)
        # faidx reports an implicit LF for a single unterminated line. Its
        # stride is never used to cross a row in a one-line contig.
        if ending not in (b"", b"\n", b"\r\n") or (total == bases and ending and width != bases + len(ending)):
            raise ValidationError(error)
        position += ((total - 1) // bases) * width + last + len(ending)
    if not names:
        raise ValidationError(error)
    while data := sequences.read(chunk):
        if data.strip(b"\r\n"):
            raise ValidationError(error)


def _verify_layout(fasta, fai, compressed, language, gzi=None):
    """Check every FASTA line and return the digest of the validated file."""
    error = _text(language, "Gli indici del riferimento non corrispondono al FASTA. Seleziona gli indici corretti o rigenerali.",
                  "The reference indexes do not match the FASTA. Select the matching indexes or regenerate them.")
    digest = hashlib.sha256()
    try:
        with fasta.open("rb") as source, fai.open("rb") as index:
            if compressed:
                _verify_gzi(source, gzi or Path(str(fasta) + ".gzi"), error)
            with io.BufferedReader(_HashedReader(source, digest), buffer_size=1024 * 1024) as raw:
                decoder = gzip.GzipFile(fileobj=raw) if compressed else nullcontext(raw)
                with decoder as sequences:
                    _verify_indexed_rows(sequences, index, error)
    except (ValidationError, ValueError, OSError, EOFError, zlib.error) as exc:
        raise ValidationError(error) from exc
    return digest.hexdigest()


def indexed_reference_identity(fasta, fai, *, gzi=None, language="it"):
    """Validate the supplied index files and pin the exact on-disk contents."""
    files = [fasta, fai] + ([gzi] if gzi else [])
    stamps = [_stamp(p) for p in files]
    result = {"fasta_sha256": _verify_layout(fasta, fai, gzi is not None, language, gzi),
              "index_sha256": _file_sha256(fai)}
    if gzi:
        result["gzi_sha256"] = _file_sha256(gzi)
    if stamps != [_stamp(p) for p in files]:
        raise ValidationError(_text(language, "Il riferimento è cambiato durante il controllo.",
                                    "The reference changed during verification."))
    return result


def _identify(chromosomes, build, language):
    types = set()
    primary = set()
    for contig in chromosomes:
        name, length = contig["name"], contig["length"]
        version = None
        if match := _NUCLEAR.fullmatch(name):
            number = {"X": 23, "Y": 24}.get(match[2]) or int(match[2])
            notation = "chr" if match[1] else "unprefixed"
        elif match := _REFSEQ.fullmatch(name):
            number = int(match[1])
            notation = "accession"
            version = int(match[2])
        else:
            continue
        types.add(notation)
        if build != "custom" and (_PRIMARY[build][number - 1] != length or number in primary
                                  or (version is not None and version != _REFSEQ_VERSIONS[build][number - 1])):
            raise ValidationError(_text(language, f"Il cromosoma {name} non corrisponde al dizionario di {_BUILDS[build]}.",
                                        f"Chromosome {name} does not match the {_BUILDS[build]} dictionary."))
        primary.add(number)
    if build != "custom" and not primary:
        raise ValidationError(_text(language, "Nessun cromosoma nucleare identifica questa assembly. Puoi caricare il FASTA come personalizzato.",
                                    "No nuclear chromosome identifies this assembly. You can import the FASTA as custom."))
    return next(iter(types)) if len(types) == 1 else "mixed" if types else "other"


class ReferenceCatalog:
    def __init__(self, path: Path, language="it"):
        self.path = Path(path)
        self.language = language

    def _read(self):
        try:
            with self.path.open("rb") as stream:
                data = stream.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError
            doc = json.loads(data)
            if doc["schema_version"] != 1 or not isinstance(doc["entries"], list):
                raise ValueError
            for item in doc["entries"]:
                if (not isinstance(item, dict) or item.get("build") not in _BUILDS
                        or not all(isinstance(item.get(k), str) for k in ("id", "label", "fasta", "index", "naming"))
                        or not re.fullmatch(r"[a-f0-9]{64}", str(item.get("index_sha256", "")))
                        or not isinstance(item.get("stamps"), dict)
                        or not Path(item["fasta"]).is_absolute() or item["index"] != item["fasta"] + ".fai"):
                    raise ValueError
            return doc["entries"]
        except FileNotFoundError:
            return []
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise ValidationError(_text(self.language, "Impossibile leggere il catalogo dei riferimenti.",
                                        "Cannot read the reference catalog.")) from exc

    @staticmethod
    def _stamps(fasta):
        return {p.name: _stamp(p) for p in reference_files(fasta)}

    def _public(self, entry, *, exact=False):
        result = dict(entry)
        stamps = result.pop("stamps")
        hashes = result.pop("content_sha256", None)
        preview = result.pop("fasta_preview_sha256", None)
        validated = result.pop("validated_layout", False)
        result["available"] = False
        # A metadata-only registration cannot establish the identity of its
        # original sequence. Keep it visible until the user imports it again.
        if not isinstance(hashes, dict) or not preview:
            return result
        path = Path(result["fasta"])
        required = list(reference_files(path))
        if any(not re.fullmatch(r"[a-f0-9]{64}", str(hashes.get(p.name, ""))) for p in required):
            return result
        result["fasta_sha256"] = hashes[path.name]
        if path.suffix.lower() in _COMPRESSED:
            result["gzi_sha256"] = hashes[path.name + ".gzi"]
        try:
            if self._stamps(path) == stamps:
                expected = hashes if exact else {**hashes, path.name: preview}
                if exact and not validated:
                    # Catalogs created before full line verification must also check their indexes.
                    fasta_hash = _verify_layout(path, Path(result["index"]), path.suffix.lower() in _COMPRESSED,
                                                self.language)
                    actual = {p.name: fasta_hash if p == path else _file_sha256(p) for p in required}
                else:
                    actual = _content_hashes(path, preview=not exact)
                result["available"] = actual == expected and self._stamps(path) == stamps
        except (OSError, ValidationError):
            result["available"] = False
        return result

    def list(self):
        builds = [{"id": key, "label": ("FASTA personalizzato" if key == "custom" and self.language != "en" else name)}
                  for key, name in _BUILDS.items()]
        return {"builds": builds, "entries": [self._public(e) for e in self._read()]}

    def resolve(self, reference_id):
        for item in self._read():
            if item["id"] == reference_id:
                entry = self._public(item, exact=True)
                if entry["available"]:
                    return entry
                break
        raise ValidationError(_text(self.language, "Riferimento assente o modificato. Carica nuovamente il FASTA.",
                                    "Reference missing or changed. Import the FASTA again."))

    def register(self, build, fasta):
        if not isinstance(build, str) or build not in _BUILDS:
            raise ValidationError(_text(self.language, "Assembly non valida.", "Invalid assembly."))
        check = LocalIGV(None, language=self.language)
        path = check.local_file(str(fasta), "FASTA")
        index = Path(str(path) + ".fai")
        compressed = path.suffix.lower() in _COMPRESSED
        if compressed and (not index.is_file() or not Path(str(path) + ".gzi").is_file()):
            raise ValidationError(_text(self.language, "Per il FASTA BGZF servono i suoi indici .fai e .gzi.",
                                        "A BGZF FASTA requires its .fai and .gzi indexes."))
        if not compressed and not index.is_file():
            build_fasta_index(path, language=self.language)
        try:
            stamps = self._stamps(path)
        except OSError as exc:
            raise ValidationError(_text(self.language, "File FASTA o indici mancanti.", "Missing FASTA file or indexes.")) from exc
        chromosomes = check.fasta_index(path, index)
        fasta_hash = _verify_layout(path, index, compressed, self.language)
        naming = _identify(chromosomes, build, self.language)
        hashes = {p.name: fasta_hash if p == path else _file_sha256(p) for p in reference_files(path)}
        preview = (_file_sha256(path, preview=True) if stamps[path.name][2] > _FULL_PREVIEW_LIMIT
                   else hashes[path.name])
        if stamps != self._stamps(path):
            raise ValidationError(_text(self.language, "Il riferimento è cambiato durante il caricamento.",
                                        "The reference changed during import."))
        entry = {"id": uuid4().hex, "build": build, "label": path.name, "fasta": str(path), "index": str(index),
                 "naming": naming, "contigs": len(chromosomes), "index_sha256": hashes[index.name], "stamps": stamps,
                 "content_sha256": hashes, "fasta_preview_sha256": preview, "validated_layout": True}
        if compressed:
            entry["compressedIndex"] = str(path) + ".gzi"
        with settings_file_lock(self.path):
            entries = self._read()
            for old in entries:
                if (old["fasta"] == str(path) and old["build"] == build and old["stamps"] == stamps
                        and old.get("content_sha256") == hashes):
                    if old.get("validated_layout"):
                        return self._public(old)
                    entry["id"] = old["id"]
                    break
            entries = [e for e in entries if not (e["fasta"] == str(path) and e["build"] == build)]
            data = json.dumps({"schema_version": 1, "entries": [*entries, entry]}, ensure_ascii=False).encode("utf-8")
            if len(data) > 4 * 1024 * 1024:
                raise ValidationError(_text(self.language, "Il catalogo dei riferimenti è pieno.", "The reference catalog is full."))
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".references-", delete=False) as tmp:
                temporary = Path(tmp.name)
                try:
                    tmp.write(data)
                    tmp.flush()
                except OSError:
                    tmp.close()
                    temporary.unlink(missing_ok=True)
                    raise
            try:
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        return self._public(entry)
