"""Shared example inputs must work after extraction, without the source checkout."""

import csv
from collections import Counter
import hashlib
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

from newpat_scientific.files import require_count_input, require_population_frequencies
from newpat_scientific.panels import read_dnp_list, read_position_panel, read_snp_list


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
ROOT = EXAMPLES / "synthetic-trio"
ROLES = ("mother", "father", "child")


def test_published_bundle_matches_the_browsable_example_and_its_manifest():
    archive = EXAMPLES / "newpat-synthetic-trio.zip"
    assert archive.with_suffix(".zip.sha256").read_text().split() == [
        hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name]
    files = {p.relative_to(ROOT).as_posix(): p for p in ROOT.rglob("*") if p.is_file()}
    manifest = {}
    for line in files["SHA256SUMS"].read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert name not in manifest
        manifest[name] = digest
    assert set(manifest) == set(files) - {"SHA256SUMS"}
    with zipfile.ZipFile(archive) as bundle:
        assert sorted(bundle.namelist()) == sorted("synthetic-trio/" + name for name in files)
        for name, source in files.items():
            payload = bundle.read("synthetic-trio/" + name)
            assert payload == source.read_bytes()
            if name in manifest:
                assert hashlib.sha256(payload).hexdigest() == manifest[name]


@pytest.mark.parametrize("marker", ("dnp", "snp"))
def test_marker_inputs_are_accepted_by_the_normal_scientific_validators(marker):
    marker_type = marker.upper()
    caller = read_dnp_list if marker == "dnp" else read_snp_list
    sites = caller(ROOT / "panels" / f"{marker}.tsv")
    assert len(sites) == 3
    assert not require_population_frequencies(ROOT / "frequencies" / f"{marker}.tsv", marker_type)
    full = read_position_panel(ROOT / "panels" / f"{marker}-full.tsv", marker_type)
    first = read_position_panel(ROOT / "panels" / f"{marker}-first.tsv", marker_type)
    assert len(full) == 3 and first == full[:1]
    for role in ROLES:
        assert not require_count_input(ROOT / "counts" / marker / (role + ".txt"), marker_type)


@pytest.mark.skipif(not shutil.which("samtools"), reason="requires samtools for indexed readback")
def test_each_indexed_bam_reproduces_the_counts_in_the_example():
    fasta = ROOT / "reference/synthetic.fa"
    for role in ROLES:
        bam = ROOT / f"alignments/{role}.bam"
        subprocess.run(["samtools", "quickcheck", bam], check=True)
        for marker in ("dnp", "snp"):
            with (ROOT / f"counts/{marker}/{role}.txt").open() as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    start = int(row["pos1"] if marker == "dnp" else row["pos"])
                    end = int(row["pos2"]) if marker == "dnp" else start
                    locus = f'{row["chr"]}:{start}-{end}'
                    reference = subprocess.check_output(["samtools", "faidx", fasta, locus], text=True)
                    assert "".join(reference.splitlines()[1:]) == row["REF"]
                    reads = subprocess.check_output(["samtools", "view", bam, locus], text=True)
                    observed = []
                    for line in reads.splitlines():
                        fields = line.split("\t")
                        # Every fixture read is contiguous and aligned end to end.
                        assert fields[5] == f"{len(fields[9])}M"
                        offset = start - int(fields[3])
                        assert 0 <= offset <= len(fields[9]) - len(row["REF"])
                        observed.append(fields[9][offset:offset + len(row["REF"])])
                    assert observed.count(row["REF"]) == int(row["N_REF"])
                    assert observed.count(row["ALT"]) == int(row["N_ALT"])
                    assert len(observed) == int(row["total_count"]) == 100


def test_timing_panels_cover_the_same_128_loci_in_both_markers():
    folder = ROOT / "timing"
    dnps = read_dnp_list(folder / "dnp.tsv")
    snps = read_snp_list(folder / "snp.tsv")
    positions = [(f"chrTiming{i:02d}", pos) for i in range(1, 5) for pos in range(64, 4096, 128)]
    assert [(d.chromosome, d.pos1) for d in dnps] == positions
    assert [(s.chromosome, s.position) for s in snps] == positions
    for dnp, snp in zip(dnps, snps, strict=True):
        assert dnp.pos2 == dnp.pos1 + 1
        assert (snp.reference, snp.alternative) == (dnp.reference[0], dnp.alternative[0])


@pytest.mark.skipif(not shutil.which("samtools"), reason="requires samtools for indexed readback")
def test_timing_bam_and_reference_have_the_documented_depth_and_alleles():
    folder = ROOT / "timing"
    sites = read_dnp_list(folder / "dnp.tsv")
    for chrom in sorted({site.chromosome for site in sites}):
        ref = subprocess.check_output(["samtools", "faidx", folder / "reference.fa", chrom], text=True)
        sequence = "".join(ref.splitlines()[1:])
        assert len(sequence) == 4096
        observed = Counter()
        with subprocess.Popen(["samtools", "view", folder / "timing.bam", chrom],
                              stdout=subprocess.PIPE, text=True) as reads:
            for line in reads.stdout:
                fields = line.split("\t")
                assert fields[2] == chrom and fields[5] == "64M"
                first = int(fields[3]) + 30
                observed[(first, fields[9][30:32])] += 1
            assert reads.wait() == 0
        expected = {}
        for site in sites:
            if site.chromosome == chrom:
                assert sequence[site.pos1 - 1:site.pos2] == site.reference
                expected[(site.pos1, site.reference)] = 600
                expected[(site.pos1, site.alternative)] = 400
        assert observed == expected
