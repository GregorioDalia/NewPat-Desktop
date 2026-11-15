import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from nipat.errors import NipatError
from nipat.update_handoff import (HANDOFF_EXIT_CODE, _start_windows_update, _verify_package,
                                 _windows_layout, begin_update, update_cache_directory,
                                 windows_installation_platform, windows_zip_root)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / 'app'
        self.project.mkdir()
        (self.project / '.runtime').mkdir()
        layout = dict(schema_version=1, installation_channel='desktop')
        for key, name in [('app_dir', 'app'), ('runtime_dir', 'runtime'), ('cache_dir', 'cache'),
                          ('data_dir', 'data'), ('runs_dir', 'runs')]:
            layout[key] = str(self.root / name)
        (self.project / '.runtime/install-layout.json').write_text(json.dumps(layout))
        self.cache = self.root / 'cache' / 'updates'
        self.cache.mkdir(parents=True)
        self.package = self.cache / 'NIPAT-Setup.exe'
        self.package.write_bytes(b'verified installer fixture')
        self.offer = SimpleNamespace(version='0.6.1', source_commit='b' * 40,
            asset=SimpleNamespace(platform='windows-x86_64', size=self.package.stat().st_size,
                                  sha256=hashlib.sha256(self.package.read_bytes()).hexdigest()))
        source = self.project / 'installer/windows/update-handoff.ps1'
        source.parent.mkdir(parents=True)
        source.write_text('# trusted bundled worker fixture')

    def tearDown(self):
        self.temporary.cleanup()

    def test_installed_layout_preserves_all_custom_paths(self):
        layout = _windows_layout(self.project)
        self.assertEqual(layout['cache_dir'], self.root / 'cache')
        with patch('nipat.update_handoff.sys.platform', 'win32'):
            self.assertEqual(update_cache_directory(self.project), self.cache)
        self.assertEqual(HANDOFF_EXIT_CODE, 85)

    def test_relative_linux_cache_rejected_before_directory_creation(self):
        with patch('nipat.update_handoff.sys.platform', 'linux'), \
                patch.dict(os.environ, {'XDG_CACHE_HOME': 'relative-cache'}), \
                patch('nipat.update_handoff.Path.mkdir') as mkdir:
            with self.assertRaisesRegex(NipatError, 'XDG_CACHE_HOME'):
                update_cache_directory(self.project)
            mkdir.assert_not_called()

    def test_foreign_or_overlapping_layout_rejected(self):
        path = self.project / '.runtime/install-layout.json'
        original = json.loads(path.read_text())
        for mutation in [{'installation_channel': 'preview-0.5'}, {'cache_dir': str(self.project / 'cache')}]:
            path.write_text(json.dumps(dict(original, **mutation)))
            with self.assertRaises(NipatError):
                _windows_layout(self.project)

    def test_modified_installer_never_reaches_platform_handoff(self):
        self.package.write_bytes(b'changed')
        with patch('nipat.update_handoff._start_windows_update') as start:
            with self.assertRaises(NipatError):
                begin_update(self.offer, self.package, self.project)
            start.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'requires Windows short-name aliases')
    def test_real_windows_short_name_alias_is_canonicalized_before_cache_check(self):
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        kernel.GetShortPathNameW.restype = wintypes.DWORD
        needed = kernel.GetShortPathNameW(str(self.package), None, 0)
        if not needed:
            self.skipTest('short names unavailable on this volume')
        buffer = ctypes.create_unicode_buffer(needed)
        length = kernel.GetShortPathNameW(str(self.package), buffer, needed)
        if not length or length >= needed:
            self.skipTest('short name could not be obtained')
        alias = Path(buffer.value)
        if str(alias).casefold() == str(self.package).casefold():
            self.skipTest('8.3 short-name generation is disabled on this volume')
        self.assertEqual(alias.resolve(strict=True), self.package)

        def started(argv, **kwargs):
            descriptor = Path(argv[-1])
            self.assertEqual(json.loads(descriptor.read_text())['package'], str(self.package))
            descriptor.with_name('ready.json').write_text(json.dumps(
                dict(schema_version=1, worker_pid=12345, parent_pid=os.getpid())))
            return MagicMock(pid=12345)

        with patch('nipat.update_handoff.subprocess.Popen', side_effect=started):
            self.assertTrue(begin_update(self.offer, alias, self.project))
            self.assertTrue(_start_windows_update(self.offer, alias, self.project))

    def test_package_symlink_rejected_before_canonicalization(self):
        link = self.cache / 'linked-installer.exe'
        try:
            link.symlink_to(self.package)
        except OSError:
            self.skipTest('symlink creation unavailable')
        with patch('nipat.update_handoff._start_windows_update') as start:
            with self.assertRaises(NipatError):
                begin_update(self.offer, link, self.project)
            start.assert_not_called()

    def test_windows_worker_is_external_and_receives_only_fixed_file_arguments(self):
        process = MagicMock(pid=12345)
        process.poll.return_value = None
        def started(argv, **kwargs):
            descriptor = Path(argv[-1])
            self.assertNotIn(self.project, descriptor.parents)
            record = json.loads(descriptor.read_text())
            self.assertEqual(record['version'], '0.6.1')
            self.assertEqual(record['source_commit'], 'b' * 40)
            self.assertEqual(record['project_dir'], str(self.project))
            self.assertEqual(kwargs['close_fds'], True)
            self.assertNotIn('shell', kwargs)
            descriptor.with_name('ready.json').write_text(json.dumps(
                dict(schema_version=1, worker_pid=12345, parent_pid=os.getpid())))
            return process
        with patch('nipat.update_handoff.sys.platform', 'win32'), \
                patch('nipat.update_handoff.subprocess.Popen', side_effect=started):
            self.assertTrue(begin_update(self.offer, self.package, self.project))
        self.assertEqual(len(list(self.cache.glob('handoff-*/cancel'))), 0)

    def install_bootstrap_marker(self):
        setup = self.project / '.runtime/setup/NIPAT-Setup.exe'
        setup.parent.mkdir()
        setup.write_bytes(b'unchanging bootstrap fixture')
        checksum = hashlib.sha256(setup.read_bytes()).hexdigest()
        marker = self.project / '.runtime/bootstrap-install.json'
        marker.write_text(json.dumps(dict(schema_version=1, installation_method='bootstrap',
                                          setup_sha256=checksum)))
        return marker, setup, checksum

    def test_bootstrap_channel_is_explicit_and_never_falls_back_when_broken(self):
        self.assertEqual(windows_installation_platform(self.project), 'windows-x86_64')
        marker, setup, _ = self.install_bootstrap_marker()
        self.assertEqual(windows_installation_platform(self.project), 'windows-bootstrap-x86_64')
        marker.write_text('{"schema_version":1,"installation_method":"bootstrap"}')
        with self.assertRaisesRegex(NipatError, 'setup stabile'):
            windows_installation_platform(self.project)
        marker.write_text('broken json')
        with self.assertRaises(NipatError):
            windows_installation_platform(self.project)

    def test_payload_handoff_pins_original_bootstrap_and_exact_release(self):
        _, _, setup_sha256 = self.install_bootstrap_marker()
        self.offer.asset.platform = 'windows-bootstrap-x86_64'
        self.package = self.package.rename(self.cache / 'NIPAT-0.6.1-Windows-payload.zip')

        def started(argv, **kwargs):
            descriptor = Path(argv[-1])
            self.assertNotIn(self.project, descriptor.parents)
            record = json.loads(descriptor.read_text())
            self.assertEqual(record['installation_method'], 'bootstrap')
            self.assertEqual(record['setup_sha256'], setup_sha256)
            self.assertEqual(record['package'], str(self.package))
            self.assertEqual(record['version'], self.offer.version)
            self.assertEqual(record['source_commit'], self.offer.source_commit)
            self.assertEqual(len(record), 12)
            descriptor.with_name('ready.json').write_text(json.dumps(
                dict(schema_version=1, worker_pid=12345, parent_pid=os.getpid())))
            return MagicMock(pid=12345)

        with patch('nipat.update_handoff.sys.platform', 'win32'), \
                patch('nipat.update_handoff.subprocess.Popen', side_effect=started):
            self.assertTrue(begin_update(self.offer, self.package, self.project))

    def test_classic_bootstrap_rejects_zip_channel_before_starting_worker(self):
        self.install_bootstrap_marker()
        self.offer.asset.platform = 'windows-zip-x86_64'
        with patch('nipat.update_handoff.sys.platform', 'win32'), \
                patch('nipat.update_handoff._start_windows_update') as start:
            with self.assertRaises(NipatError):
                begin_update(self.offer, self.package, self.project)
            start.assert_not_called()

    def test_owned_local_zip_root_survives_version_changes_and_custom_locations(self):
        for location in ('Extracted è & space/NIPAT', 'Other local folder/NIPAT'):
            root = self.root / location
            root.mkdir(parents=True)
            (root / 'installation.json').write_text(json.dumps(
                dict(schema_version=1, product='nipat-desktop', installation_method='zip')))
            for version in ('0.8.99', '0.8.100', '0.9.0'):
                project = root / 'versions' / (version + '-' + 'a' * 40)
                marker = project / '.runtime/zip-install.json'
                marker.parent.mkdir(parents=True)
                marker.write_text(json.dumps(dict(schema_version=1, installation_method='zip', root=str(root))))
                self.assertEqual(windows_zip_root(project), root)
                self.assertEqual(windows_installation_platform(project), 'windows-zip-x86_64')
            (root / 'installation.json').write_text('{"schema_version":1,"product":"foreign","installation_method":"zip"}')
            with self.assertRaises(NipatError):
                windows_zip_root(project)

    def test_zip_root_rejects_redirected_ownership_and_conflicting_channel(self):
        root = self.root / 'NIPAT'
        project = root / 'versions' / ('0.8.99-' + 'a' * 40)
        marker = project / '.runtime/zip-install.json'
        marker.parent.mkdir(parents=True)
        owner = dict(schema_version=1, product='nipat-desktop', installation_method='zip')
        (root / 'installation.json').write_text(json.dumps(owner))
        value = dict(schema_version=1, installation_method='zip', root=str(root))
        marker.write_text(json.dumps(value))
        (project / '.runtime/bootstrap-install.json').write_text('{}')
        with self.assertRaisesRegex(NipatError, 'ambigua'):
            windows_installation_platform(project)
        (project / '.runtime/bootstrap-install.json').unlink()
        for invalid in ('.', str(root.parent), str(root / 'versions')):
            marker.write_text(json.dumps(dict(value, root=invalid)))
            with self.assertRaises(NipatError):
                windows_zip_root(project)

    def test_timeout_cancels_worker_before_future_parent_exit(self):
        process = MagicMock(pid=12345)
        process.poll.return_value = None
        with patch('nipat.update_handoff.sys.platform', 'win32'), \
                patch('nipat.update_handoff.subprocess.Popen', return_value=process), \
                patch('nipat.update_handoff.time.monotonic', side_effect=[0, 20]):
            with self.assertRaises(NipatError):
                _start_windows_update(self.offer, self.package, self.project)
        self.assertEqual(len(list(self.cache.glob('handoff-*/cancel'))), 1)

    def test_keyboard_interrupt_also_cancels_pending_worker(self):
        process = MagicMock(pid=12345)
        process.poll.return_value = None
        with patch('nipat.update_handoff.sys.platform', 'win32'), \
                patch('nipat.update_handoff.subprocess.Popen', return_value=process), \
                patch('nipat.update_handoff.time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                _start_windows_update(self.offer, self.package, self.project)
        self.assertEqual(len(list(self.cache.glob('handoff-*/cancel'))), 1)

    def test_malformed_ready_cancels_worker(self):
        def started(argv, **kwargs):
            Path(argv[-1]).with_name('ready.json').write_text('{malformed')
            return MagicMock(pid=12345)
        with patch('nipat.update_handoff.sys.platform', 'win32'), \
                patch('nipat.update_handoff.subprocess.Popen', side_effect=started):
            with self.assertRaises(NipatError):
                _start_windows_update(self.offer, self.package, self.project)
        self.assertEqual(len(list(self.cache.glob('handoff-*/cancel'))), 1)

    def test_linux_dispatches_explicit_offer_without_shell(self):
        self.offer.asset.platform = 'linux-x86_64'
        with patch('nipat.update_handoff.sys.platform', 'linux'), \
                patch('nipat.update_handoff._verify_package') as duplicate_verification, \
                patch('nipat.linux_update.start_linux_update', return_value=True) as launch:
            self.assertTrue(begin_update(self.offer, self.package, self.project))
            self.assertEqual(launch.call_args.kwargs['parent_pid'], os.getpid())
            self.assertEqual(launch.call_args.kwargs['project_dir'], self.project)
        duplicate_verification.assert_not_called()
