"""Known-answer experiments from synthetic alignments, through the scientific engine.

Each read spans the four bases used by the callers. The mixed reads include
one recombinant that is Other as a dinucleotide and REF at the single base.
All references have the same sequence dictionary, including the swapped one.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from native_engine_helpers import execute_workflow
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
from test_native_r_edge_cases import table


# The long contig forces the last target into another BGZF block. The windows
# at 2 and length-2 use the first and last possible DNP flanking bases.
LENGTHS = {"chrLab_A": 70000, "scaffold.02": 37}
LOCI = (("chrLab_A", 2, "AC", "GT"), ("chrLab_A", 69998, "TG", "CA"),
        ("scaffold.02", 2, "GA", "TC"), ("scaffold.02", 35, "CT", "AG"))
# Recipe per BAM in LOCI order. Disjoint calls at identical numeric positions
# catch joins that drop the contig or fail to retain sample identity.
PROFILES = {"A": ("ref", "mixed", "alt", "empty"), "B": ("alt", "empty", "mixed", "ref"),
            "C": ("mixed", "alt", "empty", "mixed")}
COUNTS = {"ref": (20, 0, 0), "mixed": (10, 10, 1), "alt": (0, 20, 0), "empty": (0, 0, 0)}
GENOTYPES = {"ref": "0/0", "mixed": "0/1", "alt": "1/1", "empty": "NA"}


def samtools(*arguments):
    subprocess.run(["samtools", *map(str, arguments)], check=True, capture_output=True, text=True)


def reference_and_panel(folder, swapped):
    fasta = folder / "custom.fa"
    sequences = {chrom: list("C" * length) for chrom, length in LENGTHS.items()}
    dnp, snp = [], ["chr\tpos\tref\talt"]
    for chrom, pos, first, second in LOCI:
        ref, alt = (second, first) if swapped else (first, second)
        sequences[chrom][pos - 2:pos + 2] = "G" + ref + "T"
        dnp.append(f"{chrom}\t{pos}\t{pos + 1}\t{ref}\t{alt}")
        snp.append(f"{chrom}\t{pos}\t{ref[0]}\t{alt[0]}")
    with fasta.open("w", encoding="ascii", newline="\n") as stream:
        for chrom, bases in sequences.items():
            stream.write(f">{chrom}\n")
            for offset in range(0, len(bases), 61):
                stream.write("".join(bases[offset:offset + 61]) + "\n")
    for marker, lines in (("dnp", dnp), ("snp", snp)):
        (folder / f"{marker}.tsv").write_text("\n".join(lines) + "\n", encoding="ascii")
    samtools("faidx", fasta)
    return fasta


def sample_bam(folder, profile):
    sam, bam = folder / f"{profile}.sam", folder / f"{profile}.bam"
    with sam.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("@HD\tVN:1.6\tSO:coordinate\n")
        for chrom, length in LENGTHS.items():
            stream.write(f"@SQ\tSN:{chrom}\tLN:{length}\n")
        for (chrom, pos, ref, alt), recipe in zip(LOCI, PROFILES[profile], strict=True):
            n_ref, n_alt, n_other = COUNTS[recipe]
            alleles = [ref] * n_ref + [alt] * n_alt + [ref[0] + alt[1]] * n_other
            for index, allele in enumerate(alleles):
                flag = 16 if index % 2 else 0
                stream.write(f"{profile}.{chrom}.{pos}.{index}\t{flag}\t{chrom}\t{pos - 1}"
                             f"\t60\t4M\t*\t0\t0\tG{allele}T\tIIII\n")
    samtools("view", "--no-PG", "-b", "-o", bam, sam)
    return bam


def expected(marker, profile, swapped):
    wanted = {}
    for (chrom, pos, first, second), recipe in zip(LOCI, PROFILES[profile], strict=True):
        n_ref, n_alt, n_other = COUNTS[recipe]
        if marker == "snp":
            # Recombinant first[0] + second[1] matches the original SNP REF.
            n_ref += n_other
            n_other = 0
            first, second = first[0], second[0]
        gt = GENOTYPES[recipe]
        if swapped:
            first, second, n_ref, n_alt = second, first, n_alt, n_ref
            gt = {"0/0": "1/1", "1/1": "0/0"}.get(gt, gt)
        wanted[chrom, pos] = (first, second, n_ref, n_alt, n_other, gt)
    return wanted


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class ReferenceOracles(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="newpat-reference-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.samples = {profile: sample_bam(self.root, profile) for profile in PROFILES}

    def execute(self, directory, marker, fasta, panels, bams):
        inputs = directory.with_name(directory.name + "_alignments")
        inputs.mkdir()
        aliases = []
        for number, source in enumerate(bams, 1):
            alias = inputs / f"sample_{number:04d}.bam"
            shutil.copyfile(source, alias)
            index = Path(str(source) + ".bai")
            if index.exists():
                shutil.copyfile(index, str(alias) + ".bai")
            aliases.append(alias)
        source = ({"bam": str(aliases[0]), "pileup": None, "mode": "bam"} if marker == "snp" else
                  {"samples": [{"sample_id": path.stem, "path": str(path)} for path in aliases],
                   "parallel": False})
        return execute_workflow(marker + "-call", directory, timeout=120, reference=str(fasta),
                               panel=str(panels / f"{marker}.tsv"), scientific_settings={"baq": False},
                               **source)

    def assert_calls(self, path, marker, known):
        rows = table(path)
        self.assertEqual(len(rows), len(known))
        coordinate = "pos" if marker == "snp" else "pos1"
        actual = {}
        for row in rows:
            key = row["chr"], int(row[coordinate])
            actual[key] = (row["REF"], row["ALT"], int(row["N_REF"]), int(row["N_ALT"]),
                           int(row["N_Other"]), row["GT"])
            wanted_depth = sum(known[key][2:5])
            if wanted_depth:
                self.assertEqual(row["total_count"], str(wanted_depth), key)
                self.assertEqual(int(row["reads_discarded_for_indels"]), 0, key)
            else:
                # Both representations are accepted by downstream count consumers.
                self.assertIn(row["total_count"], ("0", "NA"), key)
            if marker == "dnp":
                self.assertEqual(int(row["pos2"]), key[1] + 1, key)
        self.assertEqual(actual, known)

    def test_reference_representation_allele_orientation_and_bam_order(self):
        for label, swapped, compressed, order in (
                ("plain", False, False, ("A", "B", "C")),
                ("indexed", False, True, ("C", "A", "B")),
                ("swapped", True, True, ("B", "C", "A"))):
            folder = self.root / label
            folder.mkdir()
            fasta = reference_and_panel(folder, swapped)
            if compressed:
                compressed_reference = folder / "rewrapped.fa.gz"
                samtools("faidx", "-n", "23", "-o", compressed_reference, fasta, *LENGTHS)
                samtools("faidx", compressed_reference)
                self.assertGreater(Path(str(compressed_reference) + ".gzi").stat().st_size, 8)
                fasta = compressed_reference
                for bam in self.samples.values():
                    samtools("index", bam)
            with self.subTest(reference=label, marker="dnp", order=order):
                directory = folder / "dnp"
                process = self.execute(directory, "dnp", fasta, folder, [self.samples[x] for x in order])
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                summary = table(directory / "output/summary/output_AllGenotypes.txt")
                self.assertEqual(len(summary), len(LOCI))
                for number, profile in enumerate(order, 1):
                    alias = f"sample_{number:04d}"
                    known = expected("dnp", profile, swapped)
                    self.assert_calls(directory / f"output/individual_outputs/full_output_{alias}.txt",
                                      "dnp", known)
                    self.assertEqual({(r["chr"], int(r["pos1"])): r["GT_" + alias] for r in summary},
                                     {locus: row[-1] for locus, row in known.items()})
            for profile in order:
                with self.subTest(reference=label, marker="snp", profile=profile):
                    directory = folder / ("snp_" + profile)
                    process = self.execute(directory, "snp", fasta, folder, [self.samples[profile]])
                    self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                    self.assert_calls(directory / "output/SNPcall_output.txt", "snp",
                                      expected("snp", profile, swapped))

    def test_wrong_bases_in_a_matching_dictionary_and_missing_compression_index(self):
        source, alternate = self.root / "source", self.root / "alternate"
        source.mkdir()
        alternate.mkdir()
        original = reference_and_panel(source, False)
        wrong = reference_and_panel(alternate, True)
        self.assertEqual(Path(str(original) + ".fai").read_bytes(), Path(str(wrong) + ".fai").read_bytes())
        incomplete = source / "missing_index.fa.gz"
        samtools("faidx", "-o", incomplete, original, *LENGTHS)
        samtools("faidx", incomplete)
        Path(str(incomplete) + ".gzi").unlink()
        for reference, reason in ((wrong, "panel REF differs"), (incomplete, ".gzi")):
            for marker in ("snp", "dnp"):
                with self.subTest(error=reason, marker=marker):
                    directory = self.root / (marker + "_" + reference.stem)
                    result = self.execute(directory, marker, reference, source, [self.samples["A"]])
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(reason, result.stdout + result.stderr)
                    self.assertFalse((directory / "work/scientific-validation.json").exists())
                    result_table = ("SNPcall_output.txt" if marker == "snp"
                                    else "individual_outputs/full_output_sample_0001.txt")
                    self.assertFalse((directory / "output" / result_table).exists())
