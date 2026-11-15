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
    publisher.require(type(run_id) is int and run_id > 0, "Missing completed CI run")
    run = fetch(f"actions/runs/{run_id}")
    publisher.require(run.get("id") == run_id and run.get("head_sha") == revision
                      and run.get("head_branch") == "main" and run.get("event") == "push"
                      and run.get("path") == ".github/workflows/ci.yml"
                      and (run.get("status"), run.get("conclusion")) == ("completed", "success")
                      and (run.get("repository") or {}).get("full_name") == publisher.REPO
                      and (run.get("head_repository") or {}).get("full_name") == publisher.REPO,
                      "Automatic publication requires this repository's successful main push CI")
    parent = publisher.command("git", "rev-parse", f"{revision}^1")
    paths = changed_paths(parent, revision)
    if not acceptance_only(paths):
        return []
    jobs = fetch(f"actions/runs/{run_id}/jobs?per_page=100")["jobs"]
    for name in ("acceptance", "required"):
        matches = [job for job in jobs if job.get("name") == name]
        publisher.require(len(matches) == 1 and matches[0].get("conclusion") == "success",
                          f"Automatic publication requires successful {name} verification")
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
            f"NIPAT-{version}-Windows-completo.zip": "windows_zip_sha256",
            f"NIPAT-{version}-Windows-payload.zip": "windows_payload_sha256",
            f"nipat-desktop_{version}_amd64.deb": "linux_installer_sha256",
            f"NIPAT-{version}-macos-arm64.pkg": "macos_arm64_installer_sha256",
            f"NIPAT-{version}-macos-x86_64.pkg": "macos_x86_64_installer_sha256",
            "installer-manifest.json": "installer_manifest_sha256",
            f"nipat-scientific-runtime-{version}-amd64.tar.gz": "scientific_archive_sha256",
            "qualification-evidence.zip": "qualification_evidence_sha256",
        }
        assets = existing.get("assets") or []
        digests = {asset["name"]: asset.get("digest") for asset in assets if asset.get("state") == "uploaded"}
        publisher.require(len(digests) == len(assets)
                          and all(digests.get(name) == "sha256:" + record[field]
                                  for name, field in expected.items() if field in record),
                          "An existing public release differs from the accepted asset bytes")
        if publisher.requires_windows_bootstrap(version):
            # A retry must not declare success when the entry point for the
            # online setup is missing or points to another payload/source.
            publisher.require("windows_payload_sha256" in record,
                              "Acceptance is missing the desktop payload digest")
            by_name = {asset["name"]: asset for asset in assets}
            for filename, platform, feed in (
                (f"NIPAT-{version}-Windows-payload.zip", "windows-bootstrap-x86_64",
                 publisher.WINDOWS_BOOTSTRAP_UPDATE_MANIFEST),
                (f"NIPAT-{version}-Windows-completo.zip", "windows-zip-x86_64",
                 publisher.WINDOWS_ZIP_UPDATE_MANIFEST),
            ):
                asset = by_name.get(filename, {})
                size = asset.get("size")
                publisher.require(type(size) is int and 0 < size < publisher.MAX_ASSET_BYTES,
                                  "Existing payload has invalid size metadata")
                entry = {"platform": platform, "name": filename, "size": size,
                         "sha256": digests[filename].removeprefix("sha256:"),
                         "url": f"https://github.com/{publisher.REPO}/releases/download/v{version}/{filename}"}
                document = {
                    "schema_version": 1, "product": "nipat-desktop", "version": version,
                    "release_tag": "v" + version, "channel": channel,
                    "source_commit": record["source_commit"], "minimum_updater_version": 1,
                    "assets": [entry],
                    "release_notes_url": f"https://github.com/{publisher.REPO}/releases/tag/v{version}",
                }
                raw = (json.dumps(document, indent=2) + "\n").encode("utf-8")
                publisher.require(digests.get(feed) == "sha256:" + hashlib.sha256(raw).hexdigest(),
                                  "Existing Windows update feed differs from the accepted payload")
        return None
    args = ["--operation", "prepare-and-publish", "--run-id", str(record["build_run_id"]),
            "--source-commit", record["source_commit"], "--channel", channel]
    if existing is not None:
        publisher.require(type(existing.get("id")) is int and existing["id"] > 0, "Invalid existing draft ID")
        args.extend(("--draft-release-id", str(existing["id"])))
    return args


def main():
    publisher.require(os.environ.get("GITHUB_REPOSITORY") == publisher.REPO
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
