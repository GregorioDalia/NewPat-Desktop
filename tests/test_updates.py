import hashlib
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request
from unittest.mock import Mock, patch

from newpat.repository import LEGACY_REPOSITORY, RENAMED_REPOSITORY, REPOSITORY_ID
from newpat.updates import (
    API, WEB, REPOSITORY_INFO_URL, UpdateAsset, UpdateClient, UpdateError, UpdateOffer,
    _SafeRedirectHandler, detect_platform, version_key, manifest_filename,
)


SOURCE = "a" * 40
PAYLOAD = b"verified installer bytes for unit tests"


class Response(io.BytesIO):
    def __init__(self, content, url, headers=None):
        super().__init__(content)
        self.url = url
        self.headers = headers or {}

    def geturl(self):
        return self.url


class FakeNetwork:
    def __init__(self):
        self.routes = {}
        self.calls = []
        self.add_json(REPOSITORY_INFO_URL, {"id": int(REPOSITORY_ID), "full_name": RENAMED_REPOSITORY})

    def add_json(self, url, data):
        self.routes[url] = json.dumps(data).encode()

    def __call__(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        value = self.routes[request.full_url]
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return value(request.full_url)
        return Response(value, request.full_url)


def release_fixture(version="0.7.0", *, prerelease=False, platform="windows-x86_64", payload=PAYLOAD):
    tag = "v" + version
    deb_version = version
    for suffix in ("rc", "a", "b"):
        if suffix in version:
            deb_version = version.replace(suffix, "~" + suffix)
            break
    name = "NIPAT-Setup.exe" if platform == "windows-x86_64" else f"nipat-desktop_{deb_version}_amd64.deb"
    if platform.startswith("darwin-"):
        name = f"NIPAT-{version}-macos-{platform.removeprefix('darwin-')}.pkg"
    if platform == "windows-zip-x86_64":
        name = f"NIPAT-{version}-Windows-completo.zip"
    if platform == "windows-bootstrap-x86_64":
        name = f"NIPAT-{version}-Windows-payload.zip"
    asset = {"platform": platform, "name": name, "size": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest(),
             "url": f"{WEB}/releases/download/{tag}/{name}"}
    manifest = {"schema_version": 1, "product": "nipat-desktop", "version": version,
                "release_tag": tag, "channel": "testing" if prerelease else "stable",
                "source_commit": SOURCE, "minimum_updater_version": 1, "assets": [asset],
                "release_notes_url": f"{WEB}/releases/tag/{tag}"}
    release = {"tag_name": tag, "draft": False, "prerelease": prerelease,
               "published_at": "2026-10-25T10:00:00Z", "html_url": manifest["release_notes_url"],
               "assets": [
                   {"name": manifest_filename(platform, version), "state": "uploaded", "size": len(json.dumps(manifest).encode()),
                    "browser_download_url": f"{WEB}/releases/download/{tag}/{manifest_filename(platform, version)}"},
                   {"name": name, "state": "uploaded", "size": len(payload), "browser_download_url": asset["url"]},
               ]}
    return release, manifest


class UpdateDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.network = FakeNetwork()
        self.client = UpdateClient(opener=self.network)

    def install(self, *fixtures):
        releases = []
        for release, manifest in fixtures:
            releases.append(release)
            tag = release["tag_name"]
            feed = next((item["name"] for item in release["assets"]
                         if item["name"].startswith("update-manifest")), "update-manifest.json")
            self.network.add_json(f"{WEB}/releases/download/{tag}/{feed}", manifest)
            self.network.add_json(f"{API}/git/ref/tags/{tag}",
                                  {"ref": f"refs/tags/{tag}", "object": {"type": "commit", "sha": SOURCE}})
        self.network.add_json(f"{API}/releases?per_page=100&page=1", releases)

    def check(self, channel="testing", current="0.6.0", platform="windows-x86_64"):
        return self.client.check(current, channel, platform)

    def test_renamed_repository_can_serve_unchanged_historical_manifests(self):
        for platform in ("windows-x86_64", "windows-zip-x86_64", "windows-bootstrap-x86_64",
                         "linux-x86_64", "darwin-arm64", "darwin-x86_64"):
            legacy_web = f"https://github.com/{LEGACY_REPOSITORY}"
            for active, historical in ((LEGACY_REPOSITORY, True), (RENAMED_REPOSITORY, True),
                                       (RENAMED_REPOSITORY, False)):
                with self.subTest(platform=platform, active=active, historical=historical):
                    release, manifest = release_fixture("0.9.9", platform=platform)
                    self.network.add_json(REPOSITORY_INFO_URL, {"id": int(REPOSITORY_ID), "full_name": active})
                    active_web = f"https://github.com/{active}"
                    active_api = f"https://api.github.com/repos/{active}"
                    release = json.loads(json.dumps(release).replace(WEB, active_web))
                    if historical:
                        manifest = json.loads(json.dumps(manifest).replace(WEB, legacy_web))
                        self.assertTrue(manifest["release_notes_url"].startswith(legacy_web + "/"))
                    release["assets"][0]["size"] = len(json.dumps(manifest).encode())
                    self.network.add_json(active_api + "/releases?per_page=100&page=1", [release])
                    self.network.add_json(active_api + "/git/ref/tags/v0.9.9",
                                          {"ref": "refs/tags/v0.9.9", "object": {"type": "commit", "sha": SOURCE}})
                    self.network.add_json(release["assets"][0]["browser_download_url"], manifest)
                    offer = self.check(channel="stable", current="0.9.8", platform=platform).offer
                    self.assertIsNotNone(offer)
                    self.assertEqual(offer.asset.url, release["assets"][1]["browser_download_url"])
                    self.assertEqual(offer.release_notes_url, release["html_url"])

    def test_rejects_same_name_with_wrong_repository_id_and_unexpected_name_with_right_id(self):
        for repo_id, repository in [(1, LEGACY_REPOSITORY), (int(REPOSITORY_ID), "someone/NewPat-Desktop")]:
            self.network.calls.clear()
            self.network.add_json(REPOSITORY_INFO_URL, {"id": repo_id, "full_name": repository})
            self.assertEqual(self.check().status, "invalid_metadata")
            self.assertEqual([url for url, _ in self.network.calls], [REPOSITORY_INFO_URL])

    def test_gui_preview_never_consumes_an_automatic_update_feed(self):
        for version in ("0.9.0", "0.9.0rc1", "0.9.1", "0.9.1rc1"):
            for channel in ("stable", "testing"):
                with self.subTest(version=version, channel=channel):
                    result = self.check(channel, current=version)
                    self.assertEqual(result.status, "manual_update")
                    self.assertIsNone(result.offer)
        self.assertEqual(self.network.calls, [])

    def test_0899_stable_feed_behavior_is_preserved(self):
        self.install(release_fixture("0.8.100"))
        result = self.check("stable", current="0.8.99")
        self.assertEqual(result.status, "available")
        self.assertEqual(result.offer.version, "0.8.100")
        self.assertTrue(self.network.calls)

    def test_mac_uses_its_own_feed_and_architecture_specific_package(self):
        for architecture in ("arm64", "x86_64"):
            with self.subTest(architecture=architecture):
                self.setUp()
                self.install(release_fixture("0.8.2", platform="darwin-" + architecture))
                result = self.check(platform="darwin-" + architecture, current="0.8.1")
                self.assertEqual(result.status, "available")
                self.assertEqual(result.offer.asset.name, f"NIPAT-0.8.2-macos-{architecture}.pkg")
                self.assertTrue(any(url.endswith("update-manifest-macos.json") for url, _ in self.network.calls))
                self.assertFalse(any(url.endswith("/update-manifest.json") for url, _ in self.network.calls))

    def test_mac_architecture_detection_and_legacy_feed_selection(self):
        for architecture in ("arm64", "x86_64"):
            with patch("newpat.updates.sys.platform", "darwin"), patch(
                    "newpat.updates.host_platform.machine", return_value=architecture):
                self.assertEqual(detect_platform(), "darwin-" + architecture)
        self.assertEqual(manifest_filename("windows-x86_64"), "update-manifest.json")
        self.assertEqual(manifest_filename("linux-x86_64"), "update-manifest.json")

    def test_windows_channels_select_only_their_own_manifest_and_package(self):
        for platform, feed, name in (
            ("windows-x86_64", "update-manifest.json", "NIPAT-Setup.exe"),
            ("windows-zip-x86_64", "update-manifest-windows-zip.json", "NIPAT-0.8.99-Windows-completo.zip"),
            ("windows-bootstrap-x86_64", "update-manifest-windows-bootstrap.json", "NIPAT-0.8.99-Windows-payload.zip"),
        ):
            with self.subTest(platform=platform):
                self.setUp()
                self.install(release_fixture("0.8.99", platform=platform))
                result = self.check(platform=platform, current="0.8.95")
                self.assertEqual(result.status, "available")
                self.assertEqual(result.offer.asset.name, name)
                self.assertEqual(result.offer.asset.platform, platform)
                requested = [url.rsplit("/", 1)[-1] for url, _ in self.network.calls
                             if "/releases/download/" in url]
                self.assertEqual(requested, [feed])

    def test_bootstrap_payload_cannot_be_substituted_with_exe_or_full_zip(self):
        for name in ("NIPAT-Setup.exe", "NIPAT-0.8.99-Windows-completo.zip"):
            with self.subTest(name=name):
                self.setUp()
                release, manifest = release_fixture("0.8.99", platform="windows-bootstrap-x86_64")
                manifest["assets"][0]["name"] = name
                manifest["assets"][0]["url"] = f"{WEB}/releases/download/v0.8.99/{name}"
                self.install((release, manifest))
                self.assertEqual(self.check(platform="windows-bootstrap-x86_64").status, "invalid_metadata")

    def test_versions_compare_numerically_and_order_prerelease_phases(self):
        versions = ["0.9.0", "0.10.0a2", "0.10.0a10", "0.10.0b1", "0.10.0rc1", "0.10.0", "1.0.0"]
        self.assertEqual(sorted(reversed(versions), key=version_key), versions)
        for invalid in ("v0.6.0", "0.6", "0.6.0.dev1", "0.6.0+local", "01.0.0", "0.6.0rc"):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError):
                version_key(invalid)

    def test_newest_eligible_release_is_selected_independent_of_api_order(self):
        self.install(release_fixture("0.9.0"), release_fixture("0.10.0"), release_fixture("0.8.0"))
        result = self.check()
        self.assertEqual(result.status, "available")
        self.assertEqual(result.offer.version, "0.10.0")
        self.assertEqual(result.offer.asset_name, "NIPAT-Setup.exe")
        self.assertEqual(result.offer.size, len(PAYLOAD))
        self.assertFalse(any("/v0.9.0/" in url for url, _ in self.network.calls))

    def test_stable_excludes_testing_while_testing_can_select_either(self):
        self.install(release_fixture("0.7.0"), release_fixture("0.8.0rc1", prerelease=True))
        self.assertEqual(self.check("stable").offer.version, "0.7.0")
        self.assertEqual(self.check("testing").offer.version, "0.8.0rc1")
        self.install(release_fixture("0.7.0"))
        self.assertEqual(self.check("testing").offer.channel, "stable")

    def test_equal_or_older_release_never_proposes_a_downgrade(self):
        self.install(release_fixture("0.6.0"), release_fixture("0.5.9"))
        result = self.check()
        self.assertEqual(result.status, "up_to_date")
        self.assertIsNone(result.offer)
        self.assertEqual(len(self.network.calls), 2)

    def test_draft_unpublished_and_unmanaged_releases_are_not_offered(self):
        draft, manifest = release_fixture("0.9.0")
        draft["draft"] = True
        unpublished, other = release_fixture("0.8.0")
        unpublished["published_at"] = None
        unmanaged, third = release_fixture("0.7.0")
        unmanaged["assets"] = []
        self.install((draft, manifest), (unpublished, other), (unmanaged, third))
        result = self.check()
        self.assertEqual(result.status, "no_eligible_release")
        self.assertIsNone(result.offer)

    def test_missing_platform_is_distinguished_from_available_update(self):
        self.install(release_fixture("0.7.0", platform="linux-x86_64"))
        self.assertEqual(self.check().status, "no_eligible_release")
        result = self.check(platform="linux-x86_64")
        self.assertEqual(result.status, "available")
        self.assertEqual(result.offer.asset.name, "nipat-desktop_0.7.0_amd64.deb")

    def test_debian_prerelease_asset_name_uses_tilde(self):
        self.install(release_fixture("0.7.0rc2", platform="linux-x86_64", prerelease=True))
        result = self.check(platform="linux-x86_64")
        self.assertEqual(result.status, "available")
        self.assertEqual(result.offer.asset.name, "nipat-desktop_0.7.0~rc2_amd64.deb")

    def test_wrong_repository_and_manifest_urls_are_refused_before_fetch(self):
        for field in ("html_url", "manifest_url"):
            with self.subTest(field=field):
                release, manifest = release_fixture()
                if field == "html_url":
                    release[field] = "https://github.com/another/repo/releases/tag/v0.7.0"
                else:
                    release["assets"][0]["browser_download_url"] = "https://example.org/update-manifest.json"
                self.install((release, manifest))
                self.network.calls.clear()
                self.assertEqual(self.check().status, "invalid_metadata")
                self.assertEqual(len(self.network.calls), 2)

    def test_invalid_newest_release_never_silently_falls_back_to_older_offer(self):
        newest, manifest = release_fixture("0.8.0")
        manifest["assets"][0]["sha256"] = "invalid"
        self.install((newest, manifest), release_fixture("0.7.0"))
        result = self.check()
        self.assertEqual(result.status, "invalid_metadata")
        self.assertIsNone(result.offer)
        self.assertFalse(any("/v0.7.0/" in url for url, _ in self.network.calls))

    def test_manifest_contract_rejects_mismatches_and_unsafe_assets(self):
        mutations = [
            lambda m: m.update(schema_version=True), lambda m: m.update(schema_version=2),
            lambda m: m.update(product="another-product"), lambda m: m.update(version="0.8.0"),
            lambda m: m.update(release_tag="v0.8.0"), lambda m: m.update(source_commit="z" * 40),
            lambda m: m.update(channel="testing"), lambda m: m.update(minimum_updater_version=True),
            lambda m: m.update(assets=[]), lambda m: m.update(unrecognized=True),
            lambda m: m.update(release_notes_url="https://example.com/notes"),
            lambda m: m["assets"][0].update(name="../NIPAT-Setup.exe"),
            lambda m: m["assets"][0].update(size=True),
            lambda m: m["assets"][0].update(size=2**31),
            lambda m: m["assets"][0].update(url="https://example.com/NIPAT-Setup.exe"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                release, manifest = release_fixture()
                mutate(manifest)
                self.install((release, manifest))
                self.assertEqual(self.check().status, "invalid_metadata")

    def test_package_must_be_uploaded_on_the_same_release_with_same_size(self):
        for change in ({"size": len(PAYLOAD) + 1}, {"state": "new"},
                       {"browser_download_url": "https://example.org/file"}):
            release, manifest = release_fixture()
            release["assets"][1].update(change)
            self.install((release, manifest))
            with self.subTest(change=change):
                self.assertEqual(self.check().status, "invalid_metadata")

    def test_github_digest_when_present_must_match_manifest(self):
        release, manifest = release_fixture()
        release["assets"][1]["digest"] = "sha256:" + "b" * 64
        self.install((release, manifest))
        self.assertEqual(self.check().status, "invalid_metadata")
        release["assets"][1]["digest"] = "sha256:" + manifest["assets"][0]["sha256"]
        self.install((release, manifest))
        self.assertEqual(self.check().status, "available")

    def test_tag_commit_must_match_manifest_and_annotated_tags_are_resolved(self):
        self.install(release_fixture())
        tag_url = f"{API}/git/ref/tags/v0.7.0"
        self.network.add_json(tag_url, {"ref": "refs/tags/v0.7.0", "object": {"type": "commit", "sha": "b" * 40}})
        self.assertEqual(self.check().status, "invalid_metadata")
        self.network.add_json(tag_url, {"ref": "refs/tags/v0.7.0", "object": {"type": "tag", "sha": "b" * 40}})
        self.network.add_json(f"{API}/git/tags/{'b' * 40}", {"object": {"type": "commit", "sha": SOURCE}})
        self.assertEqual(self.check().status, "available")

    def test_required_newer_updater_has_explicit_result(self):
        release, manifest = release_fixture()
        manifest["minimum_updater_version"] = 3
        self.install((release, manifest))
        self.assertEqual(self.check().status, "unsupported_updater")

    def test_offline_and_rate_limited_checks_do_not_claim_up_to_date(self):
        url = f"{API}/releases?per_page=100&page=1"
        self.network.routes[url] = URLError("offline")
        self.assertEqual(self.check().status, "offline")
        self.network.routes[url] = HTTPError(url, 403, "rate", {"X-RateLimit-Remaining": "0"}, None)
        self.assertEqual(self.check().status, "rate_limited")

    def test_truncated_http_metadata_is_reported_without_escaping_the_client(self):
        class TruncatedResponse(Response):
            def read1(self, size=-1):
                raise IncompleteRead(b"partial", 100)
        self.network.routes[f"{API}/releases?per_page=100&page=1"] = lambda url: TruncatedResponse(b"", url)
        result = self.check()
        self.assertEqual(result.status, "offline")
        self.assertIsNone(result.offer)

    def test_discovery_budget_and_page_limit_are_explicitly_incomplete(self):
        clock = Mock(side_effect=[0.0, 0.0, 20.0])
        self.network.add_json(f"{API}/releases?per_page=100&page=1", [])
        client = UpdateClient(opener=self.network, clock=clock)
        self.assertEqual(client.check("0.6.0", "testing", "windows-x86_64").status, "incomplete")
        release, _ = release_fixture()
        for page in range(1, 4):
            self.network.add_json(f"{API}/releases?per_page=100&page={page}", [release] * 100)
        self.assertEqual(self.check().status, "incomplete")

    def test_malformed_json_duplicate_keys_and_oversized_payload_are_rejected(self):
        self.install(release_fixture())
        url = f"{WEB}/releases/download/v0.7.0/update-manifest.json"
        for data in (b"{broken", b'{"schema_version":1,"schema_version":1}', b" " * (128 * 1024 + 1)):
            with self.subTest(size=len(data)):
                self.network.routes[url] = data
                self.assertEqual(self.check().status, "invalid_metadata")

    def test_redirects_require_https_and_official_asset_host(self):
        handler = _SafeRedirectHandler()
        request = Request(f"{WEB}/releases/download/v0.7.0/NIPAT-Setup.exe")
        for url in ("http://release-assets.githubusercontent.com/file", "https://evil.example/file",
                    "https://github.com@evil.example/file", "https://github.com:444/file"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        redirected = handler.redirect_request(request, None, 302, "Found", {},
                                               "https://release-assets.githubusercontent.com/file?token=temporary")
        self.assertTrue(redirected.full_url.startswith("https://release-assets.githubusercontent.com/"))

    def test_platform_detection_rejects_unsupported_architecture(self):
        with patch("newpat.updates.sys.platform", "win32"), patch("newpat.updates.host_platform.machine", return_value="AMD64"):
            self.assertEqual(detect_platform(), "windows-x86_64")
        for operating_system, architecture in (("win32", "arm64"), ("linux", "arm64"),
                                                ("darwin", "i386"), ("freebsd", "x86_64")):
            with self.subTest(operating_system=operating_system, architecture=architecture), \
                    patch("newpat.updates.sys.platform", operating_system), \
                    patch("newpat.updates.host_platform.machine", return_value=architecture), \
                    self.assertRaises(UpdateError) as rejected:
                detect_platform()
            self.assertEqual(rejected.exception.status, "unsupported_platform")


class UpdateDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / "updates" / "0.7.0"
        release, manifest = release_fixture()
        self.offer = UpdateOffer(manifest["version"], manifest["release_tag"], manifest["channel"],
                                 SOURCE, 1, UpdateAsset(**manifest["assets"][0]), manifest["release_notes_url"])
        self.network = FakeNetwork()
        self.network.routes[self.offer.asset.url] = PAYLOAD
        self.client = UpdateClient(opener=self.network)

    def test_download_verifies_bytes_then_reuses_rehashed_cache(self):
        progress = []
        downloaded = self.client.download(self.offer, self.directory, lambda done, total: progress.append((done, total)))
        self.assertEqual(downloaded.read_bytes(), PAYLOAD)
        self.assertEqual(progress[0], (0, len(PAYLOAD)))
        self.assertEqual(progress[-1], (len(PAYLOAD), len(PAYLOAD)))
        self.assertEqual(self.client.download(self.offer, self.directory), downloaded)
        self.assertEqual(len(self.network.calls), 1)
        downloaded.write_bytes(b"corrupted existing cache")
        self.client.download(self.offer, self.directory)
        self.assertEqual(downloaded.read_bytes(), PAYLOAD)
        self.assertEqual(len(self.network.calls), 2)

    def test_wrong_hash_or_size_never_replaces_cached_file(self):
        self.directory.mkdir(parents=True)
        existing = self.directory / self.offer.asset.name
        existing.write_bytes(b"previous file")
        for content in (b"x" * len(PAYLOAD), b"short", PAYLOAD + b"extra"):
            with self.subTest(content=content):
                self.network.routes[self.offer.asset.url] = content
                with self.assertRaises(UpdateError):
                    self.client.download(self.offer, self.directory)
                self.assertEqual(existing.read_bytes(), b"previous file")
                self.assertEqual(list(self.directory.iterdir()), [existing])

    def test_interrupted_download_removes_only_its_partial_file(self):
        class InterruptedResponse(Response):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("connection lost")
                return super().read(5)
        self.network.routes[self.offer.asset.url] = lambda url: InterruptedResponse(PAYLOAD, url)
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_truncated_http_download_removes_partial_and_reports_update_error(self):
        class TruncatedResponse(Response):
            def read(self, size=-1):
                raise IncompleteRead(b"partial", 100)
        self.network.routes[self.offer.asset.url] = lambda url: TruncatedResponse(PAYLOAD, url)
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])
        self.network.routes[self.offer.asset.url] = PAYLOAD
        with self.assertRaises(KeyboardInterrupt):
            self.client.download(self.offer, self.directory, Mock(side_effect=KeyboardInterrupt))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_bad_content_length_and_untrusted_final_url_are_refused(self):
        self.network.routes[self.offer.asset.url] = lambda url: Response(PAYLOAD, url, {"Content-Length": "9999"})
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, self.directory)
        self.network.routes[self.offer.asset.url] = lambda url: Response(PAYLOAD, "https://evil.example/file")
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_directory_traversal_and_linked_destinations_are_rejected(self):
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, self.root / "updates" / ".." / "elsewhere")
        target = self.root / "other"
        target.mkdir()
        linked = self.root / "linked"
        try:
            linked.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, linked / "child")
        self.directory.mkdir(parents=True)
        unrelated = target / "unrelated.exe"
        unrelated.write_bytes(b"do not modify")
        (self.directory / self.offer.asset.name).symlink_to(unrelated)
        with self.assertRaises(UpdateError):
            self.client.download(self.offer, self.directory)
        self.assertEqual(unrelated.read_bytes(), b"do not modify")
        self.assertFalse((target / "child").exists())


if __name__ == "__main__":
    unittest.main()
