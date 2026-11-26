"""Rebuild the public example and its ZIP in a fresh output directory (samtools 1.21)."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile, ZipInfo

PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT / "tests/fixtures"
sys.path.insert(0, str(PROJECT / "scripts/acceptance"))
from installed_workflows import _positive_sams

ROLES = {"mother": (96, 4), "father": (50, 50), "child": (50, 50)}
ARCHIVE = "newpat-synthetic-trio.zip"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tsv(path: Path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_tables(root: Path, marker: str, loci: list[tuple], alleles: list[tuple]) -> None:
    coordinates = ("chr", "pos1", "pos2") if marker == "dnp" else ("chr", "pos")
    for label, selected in (("full", loci), ("first", loci[:1])):
        tsv(root / f"panels/{marker}-{label}.tsv", coordinates, selected)
    tsv(root / f"frequencies/{marker}.tsv", (*coordinates, "Ref_f.pop", "Alt_f.pop"),
        [(*locus, "0.75", "0.25") for locus in loci])
    for role, (n_ref, n_alt) in ROLES.items():
        tsv(root / f"counts/{marker}/{role}.txt",
            (*coordinates, "REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count"),
            [(*locus, ref, alt, n_ref, n_alt, 0, n_ref + n_alt)
             for locus, (ref, alt) in zip(loci, alleles, strict=True)])


def create_timing_inputs(folder: Path, samtools: str) -> None:
    """A fixed four-contig workload, independently runnable from the trio."""
    folder.mkdir()
    reference = folder / "reference.fa"
    bam = folder / "timing.bam"
    contigs = {f"chrTiming{i:02d}": motif * 1024
               for i, motif in enumerate(("ACGT", "TGCA", "GTAC", "CATG"), 1)}
    with reference.open("w", encoding="ascii", newline="\n") as fasta:
        for chrom, sequence in contigs.items():
            fasta.write(f">{chrom}\n")
            for offset in range(0, len(sequence), 64):
                fasta.write(sequence[offset:offset + 64] + "\n")
    subprocess.run([samtools, "faidx", reference], check=True)

    snp_rows = []
    complement = str.maketrans("ACGT", "TGCA")
    with TemporaryDirectory() as tmp:
        sam = Path(tmp) / "timing.sam"
        with sam.open("w", encoding="ascii", newline="\n") as reads, \
                (folder / "dnp.tsv").open("w", encoding="ascii", newline="\n") as dnp:
            reads.write("@HD\tVN:1.6\tSO:coordinate\n")
            for chrom, sequence in contigs.items():
                reads.write(f"@SQ\tSN:{chrom}\tLN:{len(sequence)}\n")
            for chrom, sequence in contigs.items():
                for position in range(64, 4096, 128):
                    ref = sequence[position - 1:position + 1]
                    alt = ref.translate(complement)
                    dnp.write(f"{chrom}\t{position}\t{position + 1}\t{ref}\t{alt}\n")
                    snp_rows.append((f"{chrom}:{position}", ref[0], alt[0]))
                    start = position - 30
                    ref_read = sequence[start - 1:start - 1 + 64]
                    alt_read = ref_read[:30] + alt + ref_read[32:]
                    for number in range(1000):
                        bases = ref_read if number < 600 else alt_read
                        flag = 16 if number % 2 else 0
                        reads.write(f"{chrom}_{position}_{number:04d}\t{flag}\t{chrom}\t{start}"
                                    f"\t60\t64M\t*\t0\t0\t{bases}\t{'I' * 64}\n")
        subprocess.run([samtools, "view", "--no-PG", "-b", "-o", bam, sam], check=True)
    subprocess.run([samtools, "index", bam], check=True)
    subprocess.run([samtools, "quickcheck", bam], check=True)
    tsv(folder / "snp.tsv", ("pos", "ref", "alt"), snp_rows)


def create_inputs(root: Path, samtools: str) -> None:
    for folder in ("alignments", "reference", "panels", "frequencies", "counts/dnp", "counts/snp"):
        (root / folder).mkdir(parents=True)
    shutil.copyfile(FIXTURES / "dnp_engine/reference.fa", root / "reference/synthetic.fa")
    subprocess.run([samtools, "faidx", root / "reference/synthetic.fa"], check=True)
    panel = root / "panels/dnp.tsv"
    shutil.copyfile(FIXTURES / "dnp_engine/DNP_list.txt", panel)
    with panel.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    dnp_loci = [(chrom, int(first), int(second)) for chrom, first, second, _, _ in rows]
    dnp_alleles = [(ref.upper(), alt.upper()) for _, _, _, ref, alt in rows]
    snp_loci = [(chrom, first) for chrom, first, _ in dnp_loci]
    snp_alleles = [(ref[0], alt[0]) for ref, alt in dnp_alleles]
    tsv(root / "panels/snp.tsv", ("pos", "ref", "alt"),
        [(f"{chrom}:{pos}", ref, alt) for (chrom, pos), (ref, alt) in zip(snp_loci, snp_alleles, strict=True)])
    write_tables(root, "dnp", dnp_loci, dnp_alleles)
    write_tables(root, "snp", snp_loci, snp_alleles)
    with TemporaryDirectory() as tmp:
        staging = Path(tmp)
        _positive_sams(FIXTURES, staging)
        for role in ROLES:
            template = staging / ("maternal.sam" if role == "mother" else "paternal.sam")
            sam = staging / f"{role}.sam"
            # Distinct synthetic read identities even where two roles share the same recipe.
            with sam.open("w", encoding="ascii", newline="\n") as stream:
                for line in template.read_text(encoding="ascii").splitlines():
                    stream.write((line if line.startswith("@") else f"{role}_{line}") + "\n")
            bam = root / f"alignments/{role}.bam"
            subprocess.run([samtools, "sort", "--no-PG", "-o", bam, sam], check=True)
            subprocess.run([samtools, "index", bam], check=True)
            subprocess.run([samtools, "quickcheck", bam], check=True)


def build(output: Path, samtools: str) -> None:
    root = output / "synthetic-trio"
    output.mkdir(parents=True, exist_ok=False)
    create_inputs(root, samtools)
    create_timing_inputs(root / "timing", samtools)
    shutil.copyfile(PROJECT / "examples/synthetic-trio/README.md", root / "README.md")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    listing = "".join(f"{digest(path)}  {path.relative_to(root).as_posix()}\n" for path in files)
    (root / "SHA256SUMS").write_text(listing, encoding="ascii", newline="\n")
    archive = output / ARCHIVE
    with ZipFile(archive, "w", compression=ZIP_STORED) as bundle:
        for path in sorted([*files, root / "SHA256SUMS"]):
            info = ZipInfo(path.relative_to(output).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    (output / (ARCHIVE + ".sha256")).write_text(f"{digest(archive)}  {ARCHIVE}\n",
                                                encoding="ascii", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    parser.add_argument("--samtools", default="samtools", help="samtools executable")
    options = parser.parse_args()
    build(options.output, options.samtools)
