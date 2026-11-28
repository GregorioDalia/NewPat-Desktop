"""Failure and lifecycle contracts around real pipes with a fake samtools."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from newpat_scientific import dnp_pileup
from newpat_scientific.settings import settings_context


FAKE_SAMTOOLS = r'''
import json, os, pathlib, signal, sys, time
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
args = sys.argv[1:]
stage = args[0]
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(json.dumps({'stage': stage, 'args': args, 'pid': os.getpid()}) + '\n')
if stage == 'view':
    if os.environ.get('VIEW_FAIL'):
        raise SystemExit(13)
    if '-H' in args:
        header = pathlib.Path(args[-1] + '.header')
        sys.stdout.write(header.read_text() if header.exists() else
            '@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chr2\tLN:1000\n'
            '@SQ\tSN:chr1\tLN:1000\n@SQ\tSN:chr10\tLN:1000\n@SQ\tSN:chr3\tLN:1000\n')
        raise SystemExit(0)
    if os.environ.get('VIEW_CONTINUOUS'):
        while True:
            os.write(1, b'x' * 65536)
    sys.stdout.buffer.write(pathlib.Path(args[-1]).read_bytes())
elif stage == 'mpileup':
    if os.environ.get('MPILEUP_FAIL'):
        raise SystemExit(17)
    if os.environ.get('MPILEUP_SLEEP'):
        time.sleep(60)
    contig = args[args.index('-r') + 1] if '-r' in args else None
    if os.environ.get('MPILEUP_EMPTY'):
        raise SystemExit(0)
    if contig == os.environ.get('MPILEUP_FAIL_CONTIG', ''):
        raise SystemExit(19)
    if contig == 'chr2' and os.environ.get('MPILEUP_RELEASE_FILE'):
        deadline = time.monotonic() + 10
        while not pathlib.Path(os.environ['MPILEUP_RELEASE_FILE']).exists():
            if time.monotonic() >= deadline:
                raise SystemExit('Timed out waiting for the test to observe chr1 completion')
            time.sleep(0.01)
    if contig:
        time.sleep(json.loads(os.environ.get('MPILEUP_DELAYS', '{}')).get(contig, 0.1))
    names = pathlib.Path(args[args.index('-b')+1]).read_text().splitlines() if '-b' in args else ['-']
    data = []
    for name in names:
        data.append(sys.stdin.buffer.read() if name == '-' else pathlib.Path(name).read_bytes())
    sys.stdout.buffer.write((contig.encode() + b':' + b'|'.join(data) + b'\n') if contig else
                            (b'pileup\n' + b'|'.join(data)))
else:
    raise SystemExit(99)
'''


@unittest.skipUnless(os.name == 'posix', 'The scientific helper runs in the Linux engine')
class DnpPileupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.scratch = self.root / 'scratch'
        self.scratch.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.samtools = self.bin / 'samtools'
        self.samtools.write_text('#!' + sys.executable + '\n' + FAKE_SAMTOOLS)
        self.samtools.chmod(0o755)
        self.log = self.root / 'commands.jsonl'
        self.bed = self.root / 'same.bed'
        self.bed.write_text('chr1\t0\t10\n')
        self.reference = self.root / 'ref.fa'
        self.reference.write_text('>chr1\n' + 'A' * 1000 + '\n')
        self.reference.with_suffix('.fa.fai').write_text(
            ''.join(f'{name}\t1000\t0\t1000\t1001\n'
                    for name in ('chr2', 'chr1', 'chr10', 'chr3', 'chr1:2', '.')))
        self.bamlist = self.root / 'bamlist.txt'
        self.output = self.scratch / 'pileup.txt'
        self.metadata = self.root / 'dnp-pileup.json'
        self.enterContext(patch.dict(os.environ, {'FAKE_LOG': str(self.log),
                           'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', '')}, clear=False))
        for key in ('VIEW_FAIL', 'VIEW_CONTINUOUS', 'MPILEUP_FAIL', 'MPILEUP_SLEEP',
                    'MPILEUP_FAIL_CONTIG', 'MPILEUP_DELAYS', 'MPILEUP_RELEASE_FILE'):
            os.environ.pop(key, None)

    def samples(self, indexed):
        paths = []
        for i, has_index in enumerate(indexed):
            directory = self.root / str(i)
            directory.mkdir()
            # Repeated basenames must remain distinct inputs in the list.
            bam = directory / 'sample.bam'
            bam.write_bytes(f'reads-{i}'.encode())
            if has_index:
                Path(str(bam) + '.bai').write_bytes(b'index')
            paths.append(bam)
        self.bamlist.write_text(''.join(str(path) + '\n' for path in paths))
        return paths

    def generate(self, budget=None):
        return dnp_pileup.generate_pileup(self.bamlist, self.bed, self.reference,
                                        self.output, self.scratch, self.metadata,
                                        samtools=str(self.samtools), budget=budget)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assert_no_intermediates(self):
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_single_index_streams_and_preserves_scientific_options(self):
        bams = self.samples([True])
        result = self.generate()
        self.assertEqual(result['strategy'], 'indexed-pipe')
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(self.output.read_bytes(), b'pileup\nreads-0')
        commands = {x['stage']: x['args'] for x in self.commands()}
        self.assertEqual(commands['view'], ['view', '--no-PG', '-u', '-M', '-L', str(self.bed), str(bams[0])])
        self.assertEqual(commands['mpileup'], ['mpileup', '-l', str(self.bed), '-f', str(self.reference),
                                             *dnp_pileup.MPILEUP_OPTIONS, '-d', '0', '-'])
        self.assertEqual([x['returncode'] for x in result['processes']], [0, 0, 0])
        self.assertIsNone(result['samples'][0]['selected_bytes'])
        self.assertEqual(result['staged_bytes'], 0)
        self.assertEqual(list(self.scratch.iterdir()), [self.output])
        self.assertEqual(json.loads(self.metadata.read_text()), result)

    def test_depth_probe_uses_all_inputs_and_falls_back_without_changing_scientific_depth(self):
        bams = self.samples([True, True])
        samples = [{"index_candidates": [str(bam) + ".bai"]} for bam in bams]
        targets = {"chr1": 100, "chr2": 100}
        windows = [("chr1", 21, 24), ("chr2", 31, 34)]
        at_limit = [["chr1", "20", "24", "16000", "4000"], ["chr2", "30", "34", "0", "0"]]
        oversized = [["chr1", "20", "24", "16004", "4001"], at_limit[1]]
        for other, workers in ((at_limit, 2), (oversized, 1), ([], 1), (at_limit[::-1], 1)):
            with self.subTest(other=other):
                parallel = {"budget": {"verify_depth_limit": 8000}, "workers": 2}
                with patch.object(dnp_pileup, "_probe_rows", side_effect=[at_limit, other]) as probe:
                    dnp_pileup._verify_depth_budget(bams, samples, self.bed, windows, targets,
                                                    "samtools", dnp_pileup.Cancellation(), parallel)
                self.assertEqual(probe.call_count, 2)
                self.assertEqual(parallel["workers"], workers)
                self.assertEqual(samples[0]["depth_evidence"]["upper_bound"], 8000)
        os.utime(samples[0]["index_candidates"][0], (1, 1))
        with patch.object(dnp_pileup, "_probe_rows") as probe:
            parallel = {"budget": {"verify_depth_limit": 8000}, "workers": 2}
            dnp_pileup._verify_depth_budget(bams, samples, self.bed, windows, targets,
                                            "samtools", dnp_pileup.Cancellation(), parallel)
            probe.assert_not_called()
            self.assertEqual(parallel["workers"], 1)

    def test_large_panel_uses_one_indexed_count_and_honours_the_probe_deadline(self):
        bam, = self.samples([True])
        indexes = [str(bam) + ".bai"]
        windows = [("chr1", 21, 24)] * 2049
        cancel = dnp_pileup.Cancellation()
        with patch.object(dnp_pileup, "_probe_rows", return_value=[["8500"]]) as probe:
            self.assertEqual(dnp_pileup._sample_depth_evidence(bam, indexes, self.bed, windows,
                             8000, "samtools", time.monotonic() + 5, cancel), ("indexed-panel-count", 8500))
            self.assertEqual(probe.call_args.args[0][1:5], ["view", "-c", "-M", "-L"])
        with patch.object(dnp_pileup.subprocess, "run") as run:
            self.assertEqual(dnp_pileup._probe_rows(["samtools"], time.monotonic() - 1, cancel), [])
            run.assert_not_called()

    def test_custom_acquisition_settings_apply_with_and_without_budget(self):
        self.samples([True, True])
        settings = {"min_base_quality": 21, "min_mapping_quality": 17, "max_depth": 500,
                    "baq": False, "count_overlaps": True, "include_orphans": True}
        for budget in (None, {"schema_version": 1, "interface": "newpat-parallel-v1",
                             "mode": "serial", "workers": 1}):
            with self.subTest(budget=budget), settings_context("dnp-call", settings, self.root / "settings"):
                result = self.generate(budget)
                command = [entry["args"] for entry in self.commands() if entry["stage"] == "mpileup"][-1]
                for flag, expected in (("-Q", "21"), ("-q", "17"), ("-d", "500")):
                    self.assertEqual(command[command.index(flag) + 1], expected)
                for flag in ("-B", "-x", "-A"):
                    self.assertIn(flag, command)
                    self.assertIn(flag, result["mpileup_options"])
                self.assertEqual(result["scientific_settings"]["min_base_quality"], 21)
            self.output.unlink()
            self.metadata.unlink()

    def test_multiple_inputs_keep_order_duplicate_names_and_staging_cost(self):
        self.samples([True, False, True])
        result = self.generate()
        self.assertEqual(result['strategy'], 'indexed-disk')
        self.assertEqual(self.output.read_bytes(), b'pileup\nreads-0|reads-1|reads-2')
        self.assertEqual([x['staged_bytes'] for x in result['samples']], [7, 0, 7])
        self.assertEqual(result['staged_bytes'], 14)
        self.assertEqual([x['strategy'] for x in result['samples']],
                         ['indexed-disk', 'sequential-no-index', 'indexed-disk'])
        self.assertEqual([x['stage'] for x in self.commands()], ['view'] * 5 + ['mpileup'])
        self.assertEqual(list(self.scratch.iterdir()), [self.output])

    def test_missing_index_checks_header_then_scans_originals(self):
        self.samples([False])
        result = self.generate()
        self.assertEqual(result['strategy'], 'sequential')
        self.assertEqual([x['stage'] for x in self.commands()], ['view', 'mpileup'])
        self.assertEqual(self.output.read_bytes(), b'pileup\nreads-0')

    def test_failed_indexed_producer_cannot_report_success_or_retain_output(self):
        self.samples([True])
        os.environ['VIEW_FAIL'] = '1'
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate()
        self.assertEqual(json.loads(self.metadata.read_text())['status'], 'failed')
        self.assert_no_intermediates()

    def test_early_consumer_failure_reaps_blocked_producer(self):
        self.samples([True])
        os.environ.update(VIEW_CONTINUOUS='1', MPILEUP_FAIL='1')
        started = time.monotonic()
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate()
        self.assertLess(time.monotonic() - started, 4)
        self.assert_no_intermediates()
        for command in self.commands():
            with self.assertRaises(ProcessLookupError):
                os.kill(command['pid'], 0)

    def test_group_cancellation_reaps_children_and_removes_owned_partials(self):
        self.samples([True])
        os.environ.update(VIEW_CONTINUOUS='1', MPILEUP_SLEEP='1')
        arguments = [sys.executable, str(Path(dnp_pileup.__file__)), '--bamlist', str(self.bamlist),
                     '--bed', str(self.bed), '--reference', str(self.reference), '--output', str(self.output),
                     '--scratch-dir', str(self.scratch), '--metadata', str(self.metadata)]
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.log.exists() and len(self.commands()) == 3:
                    break
                time.sleep(0.02)
            else:
                self.fail('Both pipe children did not start')
            os.killpg(process.pid, signal.SIGTERM)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143, stderr.decode())
            self.assertEqual(json.loads(self.metadata.read_text())['status'], 'cancelled')
            self.assert_no_intermediates()
            for command in self.commands():
                with self.assertRaises(ProcessLookupError):
                    os.kill(command['pid'], 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_existing_output_and_outside_scratch_are_never_overwritten(self):
        self.samples([False])
        self.output.write_bytes(b'preserve')
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate()
        self.assertEqual(self.output.read_bytes(), b'preserve')
        self.output = self.root / 'outside.txt'
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.metadata.exists())

    def test_budgeted_chromosomes_preserve_order_and_bound_actual_processes(self):
        self.samples([True, True])
        self.bed.write_text('chr3\t0\t10\nchr10\t0\t10\nchr1\t0\t10\nchr2\t0\t10\n')
        release = self.root / 'release-chr2'
        os.environ['MPILEUP_RELEASE_FILE'] = str(release)
        finish_record = dnp_pileup._finish_record

        def observe_completion(record, process, started, cancellation):
            finish_record(record, process, started, cancellation)
            if record.get('contig') == 'chr1' and record['returncode'] == 0:
                release.touch()

        # Completion timestamps record when the parent polls a child. Hold chr2
        # until chr1 has been observed; sleeps cannot guarantee this under load.
        with patch.object(dnp_pileup, '_finish_record', side_effect=observe_completion):
            result = self.generate({'mode': 'auto', 'workers': 8, 'max_workers': 2})
        self.assertEqual(result['strategy'], 'indexed-chromosomes')
        self.assertEqual(result['parallel']['workers'], 2)
        self.assertEqual(result['parallel']['observed_max_processes'], 2)
        tasks = [item for item in result['processes'] if item['stage'] == 'mpileup-chromosome']
        self.assertEqual([item['contig'] for item in tasks], ['chr2', 'chr1', 'chr10', 'chr3'])
        self.assertEqual([item['task_index'] for item in tasks], [1, 2, 3, 4])
        self.assertEqual(self.output.read_bytes(), b''.join(
            name + b':reads-0|reads-1\n' for name in (b'chr2', b'chr1', b'chr10', b'chr3')))
        self.assertLess(tasks[1]['finished_at_unix'], tasks[0]['finished_at_unix'])
        events = [(item['started_at_unix'], 1) for item in tasks]
        events += [(item['finished_at_unix'], -1) for item in tasks]
        active, maximum = 0, 0
        for _, change in sorted(events):
            active += change
            maximum = max(maximum, active)
        self.assertEqual(maximum, 2)
        self.assertTrue(all(item['outcome'] == 'succeeded' and item['returncode'] == 0 for item in tasks))
        self.assertEqual(list(self.scratch.iterdir()), [self.output])
        self.assertEqual(json.loads(self.metadata.read_text()), result)
        for item in self.commands():
            if item['stage'] == 'mpileup':
                for option in dnp_pileup.MPILEUP_OPTIONS:
                    self.assertIn(option, item['args'])
                self.assertNotIn('-B', item['args'])
                self.assertNotIn('-@', item['args'])

    def test_serial_budget_uses_one_process_and_preserves_dictionary_order(self):
        self.samples([True])
        self.bed.write_text('chr1\t0\t10\nchr2\t0\t10\n')
        result = self.generate({'mode': 'serial', 'workers': 4})
        self.assertEqual(result['parallel']['workers'], 1)
        self.assertEqual(result['parallel']['observed_max_processes'], 1)
        tasks = [item for item in result['processes'] if item['stage'] == 'mpileup-chromosome']
        self.assertLessEqual(tasks[0]['finished_at_unix'], tasks[1]['started_at_unix'])
        self.assertEqual(self.output.read_bytes(), b'chr2:reads-0\nchr1:reads-0\n')

    def test_optimized_io_streams_identical_ordered_or_empty_pileup_only_with_one_worker(self):
        self.samples([True, True])
        self.bed.write_text('chr1\t0\t10\nchr2\t0\t10\n')
        for empty in ('', '1'):
            outputs = []
            for optimized_io, workers in (('', 1), ('1', 1), ('1', 2)):
                with self.subTest(empty=empty, optimized_io=optimized_io, workers=workers), patch.dict(
                        os.environ, MPILEUP_EMPTY=empty, NEWPAT_DNP_OPTIMIZED_IO=optimized_io):
                    result = self.generate({'mode': 'auto', 'workers': workers})
                    direct = result['parallel'].get('output_strategy') == 'direct-dictionary-order'
                    self.assertEqual(direct, bool(optimized_io) and workers == 1)
                    outputs.append(self.output.read_bytes())
                    self.output.unlink()
                    self.metadata.unlink()
            expected = b'' if empty else b'chr2:reads-0|reads-1\nchr1:reads-0|reads-1\n'
            self.assertEqual(outputs, [expected] * 3)

    def test_optimized_io_bounds_only_large_contigs_with_clustered_targets(self):
        bam, = self.samples([True])
        sizes = {"cluster": 2_000_000, "spread": 2_000_000, "tiny": 1000}
        self.reference.with_suffix(".fa.fai").write_text(
            "".join(f"{name}\t{size}\t0\t1000\t1001\n" for name, size in sizes.items()))
        Path(str(bam) + ".header").write_text("@HD\tSO:coordinate\n" + "".join(
            f"@SQ\tSN:{name}\tLN:{size}\n" for name, size in sizes.items()))
        self.bed.write_text("tiny\t5\t10\nspread\t100\t110\ncluster\t1000040\t1000050\n"
                            "spread\t1800000\t1800004\ncluster\t50\t54\n")
        for flag, expected in (("", "cluster"), ("1", "{cluster}:51-1000050")):
            with self.subTest(flag=flag), patch.dict(os.environ, NEWPAT_DNP_OPTIMIZED_IO=flag):
                result = self.generate({"mode": "auto", "workers": 1})
                args = [item["args"] for item in self.commands() if item["stage"] == "mpileup"]
                self.assertEqual([cmd[cmd.index("-r") + 1] for cmd in args], [expected, "spread", "tiny"])
                tasks = [item for item in result["processes"] if item["stage"] == "mpileup-chromosome"]
                self.assertEqual([item["contig"] for item in tasks], list(sizes))
                self.assertEqual([item["region"] for item in tasks if "region" in item],
                                 [expected] if flag else [])
                self.assertEqual(result["staged_bytes"], 0)
                self.output.unlink()
                self.metadata.unlink()
                self.log.unlink()

    def test_streamed_failure_on_second_contig_discards_first_contig(self):
        self.samples([True])
        self.bed.write_text('chr2\t0\t10\nchr1\t0\t10\n')
        with patch.dict(os.environ, MPILEUP_FAIL_CONTIG='chr1', NEWPAT_DNP_OPTIMIZED_IO='1'):
            with self.assertRaises(dnp_pileup.PileupError):
                self.generate({'mode': 'auto', 'workers': 1})
        result = json.loads(self.metadata.read_text())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual([row['outcome'] for row in result['processes'] if 'contig' in row],
                         ['succeeded', 'failed'])
        self.assert_no_intermediates()

    def test_mixed_indices_preserve_index_validation_with_sequential_staging(self):
        self.samples([True, False])
        result = self.generate({'mode': 'auto', 'workers': 4})
        self.assertEqual(result['strategy'], 'sequential-budgeted')
        self.assertEqual(result['parallel']['reason'], 'missing-index')
        self.assertEqual(result['parallel']['workers'], 1)
        self.assertEqual(result['parallel']['observed_max_processes'], 1)
        self.assertEqual([item['stage'] for item in self.commands()], ['view'] * 3 + ['mpileup'])
        self.assertEqual(result['staged_bytes'], 7)
        self.assertEqual(self.output.read_bytes(), b'pileup\nreads-0|reads-1')

    def test_reordered_dictionaries_fail_before_joint_pileup_with_or_without_index(self):
        bams = self.samples([True, False])
        Path(str(bams[1]) + '.header').write_text(
            '@HD\tSO:coordinate\n@SQ\tSN:chr1\tLN:1000\n@SQ\tSN:chr2\tLN:1000\n'
            '@SQ\tSN:chr10\tLN:1000\n@SQ\tSN:chr3\tLN:1000\n')
        for label, index, budget in (
            ('unbudgeted', False, None),
            ('mixed indices', False, {'mode': 'serial', 'workers': 1}),
            ('indexed', True, {'mode': 'auto', 'workers': 4}),
        ):
            with self.subTest(label=label):
                if index:
                    Path(str(bams[1]) + '.bai').write_bytes(b'index')
                with self.assertRaisesRegex(dnp_pileup.PileupError, 'Dizionari BAM incompatibili'):
                    self.generate(budget)
                self.assertEqual(json.loads(self.metadata.read_text())['status'], 'failed')
                self.assertEqual([item['args'][0:3] for item in self.commands()],
                                 [['view', '--no-PG', '-H']] * 2)
                self.assert_no_intermediates()
                self.metadata.unlink()
                self.log.unlink()

    def test_region_ambiguous_contig_uses_original_stream(self):
        bams = self.samples([True])
        Path(str(bams[0]) + '.header').write_text('@HD\tSO:coordinate\n@SQ\tSN:chr1:2\tLN:1000\n')
        self.bed.write_text('chr1:2\t0\t10\n')
        result = self.generate({'mode': 'auto', 'workers': 4})
        self.assertEqual(result['parallel']['reason'], 'ambiguous-contig')
        self.assertEqual(self.output.read_bytes(), b'pileup\nreads-0')

    def test_dot_contig_is_not_interpreted_as_samtools_special_region(self):
        bams = self.samples([True])
        Path(str(bams[0]) + '.header').write_text('@HD\tSO:coordinate\n@SQ\tSN:.\tLN:1000\n')
        self.bed.write_text('.\t0\t10\n')
        result = self.generate({'mode': 'auto', 'workers': 4})
        self.assertEqual(result['parallel']['reason'], 'ambiguous-contig')
        self.assertEqual(self.output.read_bytes(), b'pileup\nreads-0')
        self.assertTrue(all('-r' not in item['args'] for item in self.commands()))

    def test_budget_validation_rejects_invalid_values_before_claiming_outputs(self):
        for budget in ({'mode': 'invalid', 'workers': 1}, {'mode': 'auto', 'workers': True},
                       {'mode': 'auto', 'workers': 0}, {'mode': 'auto', 'workers': 1.5},
                       {'mode': 'auto', 'workers': 2, 'max_workers': -1},
                       {'mode': 'auto', 'workers': 2, 'cpu_limit': float('nan')}):
            with self.subTest(budget=budget), self.assertRaises(dnp_pileup.PileupError):
                self.generate(budget)
        self.assertFalse(self.metadata.exists())
        limited = dnp_pileup._budget({'mode': 'auto', 'workers': 10, 'cpu_limit': 2.9,
                                     'max_workers': 4, 'memory_worker_limit': 3})
        self.assertEqual(limited['workers'], 2)

    def test_header_failure_is_not_silently_replaced_by_sequential_execution(self):
        self.samples([True])
        os.environ['VIEW_FAIL'] = '1'
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate({'mode': 'auto', 'workers': 2})
        self.assertEqual([item['stage'] for item in self.commands()], ['view'])
        self.assertEqual(json.loads(self.metadata.read_text())['status'], 'failed')
        self.assert_no_intermediates()

    def test_present_index_failure_remains_fatal_when_another_index_is_missing(self):
        self.samples([True, False])
        os.environ['VIEW_FAIL'] = '1'
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate({'mode': 'auto', 'workers': 4})
        result = json.loads(self.metadata.read_text())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['processes'][0]['stage'], 'header')
        self.assertEqual([item['stage'] for item in self.commands()], ['view'])
        self.assert_no_intermediates()

    def test_parallel_task_failure_reaps_siblings_and_never_commits_output(self):
        self.samples([True])
        self.bed.write_text('chr1\t0\t10\nchr2\t0\t10\n')
        os.environ.update(MPILEUP_FAIL_CONTIG='chr2', MPILEUP_DELAYS=json.dumps({'chr1': 60}))
        started = time.monotonic()
        with self.assertRaises(dnp_pileup.PileupError):
            self.generate({'mode': 'auto', 'workers': 2})
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(json.loads(self.metadata.read_text())['status'], 'failed')
        self.assert_no_intermediates()
        for item in self.commands():
            with self.assertRaises(ProcessLookupError):
                os.kill(item['pid'], 0)

    def test_streamed_cancellation_discards_output_and_reaps_child(self):
        with patch.dict(os.environ, NEWPAT_DNP_OPTIMIZED_IO='1'):
            self.check_chromosome_cancellation(1)

    def test_parallel_cancellation_reaps_all_children_and_records_partial_evidence(self):
        self.check_chromosome_cancellation(2)

    def check_chromosome_cancellation(self, workers):
        self.samples([True])
        self.bed.write_text('chr1\t0\t10\nchr2\t0\t10\n')
        os.environ['MPILEUP_SLEEP'] = '1'
        budget = self.root / 'budget.json'
        budget.write_text(json.dumps({'mode': 'auto', 'workers': workers}))
        arguments = [sys.executable, str(Path(dnp_pileup.__file__)), '--bamlist', str(self.bamlist),
                     '--bed', str(self.bed), '--reference', str(self.reference), '--output', str(self.output),
                     '--scratch-dir', str(self.scratch), '--metadata', str(self.metadata), '--budget', str(budget)]
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.log.exists() and sum(item['stage'] == 'mpileup' for item in self.commands()) == workers:
                    break
                time.sleep(0.02)
            else:
                self.fail('Parallel children did not start')
            process.send_signal(signal.SIGTERM)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143, stderr.decode())
            result = json.loads(self.metadata.read_text())
            self.assertEqual(result['status'], 'cancelled')
            self.assertEqual(result['parallel']['observed_max_processes'], workers)
            tasks = [item for item in result['processes'] if item['stage'] == 'mpileup-chromosome']
            self.assertTrue(all(item['outcome'] == 'cancelled' for item in tasks))
            self.assert_no_intermediates()
            for item in self.commands():
                with self.assertRaises(ProcessLookupError):
                    os.kill(item['pid'], 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == '__main__':
    unittest.main()
