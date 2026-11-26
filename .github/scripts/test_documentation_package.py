"""Regression checks for executable examples and packaged documentation."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import check_documentation_package as docs


class DocumentationPackageTests(unittest.TestCase):
    def test_installation_guides_link_directly_to_the_same_accepted_packages(self):
        # A development branch can still advertise the previous stable release.
        # The acceptance record is available offline; public availability is
        # checked against GitHub when the documentation links are updated.
        def downloads(text):
            return {url for _, url in docs.local_links(text) if "/releases/download/" in url}

        readme = (docs.ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("## Download\n", 1)[1].split("\n## ", 1)[0]
        urls = downloads(section)
        prefixes = {url.rsplit("/", 1)[0] for url in urls}
        self.assertEqual(len(prefixes), 1, "The download section must identify one stable release")
        prefix, = prefixes
        tag = prefix.rsplit("/", 1)[1]
        self.assertRegex(tag, r"^v[0-9]+\.[0-9]+\.[0-9]+$")
        version = tag[1:]
        receipt = docs.ROOT / ".github/release-acceptance" / (tag + ".json")
        self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["decision"], "accepted-for-research")
        windows = {f"NewPat-{version}-Windows-complete.zip", "NewPat-Setup.exe", "SHA256SUMS"}
        packages = windows | {f"NewPat-{version}-macos-arm64.pkg", f"NewPat-{version}-macos-x86_64.pkg",
                              f"newpat-desktop_{version}_amd64.deb"}
        self.assertTrue({f"{prefix}/{name}" for name in packages} <= urls)
        guide = (docs.ROOT / "docs/WINDOWS_INSTALLER.md").read_text(encoding="utf-8")
        self.assertTrue({f"{prefix}/{name}" for name in windows} <= downloads(guide))

    def test_windows_zip_launcher_is_a_documented_cli_entry(self):
        text = r'''~~~powershell
.\newpat.cmd dnp-call --bam "C:\example data\sample.bam"
~~~'''
        self.assertEqual(list(docs.commands(text)),
                         [(2, ["dnp-call", "--bam", r"C:\example data\sample.bam"])])

    def test_multiline_examples_are_parsed_in_their_own_shell(self):
        text = """```powershell
& $newpat workflow snp-batch --bam ".\\space here.bam" `
    --panel ".\\panel.tsv"
```

```sh
newpat settings \\
  cpin
```
```text
newpat fictional-command
```
"""
        self.assertEqual(list(docs.commands(text)), [
            (2, ["workflow", "snp-batch", "--bam", ".\\space here.bam", "--panel", ".\\panel.tsv"]),
            (7, ["settings", "cpin"]),
        ])

    def test_continuation_requires_a_line_in_the_same_block(self):
        with self.assertRaisesRegex(ValueError, "Unfinished command"):
            list(docs.commands("```powershell\n& $newpat doctor `\n```\n"))

    def test_invalid_option_fails_with_guide_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            guide = Path(tmp) / "guide.md"
            guide.write_text("```sh\nnewpat dnp-call --impossible-option\n```", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"guide.md:2:"):
                docs.check_examples(guide, docs.build_parser())

    def test_package_readme_must_match_reviewed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "zip-readme.txt"
            readme.write_bytes(b"expected\r\n")
            package = Path(tmp) / "windows.zip"
            with ZipFile(package, "w") as archive:
                archive.writestr("README.txt", b"expected\n")
            with self.assertRaisesRegex(ValueError, "README.txt"):
                docs.check_members(package, {"README.txt": readme})

    def test_a_required_text_present_on_disk_but_not_in_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("NewPat", encoding="utf-8")
            (root / "distribution-files.txt").write_text("distribution-files.txt\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"Missing.*README.md"):
                docs.check_package(root, root / "work")

    def test_offline_guide_links_must_resolve_in_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            guide = root / "guide.md"
            guide.write_text("[Start](./quickstart.md#demo) · [Online](https://example.org)", encoding="utf-8")
            quickstart = root / "quickstart.md"
            quickstart.write_text("# Demo", encoding="utf-8")
            files = {"guide.md": guide}
            with self.assertRaisesRegex(ValueError, "guide.md:1:.*quickstart.md"):
                docs.offline_targets(root, files, ["guide.md"])
            files["quickstart.md"] = quickstart
            self.assertEqual(docs.offline_targets(root, files, ["guide.md"]), {"quickstart.md"})
