import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import installer_science_wait as wait


class InstallerWaitTests(unittest.TestCase):
    def setUp(self):
        self.source = {"commit": "1" * 40, "tree": "2" * 40}
        self.repo = {"full_name": wait.science.REPOSITORY, "id": 111}
        self.run = {"path": wait.CI_PATH, "id": 123, "run_attempt": 2, "head_sha": self.source["commit"],
                    "event": "push", "repository": self.repo, "head_repository": self.repo,
                    "status": "in_progress", "conclusion": None, "pull_requests": []}
        self.job = {"id": 55, "name": "scientific", "run_id": 123, "run_attempt": 2,
                    "head_sha": self.source["commit"], "status": "in_progress", "conclusion": None,
                    "steps": [{"name": wait.science.STEPS[0], "status": "in_progress", "conclusion": None}]}
        self.pr = {"number": 77, "base": {"sha": "3" * 40, "repo": self.repo},
                   "head": {"sha": self.source["commit"], "repo": self.repo}, "merge_commit_sha": "4" * 40}
        self.commit = {"sha": self.pr["merge_commit_sha"], "parents": [
            {"sha": self.pr["base"]["sha"]}, {"sha": self.source["commit"]}], "tree": {"sha": self.source["tree"]}}
        self.receipt = {"reused": False, "consumer": {"checkout": self.source, "repository": wait.science.REPOSITORY,
                        "event": "workflow_dispatch", "workflow_ref":
                        wait.science.REPOSITORY + "/.github/workflows/windows-installer.yml@refs/heads/main"},
                        "candidates_checked": []}
        self.elapsed = 0
        self.transition = self.complete

    def complete(self):
        for obj in [self.run, self.job]:
            obj.update(status="completed", conclusion="success")
        self.job["steps"] = [{"name": n, "status": "completed", "conclusion": "success"}
                             for n in (*wait.science.STEPS, *wait.science.PRODUCER_STEPS)]

    def fetch(self, path, *, deadline):
        self.assertEqual(deadline, wait.WAIT_SECONDS)
        if path == f"actions/workflows/ci.yml/runs?head_sha={self.source['commit']}&per_page=10":
            return {"workflow_runs": [copy.deepcopy(self.run)]}
        if path == "actions/runs/123/attempts/2/jobs?per_page=100":
            return {"total_count": 1, "jobs": [self.job]}
        if path == "actions/runs/123":
            return self.run
        if path == f"commits/{self.source['commit']}/pulls?per_page=10":
            return [self.pr]
        if path == "pulls/77":
            return self.pr
        if path == f"git/commits/{self.pr['merge_commit_sha']}":
            return self.commit
        self.fail(path)

    def sleep(self, seconds):
        self.elapsed += seconds
        self.transition()

    def poll(self, fetch=None):
        return wait.producer_finished(self.receipt, fetch=fetch or self.fetch, clock=lambda: self.elapsed, sleep=self.sleep)

    def test_finished_match_retries_full_verifier(self):
        self.assertTrue(self.poll())
        self.assertEqual(self.elapsed, wait.POLL_SECONDS)

    def test_exact_pr_merge_tree_with_missing_actions_association(self):
        self.run["event"] = "pull_request"
        self.assertTrue(self.poll())

    def test_unrelated_or_skipped_ci_never_waits(self):
        for target, changes in [
            (self.run, {"head_sha": "e" * 40}), (self.run, {"path": ".github/workflows/fake.yml"}),
            (self.run, {"head_repository": {"id": 10, "full_name": "other/fork"}}),
            (self.job, {"status": "completed", "conclusion": "skipped"}),
            (self.job, {"steps": []}), (self.job, {"run_attempt": 1}),
            (self.receipt, {"candidates_checked": [{"run_id": 123}]}),
            (self.receipt, {"reused": True}),
        ]:
            with self.subTest(changes=changes), patch.dict(target, changes):
                self.assertFalse(self.poll())
                self.assertEqual(self.elapsed, 0)

    def test_incompatible_pr_base_does_not_wait(self):
        self.run.update(event="pull_request", pull_requests=[{"number": 77}])
        self.commit["tree"]["sha"] = "a" * 40
        self.assertFalse(self.poll())
        self.assertEqual(self.elapsed, 0)

    def test_cancelled_restarted_or_reused_without_producing_falls_back(self):
        for transition in [lambda: self.run.update(status="completed", conclusion="cancelled"),
                           lambda: self.run.update(run_attempt=3),
                           lambda: self.job["steps"][0].update(status="completed", conclusion="skipped")]:
            with self.subTest(transition=transition), patch.dict(self.run):
                self.transition = transition
                self.elapsed = 0
                self.assertFalse(self.poll())
                self.assertEqual(self.elapsed, wait.POLL_SECONDS)

    def test_bounded_wait_and_api_error(self):
        self.transition = lambda: None
        self.assertFalse(self.poll())
        self.assertEqual(self.elapsed, wait.WAIT_SECONDS)
        self.assertFalse(self.poll(Mock(side_effect=OSError())))
        self.assertFalse(self.poll(Mock(return_value=None)))

    def test_installer_cli_only_outputs_a_validated_decision(self):
        rejected = {"reused": False, "reason": "No accepted proof"}
        accepted = {"reused": True, "reason": "Evidence accepted", "producer": {"run_id": 123, "attempt": 2},
                    "scientific_job_id": 55, "artifact": {"digest": "test"}}
        for outcomes, finished in [([accepted], False), ([rejected], False),
                                   ([rejected, accepted], True), ([rejected, rejected], True)]:
            with self.subTest(outcomes=outcomes), TemporaryDirectory() as temp:
                result = Path(temp) / "output"
                argv = ["scientific_reuse.py", "restore", "--image", "image", "--output-dir", temp,
                        "--output", str(result), "--runner-temp", temp, "--wait-for-active-ci"]
                with patch("sys.argv", argv), patch.object(wait, "producer_finished", return_value=finished) as poll, \
                        patch.object(wait.science, "restore", side_effect=outcomes) as restore:
                    wait.science.main()
                self.assertEqual(poll.call_count, int(not outcomes[0]["reused"]))
                self.assertEqual(restore.call_count, len(outcomes))
                self.assertEqual(result.read_text().splitlines(), ["reused=" + str(outcomes[-1]["reused"]).lower()])
