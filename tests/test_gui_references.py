import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import struct
from types import SimpleNamespace
from unittest.mock import Mock
import zlib

import pytest

from nipat.errors import ValidationError
from nipat.gui.app import DesktopApplication
from nipat.gui import references
from nipat.gui.references import ReferenceCatalog, build_fasta_index


@pytest.fixture
def catalog(tmp_path):
    return ReferenceCatalog(tmp_path / "prefs" / "references.json", language="en")


def fasta(tmp_path, data=b">first chromosome\r\nACGT\r\nNntc\r\na\r\n>second\nAgc"):
    path = tmp_path / "sample.fa"
    path.write_bytes(data)
    return path


def test_local_registration_index_restart_and_replacement(tmp_path, catalog):
    path = fasta(tmp_path)
    original = path.read_bytes()
    entry = catalog.register("custom", path)
    assert path.read_bytes() == original
    assert Path(entry["index"]).read_bytes() == b"first\t9\t19\t4\t6\nsecond\t3\t42\t3\t3\n"
    assert entry["naming"] == "other" and entry["available"] and entry["contigs"] == 2
    assert catalog.register("custom", path) == entry
    restored = ReferenceCatalog(catalog.path, language="en")
    assert restored.list()["entries"] == [entry]
    assert restored.resolve(entry["id"]) == entry
    path.write_bytes(original.replace(b"Agc", b"TGC"))
    assert not catalog.list()["entries"][0]["available"]
    with pytest.raises(ValidationError, match="missing or changed"):
        catalog.resolve(entry["id"])
    replacement = catalog.register("custom", path)
    assert replacement["id"] != entry["id"] and catalog.list()["entries"] == [replacement]
    path.unlink()
    assert not restored.list()["entries"][0]["available"]


@pytest.mark.parametrize("changed_file", ["fasta", "index"])
def test_same_metadata_rewrite_invalidates_registered_reference(tmp_path, catalog, monkeypatch, changed_file):
    path = fasta(tmp_path)
    entry = catalog.register("custom", path)
    target = Path(entry[changed_file])
    metadata = references._stamp
    old_stamp = metadata(target)
    original = target.read_bytes()
    updated = original.replace(b"Agc", b"TGC") if changed_file == "fasta" else original.replace(b"first", b"other")
    assert updated != original and len(updated) == len(original)
    target.write_bytes(updated)

    # Simulate the same file identity, size and timestamps after an in-place write.
    monkeypatch.setattr(references, "_stamp", lambda p: old_stamp if p == target else metadata(p))
    restored = ReferenceCatalog(catalog.path, language="en")
    assert not restored.list()["entries"][0]["available"]
    with pytest.raises(ValidationError, match="missing or changed"):
        restored.resolve(entry["id"])
    if changed_file == "fasta":
        replacement = restored.register("custom", path)
        assert replacement["id"] != entry["id"] and replacement["available"]
        assert restored.list()["entries"] == [replacement]
    else:
        with pytest.raises(ValidationError):
            restored.register("custom", path)


def test_legacy_metadata_only_reference_requires_explicit_reimport(tmp_path, catalog):
    path = fasta(tmp_path)
    old = catalog.register("custom", path)
    legacy = {key: old[key] for key in ("id", "build", "label", "fasta", "index", "naming", "contigs", "index_sha256")}
    legacy["stamps"] = {}
    for filename in (path, Path(old["index"])):
        stat = filename.stat()
        legacy["stamps"][filename.name] = [
            stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
        ]
    catalog.path.write_text(json.dumps({"schema_version": 1, "entries": [legacy]}), encoding="utf-8")
    restored = ReferenceCatalog(catalog.path, language="en")
    assert not restored.list()["entries"][0]["available"]
    with pytest.raises(ValidationError, match="missing or changed"):
        restored.resolve(old["id"])
    verified = restored.register("custom", path)
    assert verified["id"] != old["id"] and verified["available"]
    assert restored.list()["entries"] == [verified]
    assert restored.resolve(verified["id"]) == verified


@pytest.mark.parametrize(("header", "notation"), [("chr1", "chr"), ("1", "unprefixed"), ("NC_000001.10", "accession")])
def test_family_selection_uses_index_geometry_and_nuclear_lengths(tmp_path, catalog, monkeypatch, header, notation):
    # Scale the dictionary to keep registration and on-disk test data small.
    assert references._PRIMARY["grch37"][0] == 249250621
    assert references._PRIMARY["grch38"][0] == 248956422
    monkeypatch.setitem(references._PRIMARY, "grch37", (12,) + references._PRIMARY["grch37"][1:])
    path = fasta(tmp_path, (f">{header}\nACGTAC\nNNNNNN\n").encode())
    entry = catalog.register("grch37", path)
    assert entry["naming"] == notation and entry["build"] == "grch37"
    with pytest.raises(ValidationError, match="dictionary"):
        catalog.register("grch38", path)
    assert [x["id"] for x in catalog.list()["builds"]] == ["grch37", "grch38", "custom"]


def test_names_and_mitochondrial_contigs_do_not_establish_assembly(tmp_path, catalog):
    path = fasta(tmp_path, b">chrM\nACGT\n")
    hg = path.rename(tmp_path / "hg38.fa")
    with pytest.raises(ValidationError, match="No nuclear chromosome"):
        catalog.register("grch38", hg)


def test_different_fasta_indexes_with_matching_first_name_and_size(tmp_path, catalog):
    path = fasta(tmp_path, b">first\nAAAA\n>differ\nTGCA\n")
    index = build_fasta_index(path)
    index.write_bytes(index.read_bytes().replace(b"differ", b"second"))
    with pytest.raises(ValidationError, match="indexes do not match"):
        catalog.register("custom", path)


def test_shared_catalog_concurrent_register_is_idempotent(tmp_path, catalog):
    path = fasta(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: catalog.register("custom", path)["id"], range(8)))
    assert len(set(ids)) == len(catalog.list()["entries"]) == 1


@pytest.mark.parametrize("data", [b">a\nAAAA\nAA\nAAAA\n", b">z\nAC\n>z\nTT\n", b">a\n>z\nAC\n",
                                  b"not fasta\n", b">chr1\nAC GT\n"])
def test_invalid_fasta_leaves_input_and_registry_intact(tmp_path, catalog, data):
    path = fasta(tmp_path, data)
    with pytest.raises(ValidationError):
        catalog.register("custom", path)
    assert path.read_bytes() == data
    assert not Path(str(path) + ".fai").exists() and not catalog.path.exists()


def test_native_picker_cancel_register_resolve_and_no_network(tmp_path, catalog):
    file = fasta(tmp_path)
    picker = Mock(pick_files=Mock(side_effect=[None, [file]]))
    app = DesktopApplication(host=picker, service=SimpleNamespace(reference_catalog=lambda _: catalog))
    try:
        assert app.call("references.list", {})["entries"] == []
        assert app.call("references.register", {"build": "custom"}) == {"cancelled": True}
        result = app.call("references.register", {"build": "custom", "language": "en"})
        assert app.call("references.resolve", {"id": result["entry"]["id"]}) == result
    finally:
        app.server.close()


def test_bad_registry_not_overwritten_by_new_import(tmp_path, catalog):
    catalog.path.parent.mkdir()
    invalid = json.dumps({"schema_version": 1, "entries": [{"id": "missing"}]})
    catalog.path.write_text(invalid)
    with pytest.raises(ValidationError, match="Cannot read"):
        catalog.register("custom", fasta(tmp_path))
    assert catalog.path.read_text() == invalid


def bgzf_block(data):
    payload = zlib.compress(data)[2:-4]
    size = 18 + len(payload) + 8
    return (b"\x1f\x8b\x08\x04" + bytes(6) + b"\x06\x00BC\x02\x00" + struct.pack("<H", size - 1)
            + payload + struct.pack("<II", zlib.crc32(data), len(data)))


def test_bgzf_seeks_and_checks_real_dictionary_across_blocks(tmp_path, catalog, monkeypatch):
    first = b">chrTest\nAAAA\n"
    second = b">second\nTTTT\n"
    path = tmp_path / "genome.fa.bgzf"
    cfirst = bgzf_block(first)
    path.write_bytes(cfirst + bgzf_block(second) + bgzf_block(b""))
    index = Path(str(path) + ".fai")
    index.write_bytes(b"chrTest\t4\t9\t4\t5\nsecond\t4\t22\t4\t5\n")
    gzi = Path(str(path) + ".gzi")
    gzi.write_bytes(struct.pack("<QQQ", 1, len(cfirst), len(first)))
    entry = catalog.register("custom", path)
    assert entry["compressedIndex"] == str(gzi)
    metadata = references._stamp
    gzi_stamp = metadata(gzi)
    with monkeypatch.context() as patch:
        patch.setattr(references, "_stamp", lambda p: gzi_stamp if p == gzi else metadata(p))
        gzi.write_bytes(struct.pack("<QQQ", 1, 0, len(first)))
        with pytest.raises(ValidationError, match="missing or changed"):
            catalog.resolve(entry["id"])
        with pytest.raises(ValidationError, match="indexes do not match"):
            catalog.register("custom", path)
    gzi.write_bytes(struct.pack("<QQQ", 1, len(cfirst), len(first)))
    index.write_bytes(index.read_bytes().replace(b"second", b"wrongx"))
    with pytest.raises(ValidationError, match="indexes do not match"):
        catalog.register("custom", path)
    path.write_bytes(gzip.compress(first + second))
    with pytest.raises(ValidationError):
        catalog.register("custom", path)


def test_single_long_unwrapped_contig_can_be_indexed_and_reopened(tmp_path, catalog):
    path = fasta(tmp_path, b">single\n" + b"A" * (1024 * 1024 + 1) + b"\r\n")
    entry = catalog.register("custom", path)
    assert catalog.resolve(entry["id"])["available"]
    assert Path(entry["index"]).read_text().split()[1:] == ["1048577", "8", "1048577", "1048579"]


@pytest.mark.parametrize("sampled", [True, False])
def test_large_reference_list_is_bounded_and_resolution_checks_every_byte(tmp_path, catalog, monkeypatch, sampled):
    path = fasta(tmp_path, b">first\n" + b"A" * (2 * 1024 * 1024) + b"\n")
    metadata = references._stamp
    fasta_stamp = metadata(path)
    monkeypatch.setattr(references, "_stamp", lambda p: fasta_stamp if p == path else metadata(p))
    entry = catalog.register("custom", path)
    assert catalog.register("custom", path) == entry
    assert catalog.resolve(entry["id"]) == entry
    with path.open("r+b") as stream:
        stream.seek(path.stat().st_size - 2 if sampled else 700_000)
        stream.write(b"T")

    # Count bytes on the FASTA itself; index and registry reads have separate costs.
    with monkeypatch.context() as patch:
        open_file = Path.open
        read_sizes = []

        @contextmanager
        def track_reads(self, *args, **kwargs):
            with open_file(self, *args, **kwargs) as stream:
                if self != path:
                    yield stream
                    return
                observed = Mock(spec=stream, wraps=stream)
                def read(*arguments):
                    data = stream.read(*arguments)
                    read_sizes.append(len(data))
                    return data
                observed.read.side_effect = read
                observed.readinto.side_effect = AssertionError("Full FASTA digest during listing")
                yield observed

        patch.setattr(Path, "open", track_reads)
        assert catalog.list()["entries"][0]["available"] == (not sampled)
        assert 0 < sum(read_sizes) < 128 * 1024
    with pytest.raises(ValidationError, match="missing or changed"):
        catalog.resolve(entry["id"])
    replacement = catalog.register("custom", path)
    assert replacement["id"] != entry["id"]
    assert catalog.resolve(replacement["id"]) == replacement


def test_read_only_directory_help(tmp_path, catalog, monkeypatch):
    path = fasta(tmp_path)
    def readonly(*args, **kwargs):
        raise PermissionError("read-only")
    monkeypatch.setattr(references.tempfile, "NamedTemporaryFile", readonly)
    with pytest.raises(ValidationError, match="writable folder"):
        catalog.register("custom", path)


def test_cancel_and_failed_index_do_not_publish(tmp_path):
    path = fasta(tmp_path)
    with pytest.raises(RuntimeError, match="cancelled"):
        build_fasta_index(path, check_cancel=Mock(side_effect=RuntimeError("cancelled")))
    assert list(tmp_path.iterdir()) == [path]


def test_refseq_accession_version_must_match_the_selected_family(tmp_path, catalog, monkeypatch):
    monkeypatch.setitem(references._PRIMARY, "grch37", (4,) + references._PRIMARY["grch37"][1:])
    path = fasta(tmp_path, b">NC_000001.11\nAGCT\n")
    with pytest.raises(ValidationError, match="dictionary"):
        catalog.register("grch37", path)


def test_blank_lines_between_fasta_records_match_faidx(tmp_path, catalog):
    path = fasta(tmp_path, b">a\nACGT\n\n>b\nTC\n\n")
    entry = catalog.register("custom", path)
    assert Path(entry["index"]).read_bytes() == b"a\t4\t3\t4\t5\nb\t2\t12\t2\t3\n"
