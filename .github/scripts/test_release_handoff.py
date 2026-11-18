"""Acceptance-only CI and automatic publication keep exact build ownership."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import acceptance_ci as checker
import automatic_release as automatic
import publish_windows_release as publisher
import qualification_evidence as qualification


ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = ".github/release-acceptance/v0.8.60.json"


def record_fixture():
    return json.loads((ROOT / RECORD_PATH).read_text(encoding="utf-8"))


class AcceptanceBuildTests(unittest.TestCase):
    def setUp(self):
        self.record = record_fixture()
        self.run = {
            "id": self.record["build_run_id"], "head_sha": self.record["source_commit"],
            "status": "completed", "conclusion": "success", "event": "workflow_dispatch",
            "path": ".github/workflows/windows-installer.yml",
            "repository": {"full_name": publisher.REPO}, "head_repository": {"full_name": publisher.REPO},
        }
        self.jobs = [{"name": name, "conclusion": "success"}
                     for name in publisher.required_build_jobs(self.record["version"])]

    def test_successful_exact_build_and_every_platform_are_required(self):
        checker.validate_build(self.record, self.run, self.jobs)
        for field, value in (("id", 12), ("head_sha", "f" * 40), ("conclusion", "failure"),
                             ("event", "pull_request"), ("path", ".github/workflows/ci.yml"),
                             ("head_repository", {"full_name": "fork/nipat"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                checker.validate_build(self.record, dict(self.run, **{field: value}), self.jobs)
        for index in range(len(self.jobs)):
            jobs = copy.deepcopy(self.jobs)
            jobs[index]["conclusion"] = "skipped"
            with self.subTest(job=jobs[index]["name"]), self.assertRaises(ValueError):
                checker.validate_build(self.record, self.run, jobs)

    def test_evidence_must_belong_to_exact_nonexpired_build(self):
        artifact = {"name": "nipat-installer-set-evidence", "expired": False,
                    "workflow_run": {"id": self.run["id"], "head_sha": self.run["head_sha"]}}
        self.assertEqual(checker.evidence_artifact({"artifacts": [artifact]}, self.record), artifact)
        for candidate in (dict(artifact, expired=True), dict(artifact, workflow_run={"id": 12}),
                          dict(artifact, workflow_run={"id": self.run["id"], "head_sha": "f" * 40})):
            with self.assertRaises(ValueError):
                checker.evidence_artifact({"artifacts": [candidate]}, self.record)
        with self.assertRaises(ValueError):
            checker.evidence_artifact({"artifacts": [artifact, artifact]}, self.record)

    def test_gui_build_requires_testing_and_every_native_platform_job(self):
        for version in ("0.9.0", "0.9.1", "0.9.5"):
            with self.subTest(version=version):
                self.check_gui_build(version)

    def test_first_stable_newpat_keeps_all_preview_platform_checks(self):
        record = dict(self.record, version="0.9.7", publication_channel="stable")
        required = publisher.required_build_jobs("0.9.5")
        self.assertEqual(publisher.required_build_jobs("0.9.7"), required)
        jobs = [{"name": name, "conclusion": "success"} for name in required]
        checker.validate_build(record, self.run, jobs)
        for index, job in enumerate(jobs):
            with self.subTest(job=job["name"]), self.assertRaisesRegex(ValueError, "build job"):
                checker.validate_build(record, self.run, jobs[:index] + jobs[index + 1:])

    def check_gui_build(self, version):
        record = dict(self.record, version=version, publication_channel="testing")
        jobs = [{"name": name, "conclusion": "success"}
                for name in publisher.required_build_jobs(record["version"])]
        self.assertTrue({"macos-installer (arm64)", "macos-installer (x86_64)"}
                        <= {job["name"] for job in jobs})
        checker.validate_build(record, self.run, jobs)
        for channel in (None, "stable"):
            with self.subTest(channel=channel), self.assertRaisesRegex(ValueError, "explicit testing"):
                checker.validate_build(dict(record, publication_channel=channel), self.run, jobs)
        for index in range(len(jobs)):
            with self.subTest(job=jobs[index]["name"]), self.assertRaisesRegex(ValueError, "build job"):
                checker.validate_build(record, self.run, jobs[:index] + jobs[index + 1:])

    def test_symlink_missing_and_wrong_version_records_are_rejected(self):
        for mode in ("", "120000 blob abc\t" + RECORD_PATH):
            with patch.object(publisher, "command", return_value=mode), self.assertRaises(ValueError):
                checker.read_record(RECORD_PATH, "b" * 40)
        with patch.object(publisher, "command", return_value="100644 blob abc\t" + RECORD_PATH), \
                patch.object(publisher, "source_bytes", return_value=json.dumps(self.record).encode()), \
                patch.object(publisher, "committed_version", return_value="0.8.61"), self.assertRaises(ValueError):
            checker.read_record(RECORD_PATH, "b" * 40)


class AcceptanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.record = record_fixture()
        self.manifest = {"version": self.record["version"], "source_commit": self.record["source_commit"],
                         "assets": {"scientific_image": {"sha256": self.record["scientific_archive_sha256"]}}}
        self.components = self.root / "components"
        self.components.mkdir()
        manifest_bytes = json.dumps(self.manifest).encode()
        (self.components / "installer-manifest.json").write_bytes(manifest_bytes)
        self.record["installer_manifest_sha256"] = qualification.digest(manifest_bytes)
        self.installer_set = {
            "version": self.record["version"], "source_commit": self.record["source_commit"],
            "installer_manifest_sha256": self.record["installer_manifest_sha256"],
            "scientific_archive": {"sha256": self.record["scientific_archive_sha256"]},
            "linux_upgrade_check": {"sha256": self.record["linux_upgrade_check_sha256"]},
            "publication_authorized": False,
        }
        for key in ("windows", "linux", "macos_arm64", "macos_x86_64"):
            self.installer_set[key] = {"sha256": self.record[key + "_installer_sha256"]}
        self.evidence = self.root / "evidence"
        qualification.build(self.evidence, self.installer_set, {"components": self.components})
        (self.evidence / "installer-set-check.json").write_text(json.dumps(self.installer_set))
        self.record["qualification_evidence_sha256"] = publisher.sha256(self.evidence / qualification.ARCHIVE)

    def verify(self):
        # Numerical comparison and baseline validation have their own extensive
        # fixtures. Here they must be reached only after the real byte checks.
        with patch.object(publisher, "verify_research_baseline") as baseline, \
                patch.object(checker.acceptance, "verify_scientific_equivalence") as scientific:
            result = checker.verify_evidence(self.record, self.evidence)
            baseline.assert_called_once()
            scientific.assert_called_once()
            return result

    def test_real_archive_and_manifest_hashes_reach_scientific_validators(self):
        self.assertEqual(self.verify(), self.installer_set)

    def test_replaced_installer_cannot_pass_acceptance(self):
        self.installer_set["windows"]["sha256"] = "f" * 64
        (self.evidence / "installer-set-check.json").write_text(json.dumps(self.installer_set))
        with self.assertRaisesRegex(ValueError, "hashes do not identify"):
            self.verify()

    def test_tampered_archive_cannot_reach_numerical_verification(self):
        with (self.evidence / qualification.ARCHIVE).open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "archive bytes mismatch"):
            self.verify()

    def test_different_accepted_qualification_hash_is_rejected(self):
        self.record["qualification_evidence_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "differs from acceptance"):
            self.verify()


class AutomaticPublicationTests(unittest.TestCase):
    def setUp(self):
        self.revision = "b" * 40
        self.run = {"id": 123, "head_sha": self.revision, "head_branch": "main", "event": "push",
                    "path": ".github/workflows/ci.yml", "status": "completed", "conclusion": "success",
                    "repository": {"full_name": publisher.REPO}, "head_repository": {"full_name": publisher.REPO}}
        self.jobs = [{"name": "acceptance", "conclusion": "success"}, {"name": "required", "conclusion": "success"}]

    def paths(self, run=None, jobs=None, paths=None):
        fetch = Mock(side_effect=[run or self.run, {"jobs": jobs if jobs is not None else self.jobs}])
        with patch.object(publisher, "command", return_value="a" * 40), \
                patch.object(automatic, "changed_paths", return_value=paths if paths is not None else [RECORD_PATH]):
            return automatic.accepted_paths({"workflow_run": {"id": 123}}, self.revision, fetch=fetch)

    def test_completed_main_ci_selects_acceptance_only(self):
        self.assertEqual(self.paths(), [RECORD_PATH])
        self.assertEqual(self.paths(paths=[RECORD_PATH, "src/nipat/cli.py"]), [])
        self.assertEqual(self.paths(paths=[]), [])

    def test_fork_pr_failed_wrong_workflow_or_different_commit_cannot_publish(self):
        for field, value in (("id", 124), ("head_sha", "c" * 40), ("head_branch", "feature"),
                             ("event", "pull_request"), ("path", ".github/workflows/other.yml"),
                             ("conclusion", "failure"), ("status", "in_progress"),
                             ("head_repository", {"full_name": "fork/nipat"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.paths(run=dict(self.run, **{field: value}))

    def test_skipped_or_missing_acceptance_cannot_publish(self):
        for jobs in (self.jobs[1:], [{"name": "acceptance", "conclusion": "skipped"}, self.jobs[1]]):
            with self.assertRaises(ValueError):
                self.paths(jobs=jobs)

    def test_automatic_arguments_are_bound_to_the_reviewed_record(self):
        record = record_fixture()
        automatic.validate_publication(record, str(record["build_run_id"]), record["source_commit"], "stable")
        for run, sha, channel in (("12", record["source_commit"], "stable"),
                                  (str(record["build_run_id"]), "f" * 40, "stable"),
                                  (str(record["build_run_id"]), record["source_commit"], "testing")):
            with self.assertRaises(ValueError):
                automatic.validate_publication(record, run, sha, channel)

    def test_retry_skips_published_release_and_resumes_exact_draft(self):
        record = record_fixture()
        existing = {"tag_name": "v" + record["version"], "target_commitish": record["source_commit"],
                    "draft": False, "prerelease": False, "id": 42}
        version = record["version"]
        names = {
            "NIPAT-Setup.exe": "windows_installer_sha256",
            f"nipat-desktop_{version}_amd64.deb": "linux_installer_sha256",
            f"NIPAT-{version}-macos-arm64.pkg": "macos_arm64_installer_sha256",
            f"NIPAT-{version}-macos-x86_64.pkg": "macos_x86_64_installer_sha256",
            "installer-manifest.json": "installer_manifest_sha256",
            f"nipat-scientific-runtime-{version}-amd64.tar.gz": "scientific_archive_sha256",
            "qualification-evidence.zip": "qualification_evidence_sha256",
        }
        existing["assets"] = [{"name": name, "state": "uploaded", "digest": "sha256:" + record[field]}
                              for name, field in names.items()]
        with patch.object(publisher, "check_tag") as check:
            self.assertIsNone(automatic.publication_arguments(record, existing))
            check.assert_called_once_with("v" + version, record["source_commit"], required=True)
            with self.assertRaisesRegex(ValueError, "differs from the accepted asset"):
                automatic.publication_arguments(record, dict(existing, assets=existing["assets"][1:]))
        args = automatic.publication_arguments(record, dict(existing, draft=True))
        self.assertEqual(args[-2:], ["--draft-release-id", "42"])
        with self.assertRaises(ValueError):
            automatic.publication_arguments(record, dict(existing, target_commitish="f" * 40))
        self.assertEqual(automatic.release_channel("0.9.0a1", {"publication_channel": "testing"}), "testing")

    def test_numeric_candidate_obeys_explicit_channel(self):
        record = dict(record_fixture(), version="0.8.70", publication_channel="testing")
        self.assertEqual(automatic.publication_arguments(record, None)[-1], "testing")
        record["publication_channel"] = "stable"
        self.assertEqual(automatic.publication_arguments(record, None)[-1], "stable")
        record.pop("publication_channel")
        with self.assertRaisesRegex(ValueError, "authorized publication channel"):
            automatic.publication_arguments(record, None)

    def test_gui_candidate_cannot_implicitly_or_explicitly_be_promoted_to_stable(self):
        for version in ("0.9.0", "0.9.0a1", "0.9.1", "0.9.1rc1", "0.9.5", "0.9.5rc1"):
            record = dict(record_fixture(), version=version, publication_channel="testing")
            self.assertEqual(automatic.publication_arguments(record, None)[-1], "testing")
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "testing publication"):
                automatic.publication_arguments(dict(record, publication_channel="stable"), None)
            record.pop("publication_channel")
            with self.assertRaisesRegex(ValueError, "authorized publication channel"):
                automatic.publication_arguments(record, None)
        self.assertEqual(automatic.release_channel("0.9.2", {"publication_channel": "stable"}), "stable")

    def test_retry_requires_the_accepted_complete_windows_zip(self):
        record = dict(record_fixture(), version="0.8.95", publication_channel="stable",
                      windows_zip_sha256="e" * 64)
        existing = {"tag_name": "v0.8.95", "target_commitish": record["source_commit"],
                    "draft": False, "prerelease": False, "id": 42}
        names = {
            "NIPAT-Setup.exe": "windows_installer_sha256",
            "NIPAT-0.8.95-Windows-completo.zip": "windows_zip_sha256",
            "nipat-desktop_0.8.95_amd64.deb": "linux_installer_sha256",
            "NIPAT-0.8.95-macos-arm64.pkg": "macos_arm64_installer_sha256",
            "NIPAT-0.8.95-macos-x86_64.pkg": "macos_x86_64_installer_sha256",
            "installer-manifest.json": "installer_manifest_sha256",
            "nipat-scientific-runtime-0.8.95-amd64.tar.gz": "scientific_archive_sha256",
            "qualification-evidence.zip": "qualification_evidence_sha256",
        }
        existing["assets"] = [{"name": name, "state": "uploaded", "digest": "sha256:" + record[field]}
                              for name, field in names.items()]
        with patch.object(publisher, "check_tag"):
            self.assertIsNone(automatic.publication_arguments(record, existing))
            for replacement in (None, {"name": "NIPAT-0.8.95-Windows-completo.zip",
                                       "state": "uploaded", "digest": "sha256:" + "f" * 64}):
                assets = [asset for asset in existing["assets"] if not asset["name"].endswith("completo.zip")]
                if replacement is not None:
                    assets.append(replacement)
                with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "accepted asset bytes"):
                    automatic.publication_arguments(record, dict(existing, assets=assets))

    def test_retry_requires_separate_payload_and_exact_online_feed(self):
        self.check_bootstrap_retry("0.8.99", "stable")
        self.check_bootstrap_retry("0.9.7", "stable")

    def test_gui_retry_requires_testing_entrypoint_and_exact_testing_feeds(self):
        for version in ("0.9.0", "0.9.1", "0.9.5"):
            with self.subTest(version=version):
                self.check_bootstrap_retry(version, "testing")

    def check_bootstrap_retry(self, version, channel):
        record = dict(record_fixture(), version=version, publication_channel=channel,
                      windows_zip_sha256="e" * 64, windows_payload_sha256="f" * 64)
        existing = {"tag_name": "v" + version, "target_commitish": record["source_commit"],
                    "draft": False, "prerelease": channel == "testing", "id": 42}
        names = {
            "NIPAT-Setup.exe": "windows_installer_sha256",
            f"NIPAT-{version}-Windows-completo.zip": "windows_zip_sha256",
            f"NIPAT-{version}-Windows-payload.zip": "windows_payload_sha256",
            f"nipat-desktop_{version}_amd64.deb": "linux_installer_sha256",
            f"NIPAT-{version}-macos-arm64.pkg": "macos_arm64_installer_sha256",
            f"NIPAT-{version}-macos-x86_64.pkg": "macos_x86_64_installer_sha256",
            "installer-manifest.json": "installer_manifest_sha256",
            f"nipat-scientific-runtime-{version}-amd64.tar.gz": "scientific_archive_sha256",
            "qualification-evidence.zip": "qualification_evidence_sha256",
        }
        if version in {"0.9.0", "0.9.1", "0.9.5"}:
            record["windows_testing_sha256"] = "d" * 64
            names[f"NIPAT-{version}-Testing-installazione.zip"] = "windows_testing_sha256"
        if publisher.uses_newpat_brand(version):
            names.update({publisher.public_asset_name(name): field for name, field in list(names.items())
                          if publisher.public_asset_name(name) != name})
        existing["assets"] = [{"name": name, "state": "uploaded", "size": 100,
                               "digest": "sha256:" + record[field]} for name, field in names.items()]
        for filename, platform, feed in (
            (f"NIPAT-{version}-Windows-payload.zip", "windows-bootstrap-x86_64",
             publisher.WINDOWS_BOOTSTRAP_UPDATE_MANIFEST),
            (f"NIPAT-{version}-Windows-completo.zip", "windows-zip-x86_64",
             publisher.WINDOWS_ZIP_UPDATE_MANIFEST),
        ):
            document = {"schema_version": 1, "product": "nipat-desktop", "version": version,
                "release_tag": "v" + version, "channel": channel, "source_commit": record["source_commit"],
                "minimum_updater_version": 1, "assets": [{"platform": platform, "name": filename,
                "size": 100, "sha256": record[names[filename]],
                "url": f"https://github.com/{publisher.REPO}/releases/download/v{version}/{filename}"}],
                "release_notes_url": f"https://github.com/{publisher.REPO}/releases/tag/v{version}"}
            digest = automatic.hashlib.sha256((json.dumps(document, indent=2) + "\n").encode()).hexdigest()
            existing["assets"].append({"name": feed, "state": "uploaded", "digest": "sha256:" + digest})
        with patch.object(publisher, "check_tag"):
            self.assertIsNone(automatic.publication_arguments(record, existing))
            required = [f"NIPAT-{version}-Windows-payload.zip", publisher.WINDOWS_BOOTSTRAP_UPDATE_MANIFEST]
            if publisher.uses_newpat_brand(version):
                required.extend(name for name in names if name.startswith(("NewPat-", "newpat-desktop_")))
                altered = copy.deepcopy(existing)
                next(asset for asset in altered["assets"] if asset["name"] == "NewPat-Setup.exe")["size"] += 1
                with self.assertRaisesRegex(ValueError, "verified legacy size"):
                    automatic.publication_arguments(record, altered)
            if version in {"0.9.0", "0.9.1", "0.9.5"}:
                required.append(f"NIPAT-{version}-Testing-installazione.zip")
                missing_digest = dict(record)
                del missing_digest["windows_testing_sha256"]
                with self.assertRaisesRegex(ValueError, "testing entrypoint digest"):
                    automatic.publication_arguments(missing_digest, existing)
            for name in required:
                altered = copy.deepcopy(existing)
                altered["assets"] = [asset for asset in altered["assets"] if asset["name"] != name]
                with self.subTest(missing=name), self.assertRaises(ValueError):
                    automatic.publication_arguments(record, altered)
                altered = copy.deepcopy(existing)
                next(asset for asset in altered["assets"] if asset["name"] == name)["digest"] = "sha256:" + "0" * 64
                with self.subTest(replaced=name), self.assertRaises(ValueError):
                    automatic.publication_arguments(record, altered)

    def test_workflows_only_push_main_and_retain_protected_gate(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("  push:\n    branches: [main]", ci)
        self.assertIn("  pull_request:", ci)
        self.assertIn("  workflow_dispatch:", ci)
        self.assertIn("packaging, acceptance]", ci)
        automatic_workflow = (ROOT / ".github/workflows/publish-accepted-release.yml").read_text()
        self.assertIn("    branches: [main]", automatic_workflow)
        self.assertIn("github.event.workflow_run.event == 'push'", automatic_workflow)
        self.assertIn("ref: ${{ github.event.workflow_run.head_sha }}", automatic_workflow)
        self.assertIn("group: publish-nipat-release", automatic_workflow)
        self.assertNotIn("pull_request_target", automatic_workflow)


if __name__ == "__main__":
    unittest.main()
