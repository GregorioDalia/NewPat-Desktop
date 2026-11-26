"""Bundled IGV provenance and local-only adapter behavior."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import struct
import zlib
from pathlib import Path

import pytest

from nipat.errors import ValidationError
from nipat.gui.igv import LocalIGV

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "nipat" / "gui" / "web"


def test_igv_assets_are_pinned_and_complete():
    vendor = WEB / "vendor"
    manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "3.8.9"
    assert manifest["license"] == "MIT"
    assert "igv.min.js" in manifest["assets"]
    assert "igv.LICENSE.txt" in manifest["assets"]
    assert len(manifest["assets"]) >= 10
    for name, expected in manifest["assets"].items():
        path = vendor / name
        assert path.resolve().is_relative_to(vendor.resolve())
        content = path.read_bytes()
        assert len(content) == expected["bytes"]
        assert hashlib.sha256(content).hexdigest() == expected["sha256"]
    assert "Permission is hereby granted" in (vendor / "igv.LICENSE.txt").read_text()


def test_igv_adapter_local_resources_and_lifecycle():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the GUI JavaScript contract checks")
    result = subprocess.run(
        [node, str(ROOT / "tests" / "test_gui_igv_adapter.cjs"), str(WEB / "igv-view.js")],
        text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout


def _bgzf(data):
    """A genuine BGZF block, suitable for both the parser and IGV range reads."""
    encoder = zlib.compressobj(wbits=-15)
    payload = encoder.compress(data) + encoder.flush()
    size = len(payload) + 26
    return (b"\x1f\x8b\x08\x04\x00\x00\x00\x00\x00\xff\x06\x00BC\x02\x00"
            + struct.pack("<H", size - 1) + payload
            + struct.pack("<II", zlib.crc32(data), len(data)))


def _reference(tmp_path):
    fasta = tmp_path / "reference.fa"
    fasta.write_bytes(b">1\nACGT\n>X\nACGT\n")
    Path(str(fasta) + ".fai").write_text("1\t4\t3\t4\t5\nX\t4\t11\t4\t5\n", encoding="utf-8")
    return fasta


def _bam(tmp_path, *, name="sample", chromosome="1", length=4):
    path = tmp_path / (name + ".bam")
    encoded = chromosome.encode() + b"\0"
    header = b"BAM\x01" + struct.pack("<iii", 0, 1, len(encoded)) + encoded + struct.pack("<i", length)
    path.write_bytes(_bgzf(header) + _bgzf(b""))
    Path(str(path) + ".bai").write_bytes(b"BAI\x01" + struct.pack("<iiiQ", 1, 0, 0, 0))
    return path


@pytest.fixture
def local_igv():
    registered = []
    def register(path):
        registered.append(path)
        return {"url": f"http://127.0.0.1/resources/{len(registered)}"}
    return LocalIGV(register)


def test_reference_and_bam_indexes_are_discovered_and_returned(local_igv, tmp_path):
    fasta, bam = _reference(tmp_path), _bam(tmp_path)
    result = local_igv.prepare({"reference": {"fasta": str(fasta)}, "tracks": [{"path": str(bam)}]})
    assert result["locus"] == "all"
    assert result["chromosomes"] == [{"name": "1", "length": 4}, {"name": "X", "length": 4}]
    assert result["sources"]["reference"]["index"] == str(fasta) + ".fai"
    assert result["sources"]["tracks"][0]["index"] == str(bam) + ".bai"
    assert result["tracks"][0]["format"] == "bam"


@pytest.mark.parametrize("renamed", [False, True])
def test_bai_in_fai_field_gives_actionable_message(local_igv, tmp_path, renamed):
    fasta, bam = _reference(tmp_path), _bam(tmp_path)
    index = Path(str(bam) + ".bai")
    if renamed:
        wrong = tmp_path / "wrong.fai"
        wrong.write_bytes(index.read_bytes() + b"\xff")
        index = wrong
    with pytest.raises(ValidationError, match="FASTA.*fai") as error:
        local_igv.prepare({"reference": {"fasta": str(fasta), "index": str(index)}})
    assert "utf-8" not in str(error.value)


def test_missing_index_has_localized_recovery_instructions(local_igv, tmp_path):
    fasta = _reference(tmp_path)
    Path(str(fasta) + ".fai").unlink()
    local_igv.language = "en"
    with pytest.raises(ValidationError, match=r"FASTA index not found.*\.fai.*\.bai"):
        local_igv.prepare({"reference": {"fasta": str(fasta)}})


def test_fai_cannot_be_used_as_bam_index(local_igv, tmp_path):
    fasta, bam = _reference(tmp_path), _bam(tmp_path)
    with pytest.raises(ValidationError, match="BAI/CSI"):
        local_igv.prepare({"reference": {"fasta": str(fasta)},
                           "tracks": [{"path": str(bam), "index": str(fasta) + ".fai"}]})


@pytest.mark.parametrize("content", ["1\t4\t3\t4\t5\n1\t4\t11\t4\t5\n",
                                     "1\t400\t3\t4\t5\n", "2\t4\t3\t4\t5\n",
                                     "1\t4\t3\t0\t5\n", "1\t4\t3\t4\t999\n", ""])
def test_wrong_or_malformed_fai_is_rejected(local_igv, tmp_path, content):
    fasta = _reference(tmp_path)
    Path(str(fasta) + ".fai").write_text(content)
    with pytest.raises(ValidationError):
        local_igv.prepare({"reference": {"fasta": str(fasta)}})


@pytest.mark.parametrize("chromosome,length,reason", [("1", 5, "lunghezze diverse"), ("missing", 4, "non hanno cromosomi")])
def test_bam_reference_dictionary_must_be_compatible(local_igv, tmp_path, chromosome, length, reason):
    fasta = _reference(tmp_path)
    bam = _bam(tmp_path, chromosome=chromosome, length=length)
    with pytest.raises(ValidationError, match=reason):
        local_igv.prepare({"reference": {"fasta": str(fasta)}, "tracks": [{"path": str(bam)}]})


@pytest.mark.parametrize("language", ["it", "en"])
def test_mitochondrial_mismatch_reports_both_files_indexes_and_lengths(local_igv, tmp_path, language):
    local_igv.language = language
    fasta = tmp_path / "genome.fa"
    fasta.write_bytes(b">chrM\nACGT\n")
    Path(str(fasta) + ".fai").write_text("chrM\t4\t6\t4\t5\n", encoding="ascii")
    bam = _bam(tmp_path, name="patient", chromosome="chrM", length=5)
    with pytest.raises(ValidationError) as caught:
        local_igv.prepare({"reference": {"fasta": str(fasta)}, "tracks": [{"path": str(bam)}]})
    message = str(caught.value)
    for text in ("chrM", "patient.bam", "genome.fa", "genome.fa.fai", "4", "5", "FAI"):
        assert text in message
    assert ("allineamento" if language == "it" else "alignment") in message


def test_reference_only_remains_valid_but_empty_form_requests_fasta(local_igv, tmp_path):
    with pytest.raises(ValidationError, match="Seleziona FASTA"):
        local_igv.prepare({})
    result = local_igv.prepare({"reference": {"fasta": str(_reference(tmp_path))}})
    assert result["tracks"] == []


def test_bam_header_and_bai_reference_count_are_checked(local_igv, tmp_path):
    fasta, bam = _reference(tmp_path), _bam(tmp_path)
    params = {"reference": {"fasta": str(fasta)}, "tracks": [{"path": str(bam)}]}
    Path(str(bam) + ".bai").write_bytes(b"BAI\x01" + struct.pack("<i", 2))
    with pytest.raises(ValidationError, match="numero di cromosomi"):
        local_igv.prepare(params)
    bam.write_bytes(b"not a BAM")
    with pytest.raises(ValidationError, match="intestazione BAM"):
        local_igv.prepare(params)


def test_reference_alias_and_region_bounds(local_igv, tmp_path):
    fasta, bam = _reference(tmp_path), _bam(tmp_path, chromosome="chr1")
    params = {"reference": {"fasta": str(fasta)}, "tracks": [{"path": str(bam)}], "locus": "chr1:1-4"}
    assert local_igv.prepare(params)["locus"] == "1:1-4"
    for locus in ["1:0-4", "1:3-2", "1:1-5", "1:,", "test", "23", "https://example.org"]:
        with pytest.raises(ValidationError):
            local_igv.prepare({**params, "locus": locus})
    assert local_igv.prepare({**params, "locus": ["X", "1:2"]})["locus"] == ["X", "1:2"]


@pytest.mark.parametrize("build", ["grch37", "grch38"])
def test_named_reference_requires_matching_bam_contig_names(local_igv, tmp_path, build):
    fasta = _reference(tmp_path)
    reference = {"fasta": str(fasta), "build": build}
    bam = _bam(tmp_path, chromosome="chr1")
    with pytest.raises(ValidationError, match="BAM usa chr1.*FASTA usa 1"):
        local_igv.prepare({"reference": reference, "tracks": [{"path": str(bam)}]})
    bam = _bam(tmp_path, chromosome="1")
    prepared = local_igv.prepare({"reference": reference, "tracks": [{"path": str(bam)}], "locus": "chr1:1"})
    assert prepared["sources"]["reference"]["build"] == build
    assert prepared["locus"] == "1:1"


def test_named_reference_allows_targeted_bam_if_panel_chromosomes_are_present(local_igv, tmp_path):
    fasta, bam = _reference(tmp_path), _bam(tmp_path)
    index = Path(str(fasta) + ".fai")
    lengths = {"1": 4, "X": 4}
    assert local_igv.check_bam_reference(bam, fasta, index, lengths, exact_names=True, targets={"1"}) == 1
    with pytest.raises(ValidationError, match="X del pannello manca nel BAM"):
        local_igv.check_bam_reference(bam, fasta, index, lengths, exact_names=True, targets={"1", "X"})


def test_recorded_igv_reference_checks_and_preserves_fai_digest(local_igv, tmp_path):
    fasta = _reference(tmp_path)
    index = Path(str(fasta) + ".fai")
    digest = hashlib.sha256(index.read_bytes()).hexdigest()
    reference = {"fasta": str(fasta), "index": str(index), "index_sha256": digest}
    assert local_igv.prepare({"reference": reference})["sources"]["reference"] == {
        **reference, "fasta_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest()}

    # A syntactically valid replacement FAI can still describe a different reference.
    index.write_text("1\t4\t3\t4\t5\nY\t4\t11\t4\t5\n", encoding="ascii")
    with pytest.raises(ValidationError, match="differisce"):
        local_igv.prepare({"reference": reference})
    with pytest.raises(ValidationError, match="SHA-256"):
        local_igv.prepare({"reference": {**reference, "index_sha256": "invalid"}})


def test_bgzf_reference_requires_and_registers_compressed_index(local_igv, tmp_path):
    plain = _reference(tmp_path)
    fasta = tmp_path / "reference.fa.bgzf"
    fasta.write_bytes(_bgzf(plain.read_bytes()) + _bgzf(b""))
    shutil.copyfile(str(plain) + ".fai", str(fasta) + ".fai")
    with pytest.raises(ValidationError, match="GZI"):
        local_igv.prepare({"reference": {"fasta": str(fasta)}})
    gzi = Path(str(fasta) + ".gzi")
    gzi.write_bytes(struct.pack("<Q", 0))
    prepared = local_igv.prepare({"reference": {"fasta": str(fasta)}})
    assert prepared["sources"]["reference"]["compressedIndex"] == str(gzi)
    assert "compressedIndexURL" in prepared["reference"]


def test_bounded_index_line_does_not_read_entire_invalid_file(local_igv, tmp_path):
    fasta = _reference(tmp_path)
    Path(str(fasta) + ".fai").write_bytes(b"a" * 9000)
    with pytest.raises(ValidationError, match="troppo grande"):
        local_igv.prepare({"reference": {"fasta": str(fasta)}})


def create_alignment_fixture(directory, chromosomes=("1", "X")):
    """Deterministic indexed BAM with 20 reads for real IGV rendering checks.

    Tiny single-block BAM/BAI per SAMv1 §§4–5, without third-party tooling.
    This is synthetic UI evidence, never a scientific reference dataset.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sequence = "ACGT" * 250
    fasta = directory / "synthetic-reference.fa"
    index = []
    with fasta.open("wb") as handle:
        for name in chromosomes:
            handle.write(f">{name}\n".encode("ascii"))
            index.append(f"{name}\t1000\t{handle.tell()}\t1000\t1001\n")
            handle.write((sequence + "\n").encode("ascii"))
    Path(str(fasta) + ".fai").write_text("".join(index), encoding="ascii")
    text = ("@HD\tVN:1.6\tSO:coordinate\n" + "".join(f"@SQ\tSN:{name}\tLN:1000\n" for name in chromosomes)).encode("ascii")
    header = b"BAM\x01" + struct.pack("<i", len(text)) + text + struct.pack("<i", len(chromosomes))
    for name in chromosomes:
        chromosome = name.encode("ascii") + b"\0"
        header += struct.pack("<i", len(chromosome)) + chromosome + struct.pack("<i", 1000)
    records = []
    expected = []
    codes = {"A": 1, "C": 2, "G": 4, "T": 8}
    for number in range(20):
        pos = 100 + 4 * number
        read_name = f"qa_read_{number + 1:02d}".encode() + b"\0"
        bases = list(sequence[pos:pos + 60])
        if number % 4 == 0 and pos <= 150 < pos + len(bases):
            bases[150 - pos] = "A"  # Visible synthetic G>A difference at 1:151.
        packed = bytes((codes[bases[i]] << 4) | codes[bases[i + 1]] for i in range(0, len(bases), 2))
        core = struct.pack("<iiIIiiii", 0, pos, (4681 << 16) | (60 << 8) | len(read_name),
                           1, len(bases), -1, -1, 0)
        record = core + read_name + struct.pack("<I", len(bases) << 4) + packed + bytes([40] * len(bases))
        records.append(struct.pack("<i", len(record)) + record)
        expected.append({"name": read_name[:-1].decode(), "start": pos + 1, "length": len(bases)})
    block = _bgzf(header + b"".join(records))
    bam = directory / "synthetic-alignments.bam"
    bam.write_bytes(block + _bgzf(b""))
    chunk_begin, chunk_end = len(header), len(block) << 16
    # The first reference has one bin/chunk and one linear interval. The others have no reads.
    bai = (b"BAI\x01" + struct.pack("<iiIiQQiQ", len(chromosomes), 1, 4681, 1, chunk_begin, chunk_end, 1, chunk_begin)
           + struct.pack("<ii", 0, 0) * (len(chromosomes) - 1) + struct.pack("<Q", 0))
    Path(str(bam) + ".bai").write_bytes(bai)
    selection = {"reference": {"fasta": str(fasta.resolve()), "index": str(fasta.resolve()) + ".fai"},
                 "tracks": [{"name": "Synthetic QA · 20 reads", "path": str(bam.resolve()), "index": str(bam.resolve()) + ".bai"}],
                 "locus": "1:80-260"}
    (directory / "fixture.json").write_text(json.dumps({"selection": selection, "expected_reads": expected}, indent=2), encoding="utf-8")
    return selection


def test_real_alignment_fixture_has_indexed_records_and_matching_dictionary(local_igv, tmp_path):
    import gzip
    selection = create_alignment_fixture(tmp_path)
    prepared = local_igv.prepare(selection)
    assert prepared["chromosomes"] == [{"name": "1", "length": 1000}, {"name": "X", "length": 1000}]
    bam = Path(selection["tracks"][0]["path"])
    data = gzip.decompress(bam.read_bytes())
    bai = Path(str(bam) + ".bai").read_bytes()
    offset = struct.unpack_from("<Q", bai, 20)[0]  # First chunk's virtual uncompressed offset.
    assert offset < 65536
    reads = []
    while offset < len(data):
        size = struct.unpack_from("<i", data, offset)[0]
        ref, pos, packed = struct.unpack_from("<iiI", data, offset + 4)
        read_name_length = packed & 0xff
        name = data[offset + 36:offset + 36 + read_name_length - 1].decode()
        reads.append((ref, pos + 1, name))
        offset += size + 4
    assert len(reads) == 20
    assert reads[0] == (0, 101, "qa_read_01") and reads[-1] == (0, 177, "qa_read_20")
    assert offset == len(data)


def test_archived_fasta_same_layout_rejected_and_legacy_disclosed(local_igv, tmp_path):
    from nipat.gui.results import ResultsStore
    from nipat.gui.references import ReferenceCatalog

    fasta = _reference(tmp_path)
    ref = ReferenceCatalog(tmp_path / "catalog.json").register("custom", fasta)
    root = tmp_path / "runs"
    run = root / "archived"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"schema_version": 1, "workflow": "dnp-call",
                                             "status": "succeeded", "parameters": {}}))
    recorded = {k: ref[k] for k in ("fasta", "index", "build", "fasta_sha256", "index_sha256")}
    draft = {"reference": str(fasta), "samples": [], "reference_genome": recorded}
    gui = run / "gui.json"
    gui.write_text(json.dumps({"schema_version": 1, "draft": draft}))
    store = ResultsStore(root)
    selection, _ = store.igv_sources("archived")
    assert "historical_identity_incomplete" not in selection
    fasta.write_bytes(fasta.read_bytes().replace(b"ACGT", b"TTTT"))
    with pytest.raises(ValidationError, match="differisce"):
        local_igv.prepare({"reference": selection})
    del recorded["fasta_sha256"]
    gui.write_text(json.dumps({"schema_version": 1, "draft": draft}))
    old, _ = store.igv_sources("archived")
    reopened = local_igv.prepare({"reference": old})["sources"]["reference"]
    assert reopened["historical_identity_incomplete"] is True


def test_archived_bgzf_rejects_valid_but_replaced_gzi(local_igv, tmp_path):
    from nipat.gui.references import ReferenceCatalog

    plain = _reference(tmp_path)
    first = _bgzf(plain.read_bytes())
    fasta = tmp_path / "reference.fa.bgzf"
    fasta.write_bytes(first + _bgzf(b""))
    shutil.copyfile(str(plain) + ".fai", str(fasta) + ".fai")
    gzi = Path(str(fasta) + ".gzi")
    gzi.write_bytes(struct.pack("<Q", 0))
    entry = ReferenceCatalog(tmp_path / "catalog.json").register("custom", fasta)
    selection = {k: entry[k] for k in ("fasta", "index", "fasta_sha256", "index_sha256", "gzi_sha256")}
    assert local_igv.prepare({"reference": selection})["sources"]["reference"]["gzi_sha256"] == selection["gzi_sha256"]
    gzi.write_bytes(struct.pack("<QQQ", 1, len(first), plain.stat().st_size))
    with pytest.raises(ValidationError, match="differisce"):
        local_igv.prepare({"reference": selection})
