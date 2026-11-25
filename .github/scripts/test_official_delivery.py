"""Official four-platform candidates preserve explicit source and byte ownership."""

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import tomllib
import unittest
from unittest import mock


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load("verify_release_source")
downloads = load("installer_downloads")
publisher = load("publish_windows_release")


class OfficialDeliveryTests(unittest.TestCase):
    def test_source_preflight_uses_real_distribution_blobs_and_manifest_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            repository = Path(temp)
            def git(*args):
                return subprocess.check_output(["git", "-c", "user.name=Test", "-c", "user.email=test@example.org",
                                                *args], cwd=repository, text=True).strip()

            git("init", "--quiet")
            report = "docs/validation/0.9.10-desktop-scheduling.json"
            protected = "docs/validation/unreviewed.json"
            inventory = source.acceptance.REQUIRED_OPERATIVE_PATHS | {"distribution-files.txt"}
            for name in inventory | {report, protected}:
                path = repository / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            def commit(paths):
                (repository / "distribution-files.txt").write_text("\n".join(sorted(paths)), encoding="utf-8")
                git("add", ".")
                git("commit", "-qm", "Fixture")
                return git("rev-parse", "HEAD")

            baseline = commit(inventory)
            candidate = commit(inventory | {report})
            self.assertEqual(source.check_reviewable_delta("0.9.10", baseline, candidate, repository=repository),
                             {report})
            with self.assertRaisesRegex(ValueError, "0.9.10-desktop-scheduling"):
                source.check_reviewable_delta("0.9.9", baseline, candidate, repository=repository)
            rejected = commit(inventory | {report, protected})
            with self.assertRaisesRegex(ValueError, "unreviewed.json"):
                source.check_reviewable_delta("0.9.10", baseline, rejected, repository=repository)
            with self.assertRaisesRegex(ValueError, "unreviewed.json"):
                source.check_reviewable_delta("0.9.10", rejected, candidate, repository=repository)
            missing = commit(inventory | {"src/absent.py"})
            with self.assertRaisesRegex(ValueError, "Missing distribution files"):
                source.check_reviewable_delta("0.9.10", baseline, missing, repository=repository)

    def test_source_preflight_uses_observation_from_last_accepted_version(self):
        with tempfile.TemporaryDirectory() as temp:
            records = Path(temp)
            for version in ("0.9.8", "0.9.11", "0.9.100"):
                (records / f"v{version}.json").write_text(json.dumps({
                    "observed_baseline": {"source_commit": version}}), encoding="utf-8")
            self.assertEqual(source.historical_baseline("0.9.19", records), "0.9.11")
            with self.assertRaisesRegex(ValueError, "No previous acceptance"):
                source.historical_baseline("0.9.7", records)

    def test_only_explicit_main_or_matching_release_branch_can_build(self):
        for ref in ("refs/heads/main", "refs/heads/release/0.8.2", "refs/heads/release/0.8.2-usability"):
            source.validate_dispatch("workflow_dispatch", ref, "0.8.2", source.PROFILE)
        for event, ref, version in (("push", "refs/heads/main", "0.8.2"),
                                    ("pull_request", "refs/pull/12/merge", "0.8.2"),
                                    ("workflow_dispatch", "refs/heads/experiment/0.8-portability", "0.8.2"),
                                    ("workflow_dispatch", "refs/heads/release/0.8.3", "0.8.2"),
                                    ("workflow_dispatch", "refs/heads/main", "0.8.0a1")):
            with self.subTest(event=event, ref=ref, version=version), self.assertRaises(ValueError):
                source.validate_dispatch(event, ref, version, source.PROFILE)
        with self.assertRaises(ValueError):
            source.validate_dispatch("workflow_dispatch", "refs/heads/main", "0.8.2",
                                     dict(source.PROFILE, channel="experimental08"))

    def test_diagnostic_candidate_uses_same_version_source_gate(self):
        for ref in ("refs/heads/main", "refs/heads/release/0.8.5", "refs/heads/release/0.8.5-diagnostics"):
            source.validate_dispatch("workflow_dispatch", ref, "0.8.5", source.PROFILE)
        for ref in ("refs/heads/release/0.8.2", "refs/heads/release/0.8.50",
                    "refs/heads/release/0.8.5evil", "refs/heads/feature/0.8.5-performance-diagnostics"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                source.validate_dispatch("workflow_dispatch", ref, "0.8.5", source.PROFILE)

    def test_newpat_brand_starts_at_095_without_changing_installation_identity(self):
        for version in ("0.8.2", "0.8.99", "0.9.0", "0.9.1", "0.9.4", "0.9.5", "0.9.6"):
            expected = source.NEWPAT_PROFILE if tuple(map(int, version.split("."))) >= (0, 9, 5) else source.PROFILE
            other = source.PROFILE if expected is source.NEWPAT_PROFILE else source.NEWPAT_PROFILE
            for ref in ("refs/heads/main", f"refs/heads/release/{version}"):
                with self.subTest(version=version, ref=ref):
                    source.validate_dispatch("workflow_dispatch", ref, version, expected)
                    with self.assertRaises(ValueError):
                        source.validate_dispatch("workflow_dispatch", ref, version, other)
        for key, value in source.NEWPAT_PROFILE.items():
            with self.subTest(field=key), self.assertRaises(ValueError):
                source.validate_dispatch("workflow_dispatch", "refs/heads/main", "0.9.5",
                                         dict(source.NEWPAT_PROFILE, **{key: f"different-{value}"}))

    def test_actual_checkout_profile_passes_official_candidate_preflight(self):
        project = Path(__file__).resolve().parents[2]
        version = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        profile = json.loads((project / "installer/windows/install-profile.json").read_text(encoding="utf-8"))
        for ref in ("refs/heads/main", f"refs/heads/release/{version}"):
            with self.subTest(ref=ref):
                source.validate_dispatch("workflow_dispatch", ref, version, profile)

    def test_candidate_summary_reuses_original_package_artifacts(self):
        record = {"publication_authorized": False}
        for key, value in (("windows", "a"), ("linux", "b"), ("macos_arm64", "c"), ("macos_x86_64", "d")):
            record[key] = {"file": key, "sha256": value * 64}
        rows = downloads.download_rows(record)
        self.assertEqual({row[2] for row in rows}, {
            "nipat-windows-setup", "nipat-linux-setup", "nipat-macos-setup-arm64", "nipat-macos-setup-x86_64",
        })
        for key in ("windows", "linux", "macos_arm64", "macos_x86_64"):
            original = record[key]["sha256"]
            record[key]["sha256"] = "invalid"
            with self.subTest(platform=key), self.assertRaises(ValueError):
                downloads.download_rows(record)
            record[key]["sha256"] = original
        workflow = (Path(__file__).resolve().parents[1] / "workflows/windows-installer.yml").read_text()
        self.assertNotIn("archive: false", workflow)
        self.assertNotIn("Provide Windows as one downloadable installer", workflow)

    def test_review_build_restores_real_ubuntu_upgrade_and_requires_all_platforms(self):
        workflow = (Path(__file__).resolve().parents[1] / "workflows/windows-installer.yml").read_text()
        self.assertIn("needs: [windows-installer, linux-installer, macos-installer]", workflow)
        for verifier in ("verify_linux_dependencies.py", "verify_linux_installer.py", "verify_linux_upgrade.py",
                         "verify_installer_set.py", "verify_presentation.py", "verify_performance.py"):
            self.assertIn(verifier, workflow)
        self.assertIn("--tag v0.9.9 --kind deb --output-dir build/upgrade-baseline", workflow)
        self.assertIn("--previous-package build/upgrade-baseline/nipat-desktop_0.9.9_amd64.deb", workflow)
        self.assertIn("--macos-arm64-dir build/macos-arm64 --macos-x86-64-dir build/macos-x86_64", workflow)
        self.assertNotIn("verify_experimental_installers.py", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("${{ runner.temp }}/nipat-performance-check/", workflow)

    def test_full_build_provides_an_attempt_specific_pending_template_outside_the_evidence(self):
        import acceptance_ci
        import release_acceptance

        workflow = (Path(__file__).resolve().parents[1] / "workflows/windows-installer.yml").read_text()
        full = workflow.split("\n  installer-required:\n")[1].split("\n  macos-runtime:")[0]
        self.assertLess(full.index("name: nipat-installer-set-evidence"), full.index("scripts/release_acceptance.py"))
        self.assertIn('--run-id "$GITHUB_RUN_ID" --output build/acceptance-for-review.json', full)
        self.assertIn("name: newpat-acceptance-template-${{ github.run_attempt }}\n"
                      "          path: build/acceptance-for-review.json", full)
        self.assertIn("ACCEPTANCE_TEMPLATE_URL: ${{ steps.acceptance_template.outputs.artifact-url }}", full)
        self.assertNotIn("acceptance-for-review.json", acceptance_ci.EVIDENCE_FILES)
        record = {"version": "0.9.10", "publication_authorized": False, "source_commit": "a" * 40,
                  "installer_manifest_sha256": "b" * 64}
        for key in ("windows", "linux", "macos_arm64", "macos_x86_64", "windows_zip",
                    "windows_payload", "scientific_archive", "linux_upgrade_check"):
            record[key] = {"sha256": "c" * 64, "file": key}
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "installer-set-check.json"
            evidence.write_text(json.dumps(record), encoding="utf-8")
            pending = Path(tmp) / "acceptance-for-review.json"
            with mock.patch("sys.argv", ["release_acceptance.py", "--installer-set", str(evidence),
                                         "--run-id", "123", "--output", str(pending)]), mock.patch("builtins.print"):
                release_acceptance.main()
            template = json.loads(pending.read_text())
            self.assertEqual((template["decision"], template["publication_channel"], template["build_run_id"]),
                             ("pending", None, 123))
            self.assertEqual(template["source_commit"], record["source_commit"])
            with self.assertRaises(ValueError):
                release_acceptance.validate(template, record["version"], record["source_commit"], 123, record)
            summary = Path(tmp) / "summary.md"
            template_url = "https://github.com/example/repo/actions/runs/123/artifacts/456"
            with mock.patch.dict(os.environ, {"ACCEPTANCE_TEMPLATE_URL": template_url, "GITHUB_RUN_ID": "123",
                                              "GITHUB_RUN_ATTEMPT": "2", "GITHUB_STEP_SUMMARY": str(summary)}), \
                    mock.patch("sys.argv", ["installer_downloads.py", "--evidence", str(evidence)]):
                downloads.main()
            for item in (template_url, record["source_commit"], "build `123`, attempt `2`", "v0.9.10.json"):
                self.assertIn(item, summary.read_text())

    def test_parallel_runtime_keeps_windows_success_required_for_final_evidence(self):
        workflow = (Path(__file__).resolve().parents[1] / "workflows/windows-installer.yml").read_text()
        jobs = dict(re.findall(r"^  ([a-z][a-z-]+):\n(.*?)(?=^  [a-z][a-z-]+:\n|\Z)",
                               workflow, flags=re.MULTILINE | re.DOTALL))
        for name in ("windows-checks", "linux-runtime"):
            with self.subTest(job=name):
                header = jobs[name].split("    steps:", 1)[0]
                self.assertRegex(header, r"(?m)^    needs: release-source$")
                self.assertNotRegex(header, r"(?m)^    if:")
        self.assertNotIn("download-artifact", jobs["linux-runtime"])
        self.assertNotIn("needs.", jobs["linux-runtime"])
        windows_header = jobs["windows-installer"].split("    steps:", 1)[0]
        self.assertIn("needs: [linux-runtime, windows-checks]", windows_header)
        self.assertNotRegex(windows_header, r"(?m)^    if:")
        required = jobs["installer-required"]
        self.assertIn("needs: [windows-installer, linux-installer, macos-installer]", required)
        self.assertRegex(required, r"(?m)^    if: always\(\) && !inputs\.windows_zip_only$")
        script = re.search(r"python - <<'PY'\n(.*?)^          PY$", required,
                           flags=re.MULTILINE | re.DOTALL)[1]
        code = compile(textwrap.dedent(script), "installer-required gate", "exec")
        results = {name: {"result": "success"}
                   for name in ("windows-installer", "linux-installer", "macos-installer")}
        with mock.patch.dict(os.environ, {"CHECK_RESULTS": json.dumps(results)}):
            exec(code, {})
        for result in ("skipped", "failure", "cancelled"):
            with self.subTest(windows_result=result):
                results["windows-installer"]["result"] = result
                with mock.patch.dict(os.environ, {"CHECK_RESULTS": json.dumps(results)}), \
                        self.assertRaises(SystemExit):
                    exec(code, {})

    def test_windows_zip_review_reuses_the_offline_package_and_executes_it_before_upload(self):
        workflow = (Path(__file__).resolve().parents[1] / "workflows/windows-installer.yml").read_text()
        self.assertRegex(workflow, r"windows_zip_only:\n(?: +[^\n]*\n)*?        default: false\n        type: boolean")
        self.assertIn("  release-source:\n    if: ${{ !inputs.windows_zip_only }}", workflow)
        self.assertIn("  installer-required:\n    if: always() && !inputs.windows_zip_only", workflow)
        runtime, native = workflow.split("\n  windows-zip-runtime:\n", 1)[1].split("\n  windows-zip-review:\n")
        self.assertIn("    if: inputs.windows_zip_only\n", runtime)
        self.assertIn("if: inputs.qualify_macos_runtime", runtime)
        for step in ("*review-source", "*scientific-build", "*rootfs-build", "*export-and-stage"):
            self.assertIn(step, runtime)
        self.assertIn("include-hidden-files: true", runtime)
        self.assertIn("needs: windows-zip-runtime", native)
        self.assertIn("runs-on: windows-", native)
        self.assertLess(native.index("*review-inventory"), native.index("*review-zip"))
        self.assertLess(native.index("*review-zip"), native.index("name: newpat-windows-review-zip"))
        self.assertIn("installer/windows/zip_package.py build", workflow)
        self.assertIn("installer/windows/test-zip-package.ps1", workflow)
        for forbidden in ("nipat-installer-set-evidence", "newpat-acceptance-template", "nipat-windows-setup",
                          "continue-on-error:", "if: always()"):
            self.assertNotIn(forbidden, runtime + native)

    def test_successful_windows_zip_review_cannot_satisfy_release_acceptance(self):
        import acceptance_ci

        version = "0.9.10"
        repo = {"full_name": publisher.REPO, "id": int(publisher.REPOSITORY_ID)}
        record = {"build_run_id": 12, "source_commit": "a" * 40, "version": version}
        run = {"id": 12, "head_sha": record["source_commit"], "status": "completed",
               "conclusion": "success", "event": "workflow_dispatch",
               "path": ".github/workflows/windows-installer.yml", "repository": repo, "head_repository": repo}
        jobs = [{"name": name, "conclusion": "skipped"} for name in publisher.required_build_jobs(version)]
        jobs.extend({"name": name, "conclusion": "success"} for name in ("windows-zip-runtime", "windows-zip-review"))
        with self.assertRaisesRegex(ValueError, "Missing successful build job"):
            acceptance_ci.validate_build(record, run, jobs)
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous build evidence artifact"):
            acceptance_ci.evidence_artifact({"artifacts": [{"name": "newpat-windows-review-zip"}]}, record)

    def test_publisher_required_jobs_match_actual_workflow_display_names(self):
        workflow = (Path(__file__).resolve().parents[1] / "workflows/windows-installer.yml").read_text()
        blocks = re.findall(r"^  ([a-z][a-z-]+):\n(.*?)(?=^  [a-z][a-z-]+:\n|\Z)",
                            workflow, flags=re.MULTILINE | re.DOTALL)
        names = set()
        for identifier, body in blocks:
            display = re.search(r"^    name: (.+)$", body, re.MULTILINE)
            name = display[1] if display else identifier
            if "${{ matrix.architecture }}" in name:
                architectures = re.findall(r"^            architecture: (\S+)$", body, re.MULTILINE)
                names.update(name.replace("${{ matrix.architecture }}", value) for value in architectures)
            else:
                names.add(name)
        self.assertTrue(set(publisher.required_build_jobs("0.8.2")).issubset(names), names)


if __name__ == "__main__":
    unittest.main()
