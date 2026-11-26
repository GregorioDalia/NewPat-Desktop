"""Scientific parity and resource fallbacks for whole-chromosome SNP mpileup."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from nipat_scientific import snp


class SnpAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.bam = self.root / "sample.bam"
        self.bam.touch()
        self.index = Path(str(self.bam) + ".bai")
        self.index.touch()
        self.contigs = ("chr10", "chr2", "chr1")
        self.output = self.root / "pileup.txt"
        self.command = ["samtools", "mpileup", "-d", "0", "-o", str(self.output), str(self.bam)]
        self.metadata = self.root / "snp-acquisition.json"
        self.enterContext(patch.dict(os.environ, {"NIPAT_EXECUTION_MODE": "auto", "NIPAT_MAX_WORKERS": "3",
                                                "NIPAT_PARALLEL_CHILD": "0"}))
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.enterContext(patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}))
        self.budget = dict(mode="auto", workers=2, max_workers=2, cpu_limit=2, memory_worker_limit=2,
                           memory_budget_mib=4096, coordinator_rss_mib=64)
        self.executable("Rscript", f"print({json.dumps(self.budget)!r})")

    def executable(self, name, code):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + code + "\n")
        path.chmod(0o755)

    def run_with_fixtures(self, command):
        # CreateProcess on Windows does not resolve extensionless shebang scripts.
        # Launch each fixture explicitly in the active interpreter, retaining
        # real child PIDs, exit codes, stdout handles and cleanup on every OS.
        spawn = subprocess.Popen

        def spawn_fixture(argv, **options):
            if argv[0] in {"samtools", "Rscript"}:
                fixture = self.bin / argv[0]
                if fixture.is_file():
                    argv = [sys.executable, str(fixture), *argv[1:]]
            return spawn(argv, **options)

        self.assertEqual(command[:2], [sys.executable, str(Path(snp.__file__).resolve())])
        with patch.object(subprocess, "Popen", new=spawn_fixture):
            snp._run_acquisition(Path(command[2]), command[3:])

    def planned(self, order="coordinate"):
        lengths = {c: 200 for c in reversed(self.contigs)}
        prep = snp.SnpPreparation(self.command, [], self.output, self.bam, lengths, lengths)
        def header(argv):
            Path(argv[-2]).write_text(f"@HD\tVN:1.6\tSO:{order}\n" +
                                      "".join(f"@SQ\tSN:{c}\tLN:200\n" for c in self.contigs))
            return 0
        code, command = prep.plan_acquisition(header, self.root)
        self.assertEqual(code, 0)
        return command

    def test_dictionary_order_and_fallbacks(self):
        self.assertEqual(self.planned()[0], sys.executable)
        self.assertEqual(json.loads(self.metadata.read_text())["contigs"], list(self.contigs))
        with patch.dict(os.environ, {"NIPAT_PARALLEL_CHILD": "1"}):
            self.assertEqual(self.planned(), self.command)
        with patch.dict(os.environ, {"NIPAT_EXECUTION_MODE": "serial"}):
            self.assertEqual(self.planned(), self.command)
        self.assertEqual(self.planned("unsorted"), self.command)
        self.assertIsNone(json.loads(self.metadata.read_text())["parallel"]["observed_max_processes"])
        self.index.unlink()
        self.assertEqual(self.planned(), self.command)
        self.index.touch()
        os.utime(self.index, ns=(1, 1))
        self.assertEqual(self.planned(), self.command)
        self.index.touch()
        self.contigs = ("chr1", "chr1:5-8")
        self.assertEqual(self.planned(), self.command)

    def test_budget_and_failed_index_retry_full_scan_atomically(self):
        self.executable("samtools", "import sys\nif '-r' in sys.argv:\n"
                        "    print('partial')\n    sys.exit(9)\nsys.stdout.buffer.write(b'complete\\n')")
        self.run_with_fixtures(self.planned())
        self.assertEqual(self.output.read_bytes(), b"complete\n")
        diag = json.loads(self.metadata.read_text())
        self.assertEqual(diag["strategy"], "sequential-scan")
        self.assertIn("exit code 9", diag["parallel"]["reason"])
        self.assertEqual(diag["status"], "completed")
        self.output.unlink()
        self.budget["memory_budget_mib"] = 400
        self.executable("Rscript", f"print({json.dumps(self.budget)!r})")
        self.run_with_fixtures(self.planned())
        diag = json.loads(self.metadata.read_text())
        self.assertEqual(diag["parallel"]["workers"], 1)
        self.assertEqual(diag["parallel"]["observed_max_processes"], 1)
        self.assertEqual([r["stage"] for r in diag["processes"]], ["mpileup-sequential"])

    def test_pool_rss_fallback_and_failure_leave_no_partial_pileup(self):
        self.executable("samtools", "import sys\nprint('serial')\nsys.exit(3)")
        command = self.planned()
        with patch.object(snp, "_check_pool_rss", side_effect=snp._PoolMemoryLimit("RSS test")):
            with self.assertRaises(snp.pileup_pool.PileupError):
                self.run_with_fixtures(command)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".snp-acquisition-*")))
        self.assertEqual(json.loads(self.metadata.read_text())["parallel"]["reason"], "RSS test")

    @unittest.skipUnless(os.name == "posix", "Linux engine cancellation")
    def test_signal_cleans_workers_and_staged_output(self):
        self.executable("samtools", "import time\ntime.sleep(30)")
        process = subprocess.Popen(self.planned(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not (diag := json.loads(self.metadata.read_text()))["processes"]:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(5), 128 + signal.SIGTERM)
            self.assertEqual(json.loads(self.metadata.read_text())["status"], "cancelled")
            for record in diag["processes"]:
                if record.get("pid"):
                    with self.assertRaises(ProcessLookupError):
                        os.kill(record["pid"], 0)
            self.assertFalse(self.output.exists())
            self.assertFalse(list(self.root.glob(".snp-acquisition-*")))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    @unittest.skipUnless(shutil.which("samtools"), "real samtools required")
    def test_real_mpileup_is_byte_identical_in_header_order(self):
        # Non-lexicographic BAM, reversed panel, overlapping target windows,
        # an uncovered chromosome, a discordant overlapping pair and depth cap.
        def samtools(*args):
            return subprocess.run(["samtools", *map(str, args)], check=True, capture_output=True)

        fa = self.root / "ref.fa"
        fa.write_text("".join(f">{c}\n{'A' * 200}\n" for c in self.contigs))
        samtools("faidx", fa)
        lines = ["@HD\tVN:1.6\tSO:coordinate", *[f"@SQ\tSN:{c}\tLN:200" for c in self.contigs]]
        for c in self.contigs[:2]:
            for i in range(12):
                lines.append(f"read{i}\t0\t{c}\t1\t60\t40M\t*\t0\t0\t{'A'*19}C{'A'*20}\t{'I'*40}")
            lines.append(f"pair\t99\t{c}\t10\t60\t20M\t=\t15\t25\t{'A'*20}\t{'I'*20}")
            lines.append(f"pair\t147\t{c}\t15\t60\t20M\t=\t10\t-25\t{'A'*5}G{'A'*14}\t{'I'*20}")
        sam = self.root / "sample.sam"
        sam.write_text("\n".join(lines) + "\n")
        samtools("view", "-b", "-o", self.bam, sam)
        samtools("index", self.bam)
        panel = self.root / "SNP.tsv"
        panel.write_text("chr\tpos\tref\talt\n" + "".join(
            f"{c}\t{pos}\tA\tC\n" for c in reversed(self.contigs) for pos in (20, 21, 110)))
        for i, settings in enumerate(({}, {"max_depth": 3, "baq": False, "min_base_quality": 0},
                                      {"count_overlaps": True, "include_orphans": True})):
            with self.subTest(settings=settings):
                work = self.root / f"work{i}"
                prep = snp.prepare_snp(dict(schema_version=1, workflow="snp-call", mode="bam",
                    bam=str(self.bam), reference=str(fa), pileup=None, panel=str(panel),
                    work_dir=str(work), out_dir=str(self.root / f"out{i}"), scientific_settings=settings))
                subprocess.run(prep.preparation_command, check=True, capture_output=True)
                expected = prep.generated_pileup.read_bytes()
                self.assertTrue(expected)
                prep.generated_pileup.unlink()
                code, command = prep.plan_acquisition(lambda a: subprocess.run(a, capture_output=True).returncode, work)
                self.assertEqual(code, 0)
                if os.name == "nt":
                    self.run_with_fixtures(command)
                else:
                    subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(prep.generated_pileup.read_bytes(), expected)
                diag = json.loads((work / "snp-acquisition.json").read_text())
                self.assertEqual(diag["strategy"], "indexed-chromosomes")
                self.assertEqual(diag["parallel"]["workers"], 2)
                self.assertEqual([r["contig"] for r in diag["processes"]], list(self.contigs))
