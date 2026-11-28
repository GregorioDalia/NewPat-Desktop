import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("ci_control", Path(__file__).with_name("ci_control.py"))
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)

REPOSITORY = "example/newpat"
HEAD = "a" * 40
EVENT = {"repository": {"default_branch": "main"}}


class CheckOwnership(unittest.TestCase):
    def pull(self):
        return {"number": 42, "state": "open", "head": {
            "sha": HEAD, "ref": "feature/new", "repo": {"full_name": REPOSITORY},
        }}

    def workflow_run(self):
        return {"event": "pull_request", "head_sha": HEAD, "status": "in_progress",
                "conclusion": None, "pull_requests": [{"number": 42}]}

    def decision(self, pulls, *, name="push", ref="refs/heads/feature/new", runs=None):
        runs = {"workflow_runs": [self.workflow_run()]} if runs is None else runs
        return control.check_ownership(name, EVENT, REPOSITORY, ref, HEAD, lambda *_: pulls, lambda *_: runs)

    def test_matching_open_pr_owns_branch_push(self):
        run, duplicate, _ = self.decision([self.pull()])
        self.assertFalse(run)
        self.assertEqual(duplicate, "42")

    def test_different_commit_fork_branch_or_closed_pr_never_suppresses_checks(self):
        alternatives = [self.pull() for _ in range(5)]
        alternatives[0]["head"]["sha"] = "b" * 40
        alternatives[1]["head"]["repo"]["full_name"] = "another/newpat"
        alternatives[2]["head"]["ref"] = "different"
        alternatives[3]["state"] = "closed"
        alternatives[4]["number"] = "42"
        for pull in alternatives:
            with self.subTest(pull=pull):
                self.assertTrue(self.decision([pull])[0])

    def test_pr_draft_main_and_manual_always_run_without_api_lookup(self):
        for name, ref in (("pull_request", "refs/pull/42/merge"), ("push", "refs/heads/main"),
                          ("workflow_dispatch", "refs/heads/feature/new")):
            with self.subTest(event=name, ref=ref):
                fetch = Mock(side_effect=AssertionError("must not query"))
                self.assertTrue(control.check_ownership(name, {**EVENT, "pull_request": {"draft": True}},
                                                       REPOSITORY, ref, HEAD, fetch, fetch)[0])
                fetch.assert_not_called()

    def test_missing_or_invalid_api_response_preserves_coverage(self):
        for response in ([], None, {}, [None], [{"head": None}]):
            with self.subTest(response=response):
                self.assertTrue(self.decision(response)[0])
        self.assertTrue(control.check_ownership("push", EVENT, REPOSITORY, "refs/heads/feature/new", HEAD,
                                               Mock(side_effect=OSError("API unavailable")), Mock())[0])

    def test_missing_default_branch_never_delegates(self):
        self.assertTrue(control.check_ownership("push", {}, REPOSITORY, "refs/heads/feature/new", HEAD,
                                               Mock(return_value=[self.pull()]), Mock())[0])

    def test_open_pr_without_observed_run_keeps_push_coverage(self):
        self.assertTrue(self.decision([self.pull()], runs={"workflow_runs": []})[0])
        self.assertTrue(control.check_ownership("push", EVENT, REPOSITORY, "refs/heads/feature/new", HEAD,
                                               Mock(return_value=[self.pull()]),
                                               Mock(side_effect=OSError("Actions API unavailable")))[0])

    def test_canceled_unrelated_or_skipped_runs_never_replace_push_checks(self):
        alternatives = [self.workflow_run() for _ in range(7)]
        alternatives[0].update(status="completed", conclusion="cancelled")
        alternatives[1].update(status="completed", conclusion="skipped")
        alternatives[2]["head_sha"] = "b" * 40
        alternatives[3]["event"] = "push"
        alternatives[4]["pull_requests"] = [{"number": 43}]
        alternatives[5]["pull_requests"] = []
        alternatives[6]["status"] = "unknown"
        for run in alternatives:
            with self.subTest(run=run):
                self.assertTrue(self.decision([self.pull()], runs={"workflow_runs": [run]})[0])

    def test_observed_success_or_failure_is_owned_by_pr_required_gate(self):
        for status, conclusion in (("queued", None), ("in_progress", None),
                                   ("completed", "success"), ("completed", "failure")):
            run = self.workflow_run()
            run.update(status=status, conclusion=conclusion)
            self.assertFalse(self.decision([self.pull()], runs={"workflow_runs": [run]})[0])


class RequiredGate(unittest.TestCase):
    def results(self, scientific="true"):
        return {
            "changes": {"result": "success", "outputs": {"run_checks": "true", "scientific": scientific,
                        "desktop_scope": "standard", "caller_smoke": "false",
                        "runtime": scientific, "packaging": scientific, "acceptance_only": "false",
                        "acceptance_paths": "[]", "documentation_scope": "none", "client": scientific}},
            "documentation": {"result": "skipped"}, "caller-smoke": {"result": "skipped"},
            "linux-checks": {"result": "success"}, "windows-checks": {"result": "success"},
            "macos-checks": {"result": "success"}, "acceptance": {"result": "skipped"},
            "scientific": {"result": "success" if scientific == "true" else "skipped"},
            "runtime": {"result": "success" if scientific == "true" else "skipped"},
            "packaging": {"result": "success" if scientific == "true" else "skipped"},
        }

    def errors(self, results, event="pull_request", ref="refs/pull/42/merge"):
        return control.gate_errors(results, event_name=event, ref=ref)

    def test_full_and_documentation_only_success(self):
        self.assertEqual(self.errors(self.results()), [])
        self.assertEqual(self.errors(self.results("false")), [])

    def test_acceptance_only_requires_its_validator_and_skips_clients(self):
        results = self.results("false")
        results["changes"]["outputs"].update(acceptance_only="true", client="false",
                                             acceptance_paths='[".github/release-acceptance/v0.9.7.json"]')
        for job in ("linux-checks", "windows-checks", "macos-checks"):
            results[job]["result"] = "skipped"
        results["acceptance"]["result"] = "success"
        self.assertEqual(self.errors(results), [])
        for state in ("failure", "cancelled", "skipped", None):
            results["acceptance"]["result"] = state
            self.assertTrue(self.errors(results))
        results["acceptance"]["result"] = "success"
        results["changes"]["outputs"]["scientific"] = "true"
        self.assertTrue(self.errors(results))

    def test_invalid_metadata_flag_or_missing_acceptance_job_cannot_pass(self):
        results = self.results()
        results["changes"]["outputs"]["acceptance_only"] = "unknown"
        self.assertTrue(self.errors(results))
        results = self.results()
        del results["acceptance"]
        self.assertTrue(self.errors(results))

    def test_documentation_job_must_pass_and_native_jobs_must_skip_for_guides(self):
        results = self.results("false")
        results["changes"]["outputs"]["documentation_scope"] = "guides"
        for job in ("linux-checks", "windows-checks", "macos-checks"):
            results[job]["result"] = "skipped"
        results["documentation"]["result"] = "success"
        self.assertEqual(self.errors(results), [])
        self.assertTrue(self.errors(results, "workflow_dispatch", "refs/heads/main"))
        for outcome in ("skipped", "failure", "cancelled", None):
            results["documentation"]["result"] = outcome
            self.assertTrue(self.errors(results))
        del results["documentation"]
        self.assertTrue(self.errors(results))

    def test_mixed_application_and_acceptance_request_both_validations(self):
        results = self.results()
        results["changes"]["outputs"]["acceptance_paths"] = '[".github/release-acceptance/v0.9.7.json"]'
        self.assertTrue(self.errors(results))
        results["acceptance"]["result"] = "success"
        self.assertEqual(self.errors(results), [])
        results["linux-checks"]["result"] = "skipped"
        self.assertTrue(self.errors(results))

    def test_records_with_guides_or_image_notices_require_every_selected_job(self):
        for scope in ("guides", "image"):
            results = self.results("false")
            outputs = results["changes"]["outputs"]
            outputs.update(documentation_scope=scope,
                           acceptance_paths='[".github/release-acceptance/v0.9.7.json"]')
            for job in ("linux-checks", "windows-checks", "macos-checks"):
                results[job]["result"] = "skipped"
            required = ["documentation", "acceptance"]
            if scope == "image":
                outputs["scientific"] = "true"
                required.append("scientific")
            for job in required:
                results[job]["result"] = "success"
            self.assertEqual(self.errors(results, "push", "refs/heads/main"), [])
            for job in required:
                for state in ("skipped", "failure", "cancelled", None):
                    broken = copy.deepcopy(results)
                    broken[job]["result"] = state
                    self.assertTrue(self.errors(broken), (scope, job, state))
            outputs["acceptance_only"] = "true"
            self.assertTrue(self.errors(results, "push", "refs/heads/main"))

    def test_image_notices_cannot_pass_without_both_documentation_and_science(self):
        results = self.results("false")
        outputs = results["changes"]["outputs"]
        outputs.update(documentation_scope="image", scientific="true")
        for job in ("linux-checks", "windows-checks", "macos-checks"):
            results[job]["result"] = "skipped"
        results["documentation"]["result"] = "success"
        self.assertTrue(self.errors(results))
        results["scientific"]["result"] = "success"
        self.assertEqual(self.errors(results), [])
        results["documentation"]["result"] = "failure"
        self.assertTrue(self.errors(results))
        results["documentation"]["result"] = "success"
        outputs["scientific"] = "false"
        results["scientific"]["result"] = "skipped"
        self.assertTrue(self.errors(results))

    def test_failed_cancelled_skipped_or_missing_required_jobs_fail_closed(self):
        for name in ("changes", "linux-checks", "windows-checks", "macos-checks", "scientific", "runtime", "packaging"):
            for result in ("failure", "cancelled", "skipped", None):
                with self.subTest(job=name, result=result):
                    results = self.results()
                    results[name]["result"] = result
                    self.assertTrue(self.errors(results))
            results = self.results()
            del results[name]
            self.assertTrue(self.errors(results))

    def test_unknown_selection_fails_closed(self):
        for field in ("run_checks", "scientific", "runtime", "packaging", "documentation_scope",
                      "acceptance_only", "acceptance_paths", "desktop_scope", "caller_smoke", "client"):
            for value in (None, "", "unexpected"):
                results = self.results()
                results["changes"]["outputs"][field] = value
                self.assertTrue(self.errors(results))

    def test_focused_caller_and_native_checks_are_required_on_pr_and_main(self):
        for event, ref in (("pull_request", "refs/pull/42/merge"), ("push", "refs/heads/main")):
            results = self.results("false")
            outputs = results["changes"]["outputs"]
            outputs.update(desktop_scope="focused", caller_smoke="true", client="true")
            self.assertTrue(self.errors(results, event, ref))
            results["caller-smoke"]["result"] = "success"
            self.assertEqual(self.errors(results, event, ref), [])
            for job in ("caller-smoke", "windows-checks", "macos-checks", "linux-checks"):
                for state in ("skipped", "cancelled", "failure", None):
                    broken = copy.deepcopy(results)
                    broken[job]["result"] = state
                    self.assertTrue(self.errors(broken, event, ref), (job, state))
            outputs.update(packaging="true")
            results["packaging"]["result"] = "success"
            self.assertTrue(self.errors(results, event, ref))
            outputs.update(desktop_scope="standard")
            self.assertEqual(self.errors(results, event, ref), [])
            outputs.update(scientific="true")
            results["scientific"]["result"] = "success"
            self.assertTrue(self.errors(results, event, ref))

    def test_presentation_and_manual_scopes_cannot_hide_failed_checks(self):
        results = self.results("false")
        results["changes"]["outputs"].update(desktop_scope="focused", client="true")
        self.assertEqual(self.errors(results), [])
        self.assertTrue(self.errors(results, "workflow_dispatch", "refs/heads/main"))
        del results["caller-smoke"]
        self.assertTrue(self.errors(results))
        results = self.results()
        self.assertEqual(self.errors(results, "workflow_dispatch", "refs/heads/main"), [])
        results["changes"]["outputs"]["runtime"] = "false"
        results["runtime"]["result"] = "skipped"
        self.assertTrue(self.errors(results, "workflow_dispatch", "refs/heads/main"))

    def test_workflow_preserves_each_main_push_and_requires_the_smoke(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
        self.assertIn("group: ci-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}", workflow)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", workflow)
        self.assertIn("github.event.pull_request.base.sha || github.event.before", workflow)
        self.assertIn("CI_HEAD: ${{ steps.source.outputs.source_commit }}", workflow)
        self.assertIn("caller-smoke", workflow.split("\n  required:\n", 1)[1].split("runs-on:", 1)[0])
        for name in ("scientific", "caller-smoke"):
            job = workflow.split(f"\n  {name}:\n", 1)[1].split("\n  runtime:\n", 1)[0].split("\n  caller-smoke:", 1)[0]
            smoke_step, = [step for step in job.split("      - name: ") if "verify_caller_smoke.py" in step]
            self.assertIn('run: python .github/scripts/verify_caller_smoke.py --image "$NEWPAT_RUNTIME_IMAGE"', smoke_step)
            self.assertNotIn("continue-on-error:", smoke_step)
            self.assertNotIn("        if:", smoke_step)
        self.assertIn("needs.changes.outputs.caller_smoke == 'true'", workflow)

    def test_linux_coverage_steps_require_their_producers(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
        linux = workflow.split("\n  linux-checks:\n", 1)[1].split("\n  windows-checks:\n", 1)[0]
        steps = linux.split("      - name: ")
        tests, = [step for step in steps if "coverage run -m pytest" in step]
        reports, = [step for step in steps if "coverage json" in step]
        upload, = [step for step in steps if "name: newpat-python-quality" in step]
        self.assertIn("id: python_tests", tests)
        self.assertIn("id: coverage_reports", reports)
        self.assertIn("if: ${{ !cancelled() && (steps.python_tests.outcome == 'success' || "
                      "(steps.python_tests.outcome == 'failure' && hashFiles('.coverage') != '')) }}", reports)
        self.assertIn("if: ${{ !cancelled() && steps.coverage_reports.outcome == 'success' }}", upload)
        self.assertIn("if-no-files-found: error", upload)

    def test_documentation_selection_does_not_hide_an_unexpected_scientific_result(self):
        results = self.results("false")
        results["scientific"]["result"] = "failure"
        self.assertTrue(self.errors(results))

    def test_only_branch_context_may_report_delegation(self):
        results = self.results()
        results["changes"]["outputs"].update(run_checks="false", duplicate_pr="42")
        for name in ("linux-checks", "windows-checks", "macos-checks", "scientific", "runtime", "packaging", "acceptance"):
            results[name]["result"] = "skipped"
        self.assertEqual(self.errors(results, "push", "refs/heads/feature/new"), [])
        self.assertTrue(self.errors(results))
        self.assertTrue(self.errors(results, "push", "refs/heads/main"))
        for invalid in ("", "0", "not-a-pr"):
            broken = copy.deepcopy(results)
            broken["changes"]["outputs"]["duplicate_pr"] = invalid
            self.assertTrue(self.errors(broken, "push", "refs/heads/feature/new"))


class SourceIdentity(unittest.TestCase):
    def test_checkout_and_branch_head_are_not_conflated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
            git("init", "-q")
            git("config", "user.name", "CI source test")
            git("config", "user.email", "ci-source@example.invalid")
            (root / "input.txt").write_text("source\n", encoding="utf-8")
            git("add", "input.txt")
            git("commit", "-qm", "source")
            with patch.dict(os.environ, {"GITHUB_SHA": "e" * 40}):
                record = control.source_record("pull_request", {"pull_request": {"head": {"sha": HEAD}}},
                                               repository=root)
            self.assertEqual(record["source_commit"], git("rev-parse", "HEAD"))
            self.assertEqual(record["source_tree"], git("rev-parse", "HEAD^{tree}"))
            self.assertEqual(record["pull_request_head"], HEAD)
            self.assertEqual(record["event_sha"], "e" * 40)
            self.assertNotEqual(record["source_commit"], record["pull_request_head"])


if __name__ == "__main__":
    unittest.main()
