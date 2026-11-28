"""Exercise the publication-to-client contract with exact, local HTTP fixtures."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from newpat.repository import REPOSITORY_ID, REPOSITORY_INFO_URL
from newpat.updates import UpdateClient

SPEC = importlib.util.spec_from_file_location("update_publisher", Path(__file__).with_name("publish_windows_release.py"))
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class Response(io.BytesIO):
    def __init__(self, url, contents):
        super().__init__(contents)
        self.url = url
        self.headers = {"Content-Length": str(len(contents))}

    def geturl(self):
        return self.url


class PublishedUpdateContract(unittest.TestCase):
    def test_accepted_pair_is_discoverable_downloadable_and_channel_filtered(self):
        for channel in ("testing", "stable"):
            with self.subTest(channel=channel):
                self.check_published_pair(channel)

    def check_published_pair(self, channel, version="0.9.100", canonical=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            commit = "c" * 40
            tag = "v" + version
            manifest = {"version": version, "release_tag": tag, "source_commit": commit}
            pair = {"version": version, "source_commit": commit}
            packages = [("windows", "NewPat-Setup.exe"), ("linux", f"newpat-desktop_{version}_amd64.deb")]
            platforms = [("windows-x86_64", "windows"), ("linux-x86_64", "linux")]
            feeds = ["update-manifest.json"]
            if publisher.requires_macos(version):
                packages += [(f"macos_{arch}", f"NewPat-{version}-macos-{arch}.pkg") for arch in ("arm64", "x86_64")]
                platforms += [(f"darwin-{arch}", f"macos_{arch}") for arch in ("arm64", "x86_64")]
                feeds.append("update-manifest-macos.json")
            if publisher.requires_windows_zip(version):
                suffix = "Windows-complete.zip"
                packages.append(("windows_zip", f"NewPat-{version}-{suffix}"))
                platforms.append(("windows-zip-x86_64", "windows_zip"))
                feeds.append("update-manifest-windows-zip-v2.json")
            if publisher.requires_windows_bootstrap(version):
                packages.append(("windows_payload", f"NewPat-{version}-Windows-payload.zip"))
                platforms.append(("windows-bootstrap-x86_64", "windows_payload"))
                feeds.append("update-manifest-windows-bootstrap-v2.json")
            for system, name in packages:
                path = root / name
                path.write_bytes(b"fixture bytes for verified " + system.encode())
                pair[system] = {"file": name, "sha256": publisher.sha256(path)}
            document = publisher.write_update_manifest(root, manifest, pair, channel)
            self.assertFalse((root / "update-manifest-windows-bootstrap.json").exists())
            self.assertFalse((root / "update-manifest-windows-zip.json").exists())
            for method in ("zip", "bootstrap"):
                self.assertEqual(json.loads((root / f"update-manifest-windows-{method}-v2.json").read_text())["minimum_updater_version"], 2)
            canonical = canonical or publisher.REPO
            api = f"https://api.github.com/repos/{canonical}"
            web = f"https://github.com/{canonical}"
            release_url = f"{web}/releases/tag/{tag}"
            payloads = {REPOSITORY_INFO_URL: json.dumps({"id": int(REPOSITORY_ID), "full_name": canonical}).encode()}
            assets = []
            self.assertEqual({entry["platform"] for entry in document["assets"]}, {"windows-x86_64", "linux-x86_64"})
            for name in [*feeds, *(name for _, name in packages)]:
                content = (root / name).read_bytes()
                url = f"{web}/releases/download/{tag}/{name}"
                payloads[url] = content
                assets.append({"name": name, "state": "uploaded", "size": len(content),
                               "browser_download_url": url,
                               "digest": "sha256:" + hashlib.sha256(content).hexdigest()})
            release = {"tag_name": tag, "draft": False, "prerelease": channel == "testing",
                       "published_at": "2026-10-25T12:00:00Z", "html_url": release_url, "assets": assets}
            payloads[f"{api}/releases?per_page=100&page=1"] = json.dumps([release]).encode()
            payloads[f"{api}/git/ref/tags/{tag}"] = json.dumps({
                "ref": "refs/tags/" + tag, "object": {"type": "commit", "sha": commit},
            }).encode()
            requests = []

            def open_fixture(request, timeout):
                requests.append(request.full_url)
                return Response(request.full_url, payloads[request.full_url])

            client = UpdateClient(opener=open_fixture)
            for platform, system in platforms:
                check = client.check("0.9.99", "testing", platform)
                self.assertEqual(check.status, "available", check.message)
                self.assertEqual(check.offer.source_commit, commit)
                self.assertEqual(check.offer.asset.sha256, pair[system]["sha256"])
                package = client.download(check.offer, root / "cache" / platform / version)
                self.assertEqual(package.read_bytes(), (root / pair[system]["file"]).read_bytes())
                self.assertEqual(check.offer.release_notes_url, release_url)
            stable = client.check("0.9.99", "stable", "windows-x86_64")
            if channel == "stable":
                self.assertEqual(stable.status, "available", stable.message)
                self.assertEqual(stable.offer.channel, "stable")
            else:
                self.assertIsNone(stable.offer)
            self.assertIsNone(client.check(version, "testing", "windows-x86_64").offer)
            self.assertTrue(all(url == REPOSITORY_INFO_URL or url.startswith((api + "/", web + "/releases/")) for url in requests))


if __name__ == "__main__":
    unittest.main()
