"""Persistent selections of local, indexed human and custom reference genomes."""
from __future__ import annotations

from bisect import bisect_right
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
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


def _text(language, italian, english):
    return english if language == "en" else italian


def _stamp(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


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


def _bgzf_offsets(source, gzi, error):
    # The GZI table maps uncompressed file offsets to independently readable
    # BGZF blocks. Offset (0, 0) is implicit in the htslib format.
    header = source.read(12)
    if len(header) != 12 or header[:3] != b"\x1f\x8b\x08" or not header[3] & 4:
        raise ValidationError(error)
    extra = source.read(int.from_bytes(header[10:12], "little"))
    i = 0
    while i + 4 <= len(extra):
        size = int.from_bytes(extra[i + 2:i + 4], "little")
        if i + size + 4 > len(extra):
            raise ValidationError(error)
        if extra[i:i + 4] == b"BC\x02\x00":
            break
        i += size + 4
    else:
        raise ValidationError(error)
    with gzi.open("rb") as index:
        count = index.read(8)
        if len(count) != 8 or gzi.stat().st_size != 8 + 16 * int.from_bytes(count, "little"):
            raise ValidationError(error)
        if gzi.stat().st_size > 32 * 1024 * 1024:
            raise ValidationError(error)
        raw = index.read()
    uncompressed, compressed = [0], [0]
    file_size = os.fstat(source.fileno()).st_size
    for cstart, ustart in struct.iter_unpack("<QQ", raw):
        if not (compressed[-1] < cstart < file_size and uncompressed[-1] < ustart <= uncompressed[-1] + 65536):
            raise ValidationError(error)
        uncompressed.append(ustart)
        compressed.append(cstart)
    return uncompressed, compressed


def _verify_layout(fasta, fai, compressed, language):
    """Verify boundaries of every contig without rereading gigabytes of sequence."""
    error = _text(language, "Gli indici del riferimento non corrispondono al FASTA. Seleziona gli indici corretti o rigenerali.",
                  "The reference indexes do not match the FASTA. Select the matching indexes or regenerate them.")
    with fasta.open("rb") as source, fai.open("rb") as index:
        if compressed:
            uoffsets, coffsets = _bgzf_offsets(source, Path(str(fasta) + ".gzi"), error)

        def read_at(position, count):
            if not compressed:
                source.seek(position)
                return source.read(count)
            block = bisect_right(uoffsets, position) - 1
            skip = position - uoffsets[block]
            if skip > 65536:
                raise ValidationError(error)
            source.seek(coffsets[block])
            try:
                with gzip.GzipFile(fileobj=source) as reader:
                    return reader.read(skip + count)[skip:]
            except (OSError, EOFError) as exc:
                raise ValidationError(error) from exc

        next_header = 0
        for row in index:
            name, size, offset, bases, width = row.rstrip(b"\r\n").split(b"\t")
            size, offset, bases, width = map(int, (size, offset, bases, width))
            if not 1 <= offset - next_header <= 8192:
                raise ValidationError(error)
            header = read_at(next_header, offset - next_header).lstrip(b"\r\n")
            if (not header.startswith(b">") or not header.endswith(b"\n")
                    or header[1:].split()[:1] != [name] or len(header.splitlines()) != 1):
                raise ValidationError(error)
            if size > bases:
                separator = read_at(offset + bases, width - bases)
                if separator not in (b"\n", b"\r\n"):
                    raise ValidationError(error)
            last = offset + (size - 1) // bases * width + (size - 1) % bases
            tail = read_at(last, 3)
            if not _SEQ.fullmatch(tail[:1]):
                raise ValidationError(error)
            if tail[1:].startswith(b"\r\n"):
                next_header = last + 3
            elif tail[1:].startswith(b"\n"):
                next_header = last + 2
            elif len(tail) == 1:
                next_header = last + 1
            else:
                raise ValidationError(error)
        trailing = read_at(next_header, 8193)
        if len(trailing) > 8192 or trailing.strip(b"\r\n"):
            raise ValidationError(error)


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
        paths = [fasta, Path(str(fasta) + ".fai")]
        if fasta.suffix.lower() in _COMPRESSED:
            paths.append(Path(str(fasta) + ".gzi"))
        return {p.name: _stamp(p) for p in paths}

    def _public(self, entry):
        result = dict(entry)
        stamps = result.pop("stamps")
        try:
            result["available"] = self._stamps(Path(result["fasta"])) == stamps
        except OSError:
            result["available"] = False
        return result

    def list(self):
        builds = [{"id": key, "label": ("FASTA personalizzato" if key == "custom" and self.language != "en" else name)}
                  for key, name in _BUILDS.items()]
        return {"builds": builds, "entries": [self._public(e) for e in self._read()]}

    def resolve(self, reference_id):
        for item in self._read():
            if item["id"] == reference_id:
                entry = self._public(item)
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
        _verify_layout(path, index, compressed, self.language)
        naming = _identify(chromosomes, build, self.language)
        with index.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if stamps != self._stamps(path):
            raise ValidationError(_text(self.language, "Il riferimento è cambiato durante il caricamento.",
                                        "The reference changed during import."))
        entry = {"id": uuid4().hex, "build": build, "label": path.name, "fasta": str(path), "index": str(index),
                 "naming": naming, "contigs": len(chromosomes), "index_sha256": digest, "stamps": stamps}
        if compressed:
            entry["compressedIndex"] = str(path) + ".gzi"
        with settings_file_lock(self.path):
            entries = self._read()
            for old in entries:
                if old["fasta"] == str(path) and old["build"] == build and old["stamps"] == stamps:
                    return self._public(old)
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
