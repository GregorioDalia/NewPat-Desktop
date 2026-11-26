"""Generated truth sets for the DNP/SNP engine, independent of previous releases.

Each locus declares REF, ALT and observations before writing FASTA/SAM. Expected
counts come from the declared observations. The diploid oracle uses the closed
forms for the two homozygotes and n*log(1/2) for the heterozygote. BAQ is off
so that SAM Phred scores remain known. No values are copied from a NewPat run.
"""

from collections import Counter
from dataclasses import dataclass
import itertools
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from native_engine_helpers import execute_workflow
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
from test_native_r_edge_cases import table


# Each triple is (REF, ALT, Other). The last five distinguish <, == and >
# the default Other threshold (0.1), Other-only and entirely uncovered sites.
MIXTURES = ((8, 0, 0), (0, 8, 0), (4, 4, 0), (9, 1, 0), (1, 9, 0),
            (9, 1, 1), (8, 1, 1), (7, 1, 1), (0, 0, 3), (0, 0, 0))


@dataclass(frozen=True)
class Read:
    allele: str
    qualities: tuple[int, ...]
    mapq: int = 60
    flag: int = 0


@dataclass(frozen=True)
class Locus:
    contig: str
    pos: int
    ref: str
    alt: str
    reads: tuple[Read, ...]


def allele_matrix(width):
    alleles = ["".join(pair) for pair in itertools.product("ACGT", repeat=width)]
    loci = []
    for ref, alt in itertools.permutations(alleles, 2):
        other = next(value for value in alleles if value not in (ref, alt))
        for ref_count, alt_count, other_count in MIXTURES:
            reads = []
            for allele, count, qualities in ((ref, ref_count, (20, 32)),
                                            (alt, alt_count, (38, 20)),
                                            (other, other_count, (35, 35))):
                reads.extend(Read(allele, qualities[:width], flag=16 if i % 2 else 0)
                             for i in range(count))
            index = len(loci)
            # Reuse positions on different contigs; duplicate coordinates across
            # contigs must retain independent allele counts and likelihoods.
            loci.append(Locus(("matrixA", "matrixB")[index % 2], 12 + 15 * (index // 2),
                              ref, alt, tuple(reads)))
    return loci


def write_fixture(root, loci):
    """Write a small artificial assembly, panel, and sorted indexed BAM."""
    width = len(loci[0].ref)
    contigs = {}
    for locus in loci:
        contigs[locus.contig] = max(contigs.get(locus.contig, 0), locus.pos + 12)
    sequences = {name: list(("ACGT" * ((length + 3) // 4))[:length]) for name, length in contigs.items()}
    for locus in loci:
        sequences[locus.contig][locus.pos - 1:locus.pos - 1 + width] = locus.ref
    reference = root / "reference.fa"
    with reference.open("w", newline="\n") as out:
        for name, bases in sequences.items():
            out.write(f">{name}\n")
            for start in range(0, len(bases), 61):
                out.write("".join(bases[start:start + 61]) + "\n")
    subprocess.run(["samtools", "faidx", str(reference)], check=True, capture_output=True)

    panel = root / "panel.tsv"
    with panel.open("w", newline="\n") as out:
        if width == 1:
            out.write("chr\tpos\tref\talt\n")
        for locus in loci:
            coordinates = [locus.contig, str(locus.pos)]
            if width == 2:
                coordinates.append(str(locus.pos + 1))
            out.write("\t".join([*coordinates, locus.ref, locus.alt]) + "\n")

    sam = root / "reads.sam"
    with sam.open("w", newline="\n") as out:
        out.write("@HD\tVN:1.6\tSO:coordinate\n")
        for name, length in contigs.items():
            out.write(f"@SQ\tSN:{name}\tLN:{length}\n")
        target_order = {name: index for index, name in enumerate(contigs)}
        for locus in sorted(loci, key=lambda item: (target_order[item.contig], item.pos)):
            # SAM SEQ/QUAL are supplied in alignment orientation on either strand.
            seq = sequences[locus.contig]
            left = "".join(seq[locus.pos - 4:locus.pos - 1])
            right = "".join(seq[locus.pos - 1 + width:locus.pos + 2 + width])
            for i, read in enumerate(locus.reads):
                name = f"r_{locus.contig}_{locus.pos}_{i}"
                bases = left + read.allele + right
                qual = "III" + "".join(chr(q + 33) for q in read.qualities) + "III"
                out.write(f"{name}\t{read.flag}\t{locus.contig}\t{locus.pos - 3}\t{read.mapq}\t"
                          f"{len(bases)}M\t*\t0\t0\t{bases}\t{qual}\n")
    bam = root / "sample_0001.bam"
    subprocess.run(["samtools", "view", "-b", "-o", str(bam), str(sam)], check=True, capture_output=True)
    subprocess.run(["samtools", "index", str(bam)], check=True, capture_output=True)
    return bam, panel, reference


def expected_likelihoods(ref_reads, alt_reads):
    def errors(reads):
        return [10 ** (-sum(read.qualities) / (10 * len(read.qualities))) for read in reads]

    def log_correct(error):
        return -math.inf if error == 1 else math.log1p(-error)

    ref_errors, alt_errors = errors(ref_reads), errors(alt_reads)
    return (sum(log_correct(e) for e in ref_errors) + sum(math.log(e) for e in alt_errors),
            -(len(ref_reads) + len(alt_reads)) * math.log(2),
            sum(math.log(e) for e in ref_errors) + sum(log_correct(e) for e in alt_errors))


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class NativeCallerOracle(unittest.TestCase):
    def run_and_check(self, width, root, sources, loci, settings, accepted=None, imported=None):
        bam, panel, reference = sources
        if width == 1:
            workflow = "snp-call"
            fields = (dict(mode="pileup", pileup=str(imported), bam=None, reference=None)
                      if imported else dict(mode="bam", pileup=None, bam=str(bam), reference=str(reference)))
            result_file = "SNPcall_output.txt"
        else:
            workflow = "dnp-call"
            fields = dict(samples=[{"sample_id": "sample_0001", "path": str(bam)}],
                          reference=str(reference), parallel=False)
            result_file = "individual_outputs/full_output_sample_0001.txt"
        proc = execute_workflow(workflow, root, panel=str(panel), scientific_settings=settings,
                              timeout=240, **fields)
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-3000:])
        rows = table(root / "output" / result_file)
        expected = {(locus.contig, locus.pos): locus for locus in loci}
        actual = {(row["chr"], int(row["pos" if width == 1 else "pos1"])): row for row in rows}
        self.assertEqual(len(rows), len(expected))
        self.assertEqual(actual.keys(), expected.keys())
        for key, locus in expected.items():
            with self.subTest(workflow=workflow, contig=key[0], pos=key[1], settings=settings):
                self.check_locus(actual[key], locus, accepted[key] if accepted is not None else locus.reads,
                                 settings.get("other_fraction_max", 0.1))
        return root / "work"

    def check_locus(self, row, locus, reads, threshold):
        self.assertEqual((row["REF"], row["ALT"]), (locus.ref, locus.alt))
        dnp = len(locus.ref) == 2
        if dnp:
            self.assertEqual(int(row["pos2"]), locus.pos + 1)
        counts = Counter(read.allele for read in reads)
        nr, na = counts[locus.ref], counts[locus.alt]
        n_other = len(reads) - nr - na
        self.assertEqual(tuple(int(row[name]) for name in ("N_REF", "N_ALT", "N_Other")),
                         (nr, na, n_other))
        if reads:
            self.assertEqual(int(row["total_count"]), len(reads))
            allele_counts = dict(zip(row["combined_bases"].split("-"),
                                     map(int, row["combined_counts"].split("-")), strict=True))
            self.assertEqual(allele_counts, counts)
            self.assertEqual(int(row["reads_discarded_for_indels"]), 0)
        if nr + na == 0:
            self.assertEqual(row["GT"], "NA")
            if not dnp:
                self.assertEqual((row["ratio"], row["GL0"], row["GL1"], row["GL2"]), ("NA",) * 4)
                self.assertEqual(int(row["total_count"]), len(reads))
            return
        expected = expected_likelihoods([r for r in reads if r.allele == locus.ref],
                                        [r for r in reads if r.allele == locus.alt])
        for i, value in enumerate(expected):
            # DNP rounds to three decimal places when serialising its full table.
            self.assertAlmostEqual(float(row[f"GL{i}"]), value, delta=0.0005000001 if dnp else 1e-10)
        if not dnp:
            self.assertAlmostEqual(float(row["ratio"]), nr / (nr + na), delta=1e-12)
        best = ("0/0", "0/1", "1/1")[expected.index(max(expected))]
        self.assertEqual(row["GT"], "NA" if n_other / len(reads) >= threshold else best)

    def test_all_ordered_allele_pairs_crossed_with_ten_depth_mixtures(self):
        for width in (1, 2):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                loci = allele_matrix(width)
                self.assertEqual(len(loci), 120 if width == 1 else 2400)
                self.run_and_check(width, root / "matrix", write_fixture(root, loci), loci, {"baq": False})

    def test_acquisition_and_mask_boundaries(self):
        # Full reads with one measurement just below the cut, equal, or above it.
        # A DUP-flagged read passes only when excluded_flags is explicitly cleared.
        for width in (1, 2):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ref, alt, other = "AC"[:width], "GT"[:width], "TG"[:width]
                reads = tuple(Read(allele, quality[:width], mapq, flag) for allele, quality, mapq, flag in (
                    (ref, (19, 35), 45, 0), (alt, (20, 35), 45, 16), (ref, (21, 35), 45, 16),
                    (other, (35, 35), 29, 0), (ref, (35, 35), 30, 0), (alt, (35, 35), 31, 0),
                    (other, (35, 35), 45, 1024),
                ))
                locus = Locus("matrixA", 25, ref, alt, reads)
                sources = write_fixture(root, [locus])
                cases = (
                    ("base-cut", {"min_base_quality": 20}, (1, 2, 3, 4, 5)),
                    ("mapping-cut", {"min_mapping_quality": 30}, (0, 1, 2, 4, 5)),
                    ("both-cuts", {"min_base_quality": 20, "min_mapping_quality": 30}, (1, 2, 4, 5)),
                    ("dup-included", {"min_base_quality": 20, "min_mapping_quality": 30,
                                      "excluded_flags": 0, "other_fraction_max": 0.2}, (1, 2, 4, 5, 6)),
                    ("mask-relaxed", {"min_base_quality": 20, "min_mapping_quality": 30,
                                      "excluded_flags": 0, "other_fraction_max": 0.21}, (1, 2, 4, 5, 6)),
                )
                for name, settings, indices in cases:
                    with self.subTest(profile=name):
                        accepted = {(locus.contig, locus.pos): [reads[i] for i in indices]}
                        work = self.run_and_check(width, root / name, sources, [locus],
                                                  {"baq": False, **settings}, accepted)
                        if width == 1 and name == "both-cuts":
                            # The acquired pileup stores the four surviving calls.
                            # Importing it with a higher acquisition threshold cannot discard them again.
                            self.run_and_check(1, root / "import", sources, [locus],
                                               {"min_base_quality": 40}, accepted,
                                               imported=work / "pileup.txt")

    def test_depth_cap_and_anomalous_pairs(self):
        for width in (1, 2):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ref, alt = "AC"[:width], "GT"[:width]
                qualities = (32,) * width
                # At the cap locus every read carries the same allele and quality,
                # so the expected count and likelihood do not depend on sampling order.
                depth = Locus("matrixA", 25, ref, alt, (Read(ref, qualities),) * 8)
                # The last read is the mapped first segment of a pair with its mate unmapped.
                orphan = Locus("matrixB", 25, ref, alt,
                               (Read(alt, qualities), Read(ref, qualities, flag=73)))
                # All bases fail Q13. The selected locus must still appear with missing GT.
                low_q = Locus("matrixB", 55, ref, alt, (Read(ref, (10,) * width),))
                loci = [depth, orphan, low_q]
                sources = write_fixture(root, loci)
                for label, maximum, include_orphans, depth_count, orphan_count in (
                    ("limited", 3, False, 3, 1), ("unlimited", 0, True, 8, 2),
                ):
                    with self.subTest(profile=label):
                        self.run_and_check(width, root / label, sources, loci,
                                           {"baq": False, "max_depth": maximum, "include_orphans": include_orphans},
                                           {(depth.contig, depth.pos): depth.reads[:depth_count],
                                            (orphan.contig, orphan.pos): orphan.reads[:orphan_count],
                                            (low_q.contig, low_q.pos): ()})

    def test_phred_zero_preserves_impossible_genotype_likelihoods(self):
        for width in (1, 2):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ref, alt = "AC"[:width], "GT"[:width]
                zero = (0,) * width
                # With one REF and one ALT at Q0, both homozygotes have log(0).
                # With REF alone only the ref homozygote is impossible.
                loci = [Locus("matrixA", 15, ref, alt, (Read(ref, zero), Read(alt, zero))),
                        Locus("matrixA", 35, ref, alt, (Read(ref, zero),)),
                        Locus("matrixA", 55, ref, alt, ())]
                self.run_and_check(width, root / "zero", write_fixture(root, loci), loci,
                                   {"baq": False, "min_base_quality": 0})
