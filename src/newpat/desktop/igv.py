"""Bounded, local-file validation for the desktop IGV viewer.

This inspects indexes and alignment headers, never reads complete BAMs or
recomputes scientific outputs. File type checks do not prove index freshness.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import re
import struct

from newpat.errors import ValidationError
from newpat.experiments.tracking import input_stat_snapshot


class LocalIGV:
    def __init__(self, register, *, language="it", register_reference=None):
        self.register = register
        self.register_reference = register_reference or (lambda path, **_: register(path))
        self.language = language

    def text(self, italian, english):
        return english if self.language == "en" else italian

    def fail(self, italian, english):
        raise ValidationError(self.text(italian, english))

    def local_file(self, value, label):
        if not isinstance(value, str) or not value.strip():
            self.fail(f"Seleziona {label}.", f"Select {label}.")
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
            self.fail("IGV utilizza file locali; seleziona il file sul computer.",
                      "IGV uses local files; select the file on your computer.")
        try:
            path = Path(value).expanduser().resolve(strict=True)
            if path.is_file():
                return path
        except (OSError, ValueError):
            pass
        self.fail(f"File non disponibile: {label}. Seleziona un file esistente sul computer.",
                  f"File unavailable: {label}. Select an existing file on your computer.")

    def _prefix(self, path, size=4, *, compressed=False):
        try:
            opener = gzip.open if compressed else open
            with opener(path, "rb") as stream:
                return stream.read(size)
        except (OSError, EOFError):
            self.fail(f"File non leggibile o incompleto: {path.name}.",
                      f"Unreadable or incomplete file: {path.name}.")

    def fasta_index(self, fasta, index, *, expected_sha256=None):
        if index.suffix.lower() != ".fai":
            self.fail("Il riferimento FASTA richiede il suo indice .fai. Un file .bai è invece l’indice di una traccia BAM.",
                      "The FASTA reference requires its .fai index. A .bai file is the index of a BAM track.")
        compressed = fasta.name.lower().endswith((".gz", ".bgz", ".bgzf"))
        prefix = self._prefix(fasta, 4096, compressed=compressed)
        if not prefix.startswith(b">"):
            self.fail("Il genoma di riferimento non è un file FASTA valido (atteso un nome preceduto da >).",
                      "The reference genome is not a valid FASTA file (expected a name preceded by >).")
        if expected_sha256 is not None and (
                not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
            self.fail("Impronta SHA-256 dell’indice FASTA non valida.", "Invalid FASTA index SHA-256 digest.")
        digest = hashlib.sha256() if expected_sha256 is not None else None
        chromosomes = []
        seen = set()
        try:
            fasta_size = fasta.stat().st_size
            if index.stat().st_size > 32 * 1024 * 1024:
                self.fail("L’indice FASTA supera 32 MiB.", "The FASTA index exceeds 32 MiB.")
            with index.open("rb") as stream:
                total = 0
                while raw := stream.readline(8193):
                    total += len(raw)
                    if digest is not None:
                        digest.update(raw)
                    if len(raw) > 8192 or total > 32 * 1024 * 1024 or len(chromosomes) >= 100_000:
                        self.fail("L’indice FASTA è troppo grande o contiene righe non valide.",
                                  "The FASTA index is too large or contains invalid lines.")
                    fields = raw.decode("utf-8-sig").rstrip("\r\n").split("\t")
                    if (len(fields) != 5 or not re.fullmatch(r"[A-Za-z0-9_.-]+", fields[0])
                            or any(not re.fullmatch(r"[0-9]{1,18}", field) for field in fields[1:])):
                        raise ValueError
                    name = fields[0]
                    length, offset, bases, width = map(int, fields[1:])
                    if (name in seen or length < 1 or bases < 1 or width < bases
                            or width > bases + 2 or offset < 1):
                        raise ValueError
                    last_byte = offset + ((length - 1) // bases) * width + (length - 1) % bases
                    if not compressed and last_byte >= fasta_size:
                        self.fail("L’indice FAI non corrisponde alle dimensioni del FASTA selezionato. Seleziona il suo indice o rigeneralo.",
                                  "The FAI index does not match the selected FASTA size. Select its matching index or regenerate it.")
                    seen.add(name)
                    chromosomes.append({"name": name, "length": length})
            if digest is not None and digest.hexdigest() != expected_sha256:
                self.fail("L’indice FASTA differisce da quello registrato per questo esperimento. Ripristina il FASTA e il FAI originali.",
                          "The FASTA index differs from the one recorded for this experiment. Restore the original FASTA and FAI.")
            first_name = prefix[1:].splitlines()[0].split()[0].decode("utf-8")
            if not chromosomes or first_name != chromosomes[0]["name"]:
                self.fail("Il primo cromosoma del FASTA non corrisponde all’indice FAI. Seleziona l’indice dello stesso riferimento.",
                          "The first FASTA chromosome does not match the FAI index. Select the index of the same reference.")
        except (UnicodeError, ValueError, IndexError):
            self.fail("Indice FASTA non valido: seleziona il file .fai del riferimento, non l’indice .bai del BAM.",
                      "Invalid FASTA index: select the reference .fai file, not the BAM .bai index.")
        except OSError:
            self.fail("Impossibile leggere l’indice FASTA. Seleziona nuovamente il file .fai.",
                      "The FASTA index cannot be read. Select the .fai file again.")
        return chromosomes

    @staticmethod
    def chromosome_alias(name, lengths):
        if name in lengths:
            return name
        alternatives = {name[3:] if name.startswith("chr") else "chr" + name}
        if name in {"M", "MT", "chrM", "chrMT"}:
            alternatives.update({"M", "MT", "chrM", "chrMT"})
        matches = alternatives.intersection(lengths)
        return next(iter(matches)) if len(matches) == 1 else None

    def locus(self, value, chromosomes):
        if isinstance(value, list):
            if not 1 <= len(value) <= 12:
                self.fail("Seleziona da 1 a 12 regioni.", "Select 1 to 12 regions.")
            return [self.locus(item, chromosomes) for item in value]
        if value is None or value == "":
            return "all"
        if not isinstance(value, str) or len(value) > 300:
            self.fail("Inserisci un cromosoma o una regione valida.", "Enter a valid chromosome or region.")
        value = value.strip().replace("–", "-").replace("—", "-")
        if value == "all":
            return "all"
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?::([0-9]+(?:,[0-9]{3})*)(?:-([0-9]+(?:,[0-9]{3})*))?)?", value)
        if not match:
            self.fail("Usa il formato cromosoma:inizio-fine, ad esempio 1:100000-110000.",
                      "Use chromosome:start-end, for example 1:100000-110000.")
        lengths = {item["name"]: item["length"] for item in chromosomes}
        name = self.chromosome_alias(match[1], lengths)
        if name is None:
            self.fail(f"Il cromosoma {match[1]} non è presente nel riferimento. Sceglilo dall’elenco; X e Y non sono indicati come 23.",
                      f"Chromosome {match[1]} is absent from the reference. Choose one from the list; X and Y are not named 23.")
        if match[2] is None:
            return name
        start = int(match[2].replace(",", ""))
        end = int(match[3].replace(",", "")) if match[3] else start
        if not 1 <= start <= end <= lengths[name]:
            self.fail(f"Le coordinate di {name} devono essere comprese tra 1 e {lengths[name]}, con fine non precedente all’inizio.",
                      f"Coordinates for {name} must be between 1 and {lengths[name]}, with end at or after start.")
        return f"{name}:{start}-{end}" if match[3] else f"{name}:{start}"

    def bam_references(self, path):
        """Read at most 16 MiB of decompressed header, never alignment records."""
        try:
            compressed = self._prefix(path, 2) == b"\x1f\x8b"
            opener = gzip.open if compressed else open
            with opener(path, "rb") as stream:
                budget = 16 * 1024 * 1024
                def read(size):
                    nonlocal budget
                    if not 0 <= size <= budget:
                        raise ValueError
                    budget -= size
                    data = stream.read(size)
                    if len(data) != size:
                        raise ValueError
                    return data
                def number():
                    return struct.unpack("<i", read(4))[0]
                if read(4) != b"BAM\x01":
                    raise ValueError
                read(number())  # SAM header text
                count = number()
                if not 0 <= count <= 100_000:
                    raise ValueError
                references = []
                seen = set()
                for _ in range(count):
                    raw_name = read(number())
                    if not raw_name.endswith(b"\0"):
                        raise ValueError
                    name = raw_name[:-1].decode("utf-8")
                    length = number()
                    if not name or name in seen or length < 1:
                        raise ValueError
                    seen.add(name)
                    references.append((name, length))
                return references
        except (OSError, EOFError, ValueError, struct.error):
            self.fail(f"Il file {path.name} non contiene un’intestazione BAM valida o è incompleto. Seleziona il BAM del campione, non il suo indice.",
                      f"{path.name} has an invalid or incomplete BAM header. Select the sample BAM file, not its index.")

    def check_bam_reference(self, path, fasta, fai, lengths, *, exact_names, targets=frozenset()):
        """Check metadata only. Extra decoys are allowed and target names must match."""
        references = self.bam_references(path)
        common = set()
        for name, length in references:
            alias = self.chromosome_alias(name, lengths)
            if alias:
                if alias != name and exact_names:
                    self.fail(
                        f"Il BAM usa {name}, mentre il FASTA usa {alias}. Seleziona il FASTA con i nomi usati per l’allineamento.",
                        f"The BAM uses {name}, while the FASTA uses {alias}. Select the FASTA with the names used for alignment.")
                common.add(alias)
                if lengths[alias] != length:
                    self.fail(
                        f"Il BAM e il FASTA indicano lunghezze diverse per {name}: "
                        f"{path.name} dichiara {length} basi; {fasta.name}, tramite "
                        f"{fai.name}, dichiara {lengths[alias]} basi per {alias}. "
                        "Seleziona il FASTA usato per l’allineamento e il suo indice FAI corrispondente.",
                        f"BAM and FASTA lengths differ for {name}: "
                        f"{path.name} declares {length} bases; {fasta.name}, through "
                        f"{fai.name}, declares {lengths[alias]} bases for {alias}. "
                        "Select the FASTA used for alignment and its matching FAI index.")
        if (references or exact_names) and not common:
            self.fail("BAM e FASTA non hanno cromosomi in comune. Seleziona il riferimento usato per l’allineamento.",
                      "BAM and FASTA have no chromosomes in common. Select the reference used for alignment.")
        missing = targets - common
        if missing:
            name = min(missing)
            self.fail(f"Il cromosoma {name} del pannello manca nel BAM {path.name}. Verifica il riferimento e il pannello.",
                      f"Panel chromosome {name} is missing from BAM {path.name}. Check the reference and the panel.")
        return len(references)

    def prepare(self, params, *, reference_cache=None, require_locus=False):
        reference = params.get("reference", {})
        if not isinstance(reference, dict):
            self.fail("Seleziona il riferimento e il suo indice.", "Select the reference and its index.")
        build = reference.get("build")
        if build not in (None, "", "custom", "grch37", "grch38"):
            self.fail("Build di riferimento non supportata.", "Unsupported reference build.")
        fasta = self.local_file(reference.get("fasta"), "FASTA")
        automatic_fai = Path(str(fasta) + ".fai")
        if not reference.get("index") and not automatic_fai.is_file():
            self.fail(f"Indice FASTA non trovato: {automatic_fai.name}. Seleziona il file .fai dello stesso riferimento; il file .bai appartiene al BAM.",
                      f"FASTA index not found: {automatic_fai.name}. Select the .fai of the same reference; .bai belongs to the BAM.")
        fai = self.local_file(reference.get("index") or str(automatic_fai), "FAI")
        expected_digest = reference.get("index_sha256")
        chromosomes = self.fasta_index(fasta, fai, expected_sha256=expected_digest)
        from .references import indexed_reference_identity
        gzi = None
        if fasta.suffix.lower() in (".gz", ".bgz", ".bgzf"):
            gzi = self.local_file(reference.get("compressedIndex") or str(fasta) + ".gzi", "GZI")
        files = (fasta, fai, gzi) if gzi else (fasta, fai)
        identities = {p: input_stat_snapshot(p.stat()) for p in files}
        # A multi-case report may use the same multi-gigabyte reference many
        # times. The cache lives for that request, keyed by every file's identity.
        cache_key = tuple((p, tuple(stamp.items())) for p, stamp in identities.items())
        actual = reference_cache.get(cache_key) if reference_cache is not None else None
        if actual is None:
            actual = indexed_reference_identity(fasta, fai, gzi=gzi, language=self.language)
            if reference_cache is not None:
                reference_cache[cache_key] = actual
        for key, digest in actual.items():
            expected = reference.get(key)
            if expected is None:
                continue
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                self.fail("Impronta SHA-256 del riferimento non valida.", "Invalid reference SHA-256 digest.")
            if digest != expected:
                self.fail("Il FASTA o il suo indice differisce da quello registrato. Ripristina i file originali.",
                          "The FASTA or its index differs from the recorded reference. Restore the original files.")
        locus = self.locus(params.get("locus"), chromosomes)
        required_contigs = {locus.split(":", 1)[0]} if require_locus else set()
        if any(input_stat_snapshot(p.stat()) != identity for p, identity in identities.items()):
            self.fail("Il riferimento è cambiato durante il controllo.", "The reference changed during verification.")
        urls = {p: self.register_reference(p, expected_identity=identity)["url"] for p, identity in identities.items()}
        ref = {"id": "newpat-local", "name": fasta.name, "fastaURL": urls[fasta], "indexURL": urls[fai]}
        sources = {"reference": {"fasta": str(fasta), "index": str(fai), **actual}, "tracks": []}
        if reference.get("historical_identity_incomplete"):
            sources["reference"]["historical_identity_incomplete"] = True
        if build in ("grch37", "grch38"):
            sources["reference"]["build"] = build
        if gzi:
            ref["compressedIndexURL"] = urls[gzi]
            sources["reference"]["compressedIndex"] = str(gzi)
        tracks = params.get("tracks", [])
        if not isinstance(tracks, list) or len(tracks) > 200:
            self.fail("Elenco di tracce non valido.", "Invalid track list.")
        prepared = []
        formats = {"bam": "alignment", "cram": "alignment", "vcf": "variant", "bed": "annotation",
                   "gff": "annotation", "gff3": "annotation", "gtf": "annotation", "bw": "wig",
                   "bigwig": "wig", "wig": "wig", "bedgraph": "wig", "seg": "seg", "bb": "annotation", "bigbed": "annotation"}
        lengths = {item["name"]: item["length"] for item in chromosomes}
        for item in tracks:
            if not isinstance(item, dict):
                self.fail("Traccia non valida.", "Invalid track.")
            path = self.local_file(item.get("path"), self.text("traccia", "track"))
            stem = path.name.lower().removesuffix(".gz").removesuffix(".bgz")
            fmt = str(item.get("format") or stem.rsplit(".", 1)[-1]).lower()
            if fmt not in formats:
                self.fail(f"Formato della traccia non supportato: {path.name}.", f"Unsupported track format: {path.name}.")
            index = item.get("index")
            suffixes = (".bai", ".csi") if fmt == "bam" else (".crai",) if fmt == "cram" else ()
            if not suffixes and path.name.lower().endswith((".gz", ".bgz")) and fmt in {"vcf", "bed", "gff", "gff3", "gtf"}:
                suffixes = (".tbi", ".csi")
            if not index and suffixes:
                candidates = [candidate for suffix in suffixes
                              for candidate in (Path(str(path) + suffix), path.with_suffix(suffix))]
                index = next((str(p) for p in candidates if p.is_file()), None)
            if suffixes and not index:
                names = "/".join(suffix[1:].upper() for suffix in suffixes)
                self.fail(f"Seleziona l’indice {names} per {path.name}.", f"Select the {names} index for {path.name}.")
            index_path = self.local_file(index, self.text("indice della traccia", "track index")) if index else None
            if index_path and suffixes and index_path.suffix.lower() not in suffixes:
                names = "/".join(suffix[1:].upper() for suffix in suffixes)
                self.fail(f"Indice non corretto per {path.name}: serve {names}. Il FAI appartiene al riferimento FASTA.",
                          f"Wrong index for {path.name}: {names} is required. FAI belongs to the FASTA reference.")
            if index_path and index_path.suffix.lower() in {".bai", ".csi", ".tbi"}:
                magic = {".bai": b"BAI\x01", ".csi": b"CSI\x01", ".tbi": b"TBI\x01"}[index_path.suffix.lower()]
                compressed = self._prefix(index_path, 2) == b"\x1f\x8b"
                minimum = {".bai": 8, ".csi": 16, ".tbi": 36}[index_path.suffix.lower()]
                header = self._prefix(index_path, minimum, compressed=compressed)
                if len(header) != minimum or header[:4] != magic:
                    self.fail(f"Il file {index_path.name} non è un indice {index_path.suffix[1:].upper()} valido.",
                              f"{index_path.name} is not a valid {index_path.suffix[1:].upper()} index.")
            if fmt == "bam":
                count = self.check_bam_reference(path, fasta, fai, lengths, targets=required_contigs,
                                                 exact_names=build in ("grch37", "grch38"))
                if index_path and index_path.suffix.lower() == ".bai":
                    header = self._prefix(index_path, 8)
                    if (len(header) != 8 or struct.unpack("<i", header[4:])[0] != count
                            or index_path.stat().st_size < 8 + 8 * count):
                        self.fail("L’indice BAI non corrisponde al numero di cromosomi del BAM o è incompleto. Seleziona il suo indice o rigeneralo.",
                                  "The BAI index does not match the BAM chromosome count or is incomplete. Select its matching index or regenerate it.")
            elif fmt == "cram" and self._prefix(path) != b"CRAM":
                self.fail("La traccia selezionata non è un file CRAM valido.", "The selected track is not a valid CRAM file.")
            track = {"name": str(item.get("name") or path.name), "format": fmt, "type": formats[fmt],
                     "url": self.register(path)["url"], "indexed": bool(index_path)}
            if index_path:
                track["indexURL"] = self.register(index_path)["url"]
            prepared.append(track)
            sources["tracks"].append({"name": track["name"], "path": str(path), "format": fmt,
                                       "index": str(index_path) if index_path else ""})
        return {"reference": ref, "tracks": prepared, "locus": locus, "chromosomes": chromosomes,
                "sources": sources, "loadDefaultGenomes": False, "genomeList": [], "search": False}
