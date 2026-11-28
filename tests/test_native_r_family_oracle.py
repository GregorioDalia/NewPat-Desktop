"""Keep every shared parent attached to its expected numerical result in batch CPI."""

import math
import os
from pathlib import Path
import tempfile
import unittest

from native_engine_helpers import execute_workflow
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
from test_native_r_edge_cases import table


# There is one informative locus. REF and ALT population frequencies are .8 and .2.
# Each row fixes the observable number of fetal reads, the per-locus index, and a
# mismatch indicator. Maternal 1 carries predominantly REF; maternal 10 carries ALT.
# A matching homozygous father transmits with weight 1, a heterozygote with .5,
# and an incompatible father with the explicitly supplied mismatch weight .02.
EXPECTED = {
    ("1", "1"): (3, 1 / .2, 0),
    ("1", "10"): (3, .5 / .2, 0),
    ("10", "10"): (4, .5 / .8, 0),
    ("10", "2"): (4, 1 / .8, 0),
    ("1", "2"): (3, .02 / .2, 1),
    ("10", "1"): (4, .02 / .8, 1),
}


def inputs(directory, marker):
    directory.mkdir()
    coordinate = "chr\tpos" if marker == "SNP" else "chr\tpos1\tpos2"
    locus = "chrA\t42" if marker == "SNP" else "chrA\t42\t43"
    alleles = "A\tC" if marker == "SNP" else "AA\tCC"
    header = coordinate + "\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
    samples = []
    for i, (name, ref) in enumerate((
        ("Mother1", 97), ("Father2", 100), ("Father1", 0),
        ("Mother10", 4), ("Father10", 50),
    )):
        path = directory / f"input {i}.tsv"
        path.write_text(header + f"{locus}\t{alleles}\t{ref}\t{100 - ref}\t0\t100\n",
                        encoding="utf-8")
        samples.append({"path": str(path), "name": name + ".txt"})
    population = directory / "frequencies.tsv"
    population.write_text(f"{coordinate}\tRef_f.pop\tAlt_f.pop\n{locus}\t0.8\t0.2\n",
                          encoding="utf-8")
    return samples, population


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class NativeFamilyOracle(unittest.TestCase):
    def test_shared_parent_pair_identities_survive_reordering_and_worker_settings(self):
        for marker in ("SNP", "DNP"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                samples, population = inputs(root / "study inputs", marker)
                originals = {p: p.read_bytes() for p in population.parent.iterdir()}
                for mode in ("serial", "auto"):
                    with self.subTest(marker=marker, mode=mode):
                        pairs = list(EXPECTED) if mode == "serial" else list(reversed(EXPECTED))
                        run = root / mode
                        process = execute_workflow(
                            "cpi", run, execution_mode=mode, env=dict(os.environ, NEWPAT_MAX_WORKERS="3"),
                            marker_type=marker, samples=samples if mode == "serial" else samples[::-1],
                            pairs=",".join(f"{m}:{f}" for m, f in pairs),
                            mother_prefix="Mother", father_prefix="Father", popfreq=str(population),
                            cutoff_mode="all", cutoffs=[], scientific_settings={"err_const_" + marker.lower(): .02},
                        )
                        self.assertEqual(process.returncode, 0, process.stderr)
                        output = run / "output"
                        summaries = table(output / "Summary_FetalFraction_CPI.csv", ",")
                        ids = [f"Mother{m}-Father{f}_{marker}s" for m, f in pairs]
                        self.assertEqual([row["Pair"] for row in summaries], ids)
                        self.assertEqual({p.name for p in (output / "curves").iterdir()},
                                         {f"{pair_id}_panel_1.tsv" for pair_id in ids})
                        for pair, row in zip(pairs, summaries, strict=True):
                            with self.subTest(mother=pair[0], father=pair[1]):
                                support, index, mismatch = EXPECTED[pair]
                                self.assertEqual((row["N_sites_mother"], row["N_sites_father"]), ("1", "1"))
                                self.assertAlmostEqual(float(row["Median_fetal_fraction_raw"]), 2 * support / 100)
                                self.assertAlmostEqual(float(row["CPI_medianFF"]), round(math.log10(index), 3), places=3)
                                curve = table(output / "curves" / (row["Pair"] + "_panel_1.tsv"))
                                self.assertEqual([int(point["Iteration"]) for point in curve], list(range(2, support + 1)))
                                for point in curve:
                                    self.assertAlmostEqual(float(point["CPI"]), index, places=10)
                                    self.assertAlmostEqual(float(point["log_CPI"]), math.log10(index), places=10)
                                    self.assertEqual((int(point["Mismatch"]), int(point["NotMismatch"])),
                                                     (mismatch, 1 - mismatch))
                        self.assertEqual(originals, {p: p.read_bytes() for p in population.parent.iterdir()})
