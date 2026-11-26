"""Publish a committed acceptance after its main-branch CI succeeds."""

import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error

from acceptance_ci import read_record
from ci_changes import acceptance_only, changed_paths
from release_acceptance import explicit_publication_contract
import publish_windows_release as publisher
from scientific_reuse import fetch_json


def accepted_paths(event, revision, *, fetch=fetch_json):
    trigger = event.get("workflow_run") or {}
    run_id = trigger.get("id")
    attempt = trigger.get("run_attempt")
    publisher.require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0,
                      "Missing completed CI run or attempt")
    endpoint = f"actions/runs/{run_id}/attempts/{attempt}"
    run = fetch(endpoint)
    publisher.require(run.get("id") == run_id and run.get("run_attempt") == attempt and run.get("head_sha") == revision
                      and run.get("head_branch") == "main" and run.get("event") == "push"
                      and run.get("path") == ".github/workflows/ci.yml"
                      and (run.get("status"), run.get("conclusion")) == ("completed", "success")
                      and all(publisher.official_run_repository(run.get(field)) for field in ("repository", "head_repository")),
                      "Automatic publication requires this repository's successful main push CI")
    jobs = fetch(f"{endpoint}/jobs?per_page=100")["jobs"]
    gates = [job for job in jobs if job.get("name") == "required"]
    publisher.require(len(gates) == 1 and gates[0].get("conclusion") == "success",
                      "Automatic publication requires successful required verification")
    checks = [job for job in jobs if job.get("name") == "acceptance"]
    publisher.require(len(checks) <= 1, "Ambiguous acceptance verification")
    if not checks or checks[0].get("conclusion") == "skipped":
        return []
    publisher.require(checks[0].get("conclusion") == "success",
                      "Automatic publication requires successful acceptance verification")
    # A rebase merge can add multiple commits. GitHub binds this step's name to
    # event.before for the entire push that CI classified and verified.
    prefix = "Verified acceptance-only push from "
    markers = [step for step in checks[0].get("steps", []) if step.get("name", "").startswith(prefix)]
    if not markers or (len(markers) == 1 and markers[0].get("conclusion") == "skipped"):
        return []  # Ordinary changes and older CI runs carry no publication proof.
    publisher.require(len(markers) == 1 and markers[0].get("conclusion") == "success",
                      "Incomplete acceptance-only push verification")
    base = markers[0]["name"].removeprefix(prefix)
    publisher.require(re.fullmatch(r"[0-9a-f]{40}", base) and base != "0" * 40,
                      "Invalid acceptance-only push base")
    paths = changed_paths(base, revision)
    publisher.require(acceptance_only(paths), "Verified push range must contain only acceptance records")
    return paths


def release_channel(version, record=None):
    if explicit_publication_contract(version):
        channel = (record or {}).get("publication_channel")
        publisher.require(channel in {"stable", "testing"}, "Missing authorized publication channel")
        return publisher.publication_channel(version, channel)
    return "stable" if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) else "testing"


def validate_publication(record, run_id, source, channel):
    publisher.require(str(record["build_run_id"]) == run_id and record["source_commit"] == source
                      and release_channel(record["version"], record) == channel,
                      "Automatic publication arguments differ from the accepted record")


def existing_release(version, *, fetch=fetch_json):
    try:
        return fetch(f"releases/tags/v{version}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return None


def publication_arguments(record, existing):
    channel = release_channel(record["version"], record)
    if existing is not None and existing.get("draft") is False:
        publisher.require(existing.get("tag_name") == "v" + record["version"]
                          and existing.get("target_commitish") == record["source_commit"]
                          and existing.get("prerelease") == (channel == "testing"),
                          "An existing public release conflicts with this acceptance")
        publisher.check_tag("v" + record["version"], record["source_commit"], required=True)
        version = record["version"]
        expected = {
            "NIPAT-Setup.exe": "windows_installer_sha256",
            publisher.windows_complete_filename(version): "windows_zip_sha256",
            f"NIPAT-{version}-Windows-payload.zip": "windows_payload_sha256",
            publisher.windows_testing_filename(version): "windows_testing_sha256",
            f"nipat-desktop_{version}_amd64.deb": "linux_installer_sha256",
            f"NIPAT-{version}-macos-arm64.pkg": "macos_arm64_installer_sha256",
            f"NIPAT-{version}-macos-x86_64.pkg": "macos_x86_64_installer_sha256",
            "installer-manifest.json": "installer_manifest_sha256",
            f"nipat-scientific-runtime-{version}-amd64.tar.gz": "scientific_archive_sha256",
            "qualification-evidence.zip": "qualification_evidence_sha256",
        }
        assets = existing.get("assets") or []
        aliases = {}
        if publisher.uses_newpat_brand(version):
            aliases = {publisher.public_asset_name(name): name for name, field in expected.items()
                       if field in record and publisher.public_asset_name(name) != name}
            expected.update({alias: expected[legacy] for alias, legacy in aliases.items()})
        if publisher.requires_gui_prerelease(version):
            publisher.require("windows_testing_sha256" in record,
                              "Acceptance is missing the Windows testing entrypoint digest")
        digests = {asset["name"]: asset.get("digest") for asset in assets if asset.get("state") == "uploaded"}
        publisher.require(len(digests) == len(assets)
                          and all(digests.get(name) == "sha256:" + record[field]
                                  for name, field in expected.items() if field in record),
                          "An existing public release differs from the accepted asset bytes")
        if aliases:
            by_name = {asset["name"]: asset for asset in assets}
            for alias, legacy in aliases.items():
                size = by_name[legacy].get("size")
                publisher.require(type(size) is int and 0 < size < publisher.MAX_ASSET_BYTES
                                  and type(by_name[alias].get("size")) is int
                                  and by_name[alias]["size"] == size,
                                  "An existing NewPat alias differs from the verified legacy size")
        if publisher.requires_windows_bootstrap(version):
            # A retry must not declare success when the entry point for the
            # online setup is missing or points to another payload/source.
            publisher.require("windows_payload_sha256" in record,
                              "Acceptance is missing the desktop payload digest")
            by_name = {asset["name"]: asset for asset in assets}
            if publisher.windows_package_generation(version) == 2:
                publisher.require(not ({publisher.WINDOWS_BOOTSTRAP_UPDATE_MANIFEST,
                                        publisher.WINDOWS_ZIP_UPDATE_MANIFEST} & by_name.keys()),
                                  "An incompatible legacy Windows feed is present")
            for filename, platform, feed in (
                (f"NIPAT-{version}-Windows-payload.zip", "windows-bootstrap-x86_64",
                 publisher.windows_feed_filename("bootstrap", version)),
                (publisher.windows_complete_filename(version), "windows-zip-x86_64",
                 publisher.windows_feed_filename("zip", version)),
            ):
                asset = by_name.get(filename, {})
                size = asset.get("size")
                publisher.require(type(size) is int and 0 < size < publisher.MAX_ASSET_BYTES,
                                  "Existing payload has invalid size metadata")
                # A retry after the repository is renamed still verifies the exact
                # bytes of the original feed, including its then-canonical URLs.
                approved_digests = set()
                for repository in publisher.OFFICIAL_REPOSITORIES:
                    entry = {"platform": platform, "name": filename, "size": size,
                             "sha256": digests[filename].removeprefix("sha256:"),
                             "url": f"https://github.com/{repository}/releases/download/v{version}/{filename}"}
                    document = {
                        "schema_version": 1, "product": "nipat-desktop", "version": version,
                        "release_tag": "v" + version, "channel": channel,
                        "source_commit": record["source_commit"], "minimum_updater_version": publisher.windows_package_generation(version),
                        "assets": [entry],
                        "release_notes_url": f"https://github.com/{repository}/releases/tag/v{version}",
                    }
                    raw = (json.dumps(document, indent=2) + "\n").encode("utf-8")
                    approved_digests.add("sha256:" + hashlib.sha256(raw).hexdigest())
                publisher.require(digests.get(feed) in approved_digests,
                                  "Existing Windows update feed differs from the accepted payload")
        return None
    args = ["--operation", "prepare-and-publish", "--run-id", str(record["build_run_id"]),
            "--source-commit", record["source_commit"], "--channel", channel]
    if existing is not None:
        publisher.require(type(existing.get("id")) is int and existing["id"] > 0, "Invalid existing draft ID")
        args.extend(("--draft-release-id", str(existing["id"])))
    return args


def main():
    publisher.require(publisher.official_actions_context() and os.environ.get("GITHUB_REPOSITORY") == publisher.REPO
                      and os.environ.get("GITHUB_EVENT_NAME") == "workflow_run"
                      and os.environ.get("GITHUB_REF") == "refs/heads/main",
                      "Automatic publication must run on the owned main branch")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    revision = publisher.command("git", "rev-parse", "HEAD")
    paths = accepted_paths(event, revision)
    if not paths:
        print("No acceptance-only main change; no automatic publication requested.")
    if os.environ.get("NIPAT_ACCEPTANCE_SELECT") == "1":
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"publish={str(bool(paths)).lower()}\n")
        return
    if not paths:
        return
    # The shared publication queue can delay this run. Bind it to the record
    # still authorized on main before writing GitHub release assets.
    current = fetch_json("git/ref/heads/main")["object"]["sha"]
    publisher.require(re.fullmatch(r"[0-9a-f]{40}", current), "Missing current main revision")
    if current != revision:
        publisher.command("git", "fetch", "--no-tags", "origin", current)
    for path in sorted(paths):
        record = read_record(path, revision)
        publisher.require(publisher.source_bytes(current, path) == publisher.source_bytes(revision, path),
                          "The accepted publication record changed while queued")
        args = publication_arguments(record, existing_release(record["version"]))
        if args is None:
            print(f"Release {record['version']} is already public from the accepted source.")
        else:
            publisher.main(args)


if __name__ == "__main__":
    main()
