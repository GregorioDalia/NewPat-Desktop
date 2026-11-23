"""Wait briefly for a matching CI producer before retrying the installer's proof lookup.

This helper only schedules another lookup. The existing verifier checks the
artifact, immutable image, Git tree and completed run before any gate is skipped.
"""

import time

import scientific_reuse as science


WAIT_SECONDS = 15 * 60
POLL_SECONDS = 30
CI_PATH = ".github/workflows/ci.yml"


def same_source_ci(run, commit):
    repo = run.get("repository") or {}
    head = run.get("head_repository") or {}
    return (run.get("path") == CI_PATH and run.get("head_sha") == commit
            and run.get("event") in {"pull_request", "push", "workflow_dispatch"}
            and run.get("status") in {"in_progress", "completed"}
            and run.get("conclusion") in {None, "success"}
            and repo.get("full_name") == head.get("full_name") == science.REPOSITORY
            and repo.get("id") == head.get("id") == int(science.REPOSITORY_ID)
            and science.positive(run.get("id")) and science.positive(run.get("run_attempt")))


def matches_pull_tree(run, source, fetch, deadline):
    # The run's head SHA identifies the PR tip. The CI checkout was its test
    # merge; a different base can change the tree even with the same head.
    attached = run.get("pull_requests") or []
    if len(attached) == 1 and science.positive(attached[0].get("number")):
        numbers = [attached[0]["number"]]
    elif not attached:
        # Actions may omit the PR association. Only consider an unambiguous,
        # same-repository PR for this commit and exact head.
        pulls = fetch(f"commits/{source['commit']}/pulls?per_page=10", deadline=deadline)
        numbers = [pr["number"] for pr in pulls if pr.get("head", {}).get("sha") == source["commit"]
                   and pr.get("head", {}).get("repo", {}).get("full_name") == science.REPOSITORY
                   and science.positive(pr.get("number"))]
    else:
        return False
    if len(numbers) != 1:
        return False
    pr = fetch(f"pulls/{numbers[0]}", deadline=deadline)
    head, base = pr["head"], pr["base"]
    merge = pr["merge_commit_sha"]
    if (pr.get("number") != numbers[0] or head["sha"] != source["commit"] or not science.sha(merge)
            or head["repo"]["full_name"] != science.REPOSITORY or base["repo"]["full_name"] != science.REPOSITORY):
        return False
    merged = fetch(f"git/commits/{merge}", deadline=deadline)
    return (merged["sha"] == merge and merged["tree"]["sha"] == source["tree"]
            and [parent["sha"] for parent in merged["parents"]] == [base["sha"], source["commit"]])


def producing(run, fetch, deadline):
    document = fetch(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100", deadline=deadline)
    jobs = document["jobs"]
    if len(jobs) != document["total_count"] or any(job.get("conclusion") not in {None, "success", "skipped"}
                                                  for job in jobs):
        return False
    matches = [job for job in jobs if job.get("name") == "scientific"]
    if len(matches) != 1:
        return False
    job = matches[0]
    if (job.get("run_id"), job.get("run_attempt"), job.get("head_sha")) != (run["id"], run["run_attempt"], run["head_sha"]):
        return False
    if job["status"] == "completed":
        science.validate_job(document, run)
        return True
    if job["status"] != "in_progress":
        return False
    steps = [step for step in job.get("steps", []) if step.get("name") in (*science.STEPS, *science.PRODUCER_STEPS)]
    return (all(step.get("conclusion") in {None, "success"} for step in steps)
            and any(step.get("status") in {"in_progress", "completed"} for step in steps))


def producer_finished(receipt, *, fetch=science.fetch_json, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + WAIT_SECONDS
    try:
        consumer = receipt["consumer"]
        if (receipt["reused"] or consumer.get("repository") != science.REPOSITORY
                or consumer.get("event") != "workflow_dispatch"
                or not consumer.get("workflow_ref", "").startswith(science.REPOSITORY + "/.github/workflows/windows-installer.yml@refs/heads/")):
            return False
        source = consumer["checkout"]
        if not science.sha(source["commit"]) or not science.sha(source["tree"]):
            return False
        checked = {miss["run_id"] for miss in receipt["candidates_checked"]}
        runs = fetch(f"actions/workflows/ci.yml/runs?head_sha={source['commit']}&per_page=10", deadline=deadline)["workflow_runs"]
        for run in runs:
            if (run.get("id") in checked or not same_source_ci(run, source["commit"])
                    or not producing(run, fetch, deadline)):
                continue
            if run["event"] == "pull_request" and not matches_pull_tree(run, source, fetch, deadline):
                continue
            run_id, attempt = run["id"], run["run_attempt"]
            print(f"Matching CI run {run_id}, attempt {attempt}, is qualifying this source. "
                  f"Waiting up to {WAIT_SECONDS // 60} minutes before running the installer checks.", flush=True)
            while run["status"] != "completed":
                remaining = deadline - clock()
                if remaining <= 0:
                    return False
                sleep(min(POLL_SECONDS, remaining))
                if clock() >= deadline:
                    return False
                run = fetch(f"actions/runs/{run_id}", deadline=deadline)
                if (not same_source_ci(run, source["commit"]) or run["id"] != run_id
                        or run["run_attempt"] != attempt or not producing(run, fetch, deadline)):
                    return False
            science.validate_run(run)
            return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        # Keep API messages and authentication details out of public logs.
        print(f"Optional wait unavailable ({type(error).__name__}). Running installer checks.", flush=True)
    return False
