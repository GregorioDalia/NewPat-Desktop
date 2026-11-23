"""Regression checks for executable examples and packaged documentation."""
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import check_documentation_package as docs


class DocumentationPackageTests(unittest.TestCase):
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
