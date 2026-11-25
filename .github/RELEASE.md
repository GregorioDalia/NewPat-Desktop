# Verify and publish a NewPat release

A release publishes the packages produced by a reviewed GitHub Actions installer build. The publisher checks the files again and reuses those bytes. The package set covers Windows x64, Ubuntu 24.04 x86_64, macOS Intel and macOS Apple Silicon, all tied to one Linux AMD64 scientific archive.

For a request to make a version stable, first identify the version, the intended source commit and the approved scientific scope. Integrate that source through the development PR and wait for its required checks. Use an existing successful full installer build only if it still meets the source, ancestry, artifact and evidence requirements. Otherwise dispatch one full build from the integrated commit. Complete the acceptance record with the selected `stable` channel and reviewer's evidence, then merge the acceptance-only PR. The verified publisher creates and checks the draft before publication. A stable version newer than the current **Latest** becomes the default download. These are normally two PRs across the life of the version. Once the code is integrated, only the acceptance PR remains.

## Before the 0.9.10 source is finalized

The prenatal and postnatal CPI revisions are available. The sixth analysis is still under development. Review the scientific changes in the development PR so the installer build includes the corresponding code, fixtures and user documentation.

| Delivery | Evidence to include in the source PR |
| --- | --- |
| Revised CPI workflows | Check prenatal count-only, percentage-only and combined settings. Compare the postnatal scalar, site counts and base-10 logarithm against the [upstream SNP and DNP examples](https://github.com/lpistacchia/NEWPAT/tree/97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4/CPI_postnatal/examples/outputs). Inspect the installed summary and exported tables, including a zero-site case. |
| Sixth analysis (sex estimation) | Record the script revision, required inputs, parameters, outputs and an author-confirmed synthetic example. Exercise the installed workflow and publish its expected results with the user guide. Extend the scientific qualification and its release verifier to cover the module. |

Use the [0.9.10 release notes](../docs/RELEASE_0.9.10.md) to track what the candidate actually delivers. Record the planned timing comparison on the target Mac as a post-release observation once it has run.

## Finalize documentation for each release

Close the documentation in the **source PR**, before building the intended installers.

1. Check each delivery against its reviewed example. Update the desktop and command-line guides, demo instructions, expected results and scientific catalog wherever the inputs, labels or outcomes changed.
2. Reconcile the README, documentation index, Italian first-run guide and versioned release notes with the final module set. Remove candidate-only notices and completed pending items, including any version-specific handoff above. Keep any outstanding limitation explicit. Point users to the release channel so the instructions also work after publication.
3. Confirm that examples, links and shortcuts work from the distributed files and that the notes distinguish observed results from deferred device tests.

Build this revision. The later acceptance-only PR contains just the release record.

## 1. Build the candidate

1. Check that `pyproject.toml`, the client version and release notes identify the intended version. The publisher reads `docs/RELEASE_<version>.md` for the version being prepared.
2. Run **Installers (review build)** with the default full build (`windows_zip_only` unchecked) on the reviewed commit of `main`, `release/VERSION` or a corresponding `release/VERSION-…` branch. Before starting the platform jobs, the full build checks whether changes to the distributed files are eligible for review against the observed baseline in the latest applicable acceptance record. If the reviewer has a different documented observation, enter its full commit SHA in `observed_baseline` and use that same observation in the acceptance record. Building from integrated `main` makes commit ancestry straightforward. For an already built release branch, use a merge that preserves the built commit as an ancestor of `main`. A squash or rebase may require a new build even with identical file contents.
3. Record the full source SHA, installer build run ID, workflow attempt and resulting digests. Require the successful `installer-required` check and all required platform packages. A pull request's CI artifacts cannot substitute for this installer build.

The builder checks the client, qualifies the scientific image, exports the common archive and packages files allowed by `distribution-files.txt`. It may reuse successful scientific evidence from the exact Git tree and immutable image. Without verified matching evidence it runs the scientific checks itself. [CI evidence reuse](../docs/CI_CD.md#scientific-evidence-reuse)

| Actions artifact | Contents |
| --- | --- |
| `nipat-windows-setup` | Bootstrap EXE, Windows payload and complete ZIP, manifest, checksums, `installer-build.json` and client checks. |
| `nipat-runtime-assets` | Scientific archive, WSL filesystem, manifest and checksums. |
| `nipat-linux-setup` | Ubuntu DEB and packaging, installation, dependency and upgrade reports. |
| `nipat-macos-setup-arm64`, `nipat-macos-setup-x86_64` | Native PKG and package report for each macOS architecture. |
| `nipat-scientific-check-logs` | Scientific reports and the executed/reused provenance in `reuse.json`. |
| `nipat-installer-set-evidence` | `installer-set-check.json`, which identifies the four installers together. |

### Local Windows ZIP review

To test a candidate on a Windows PC, enable `windows_zip_only` when dispatching the installer workflow on its reviewed revision. Download `newpat-windows-review-zip`, extract the complete ZIP inside it and run `1_INSTALL.cmd`. The release publisher requires the full four-platform build and its scientific and installer evidence.

### Platform evidence

- **Windows.** `windows-client-check.json` tests the staged payload with its embedded Python, including complex paths. `windows-installer-fixture-check.json` exercises installation, upgrade and removal of a fixture compiled from the candidate Inno definition. `windows-trust-check.json` binds actual Authenticode observations to package bytes. Record execution of the production setup, a real WSL installation or Smart App Control on a physical system only when observed. Bootstrap, separately downloaded payload and complete local ZIP have distinct identities.
- **Ubuntu.** Package checks cover APT installation, dependency resolution, non-root preparation and analysis, reinstall/removal, and preservation of user files. `linux-upgrade-check.json` binds a real upgrade from the 0.7.2 baseline to this candidate. A configured Actions runner and a clean physical desktop are different environments.
- **macOS.** Review native PKG, bundled Python, Lima, launcher and archive identity for each architecture. `qualify_macos_runtime` can request separate VM tests on appropriately equipped dedicated runners. Record an unexecuted architecture as `not-performed`. Checksum verification establishes file identity. It does not confer a Developer ID signature or notarization.

## 2. Review and record acceptance

The summary of a full installer build links to `newpat-acceptance-template-<attempt>`. Download `acceptance-for-review.json` for that attempt. The template records the build identity and package digests. Its decision is `pending`. A template can also be generated locally from the same build.

```bash
python .github/scripts/release_acceptance.py \
  --installer-set /path/to/installer-set-check.json \
  --run-id BUILD_RUN_ID \
  --output /path/to/acceptance-for-review.json
```

Review the platform evidence, baseline source comparison, qualified scientific reports, installer and common archive identities. Complete `.github/release-acceptance/vVERSION.json`, replacing VERSION with the actual release. Use the [installer acceptance protocol](../docs/INSTALLER_ACCEPTANCE.md) for the fields, desktop scenarios and limits of each claim. The reviewer records `accepted-for-research` and the `pre-1.0-research` scope only after reviewing the evidence. Keep deferred tests and pending domain validation visible. Historical evidence belongs to its original build.

The `publication_channel` is explicit. Use `stable` for an authorized numeric `MAJOR.MINOR.PATCH` release. Publishing an older stable keeps the newer release as GitHub **Latest**. Use `testing` for a prerelease. This choice determines discovery by clients; the scientific validation scope is described separately.

<a id="contratto-scientifico-della-0850"></a>

### Scientific evidence in schema 7

The `scientific_equivalence` and `scientific_analysis_qualification` entries each record `reference_source_commit`, `report_path`, `report_sha256` and `runtime_image`. Use the normalized paths and digests from the verified `qualification-evidence.zip`. Both reports identify the same immutable image contained in the accepted packages.

- **DNP and SNP.** The 17-case caller comparison uses frozen NIPAT 0.8.5 for DNP and the separately pinned SNPcall 2.0 source for SNP. Check exact exported tables and unrounded R results, histogram values, plot content and dimensions, and equivalent serial/parallel candidate renderings.
- **Contamination, Prenatal CPI and Postnatal CPI.** The upstream reference snapshot is `97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4`. `five-module-qualification.json` covers 86 executions, including 16 upstream comparisons and 54 batch cases across both marker types, 2/3/5 samples or families and serial, automatic and two-worker modes. Check analytical expectations, numerical tolerances, fixture and source identity, data integrity, effective settings and worker completion.
- **Distributed image.** The final image must pass native regressions for empty and zero-coverage inputs and settings, as well as the three-BAM composed workflow. A missing required R dependency, skipped required test or failed case blocks qualification. The publisher verifies sources against Git and compares report and bundle digests. Individual output/log digests describe original run bytes; path sanitization in the public evidence bundle can change those individual files.

Use `reviewed-operative-changes-with-versioned-scientific-models-v1` for the schema 7 source review. List actual before/after digests, including reviewed changes to pinned scientific sources. The caller and downstream decisions are both recorded in `scientific-equivalence-check.json` and their report hashes in `release-provenance.json`. Older accepted records retain their original schema, protected source files and equivalence rules.

## 3. Publish the accepted build

**Automatic route.** Once the source is integrated and the maintainer has authorized publication on the intended channel, merge an acceptance-only pull request to `main`. The Linux acceptance CI verifies the record and build evidence. A successful push run with `acceptance`, `required` and a verified acceptance-only change across the full push can trigger **Publish accepted release** for the recorded build/channel. Merging an accepted record can publish the build. Use the manual workflow for a mixed change or a deliberately separated draft review.

**Manual route.** Dispatch **Prepare or publish verified release** from `main`. After authorizing the release, select one of the following:

| Operation | Inputs | Outcome |
| --- | --- | --- |
| `prepare-and-publish` | Installer `run_id`, full `source_commit`, `channel`; leave `preparation_commit` empty. | Verify the packages, prepare a draft, re-read and verify its exact assets, then publish. |
| `prepare` (default) | Same build and channel inputs; leave `preparation_commit` empty. | Verify, upload a draft and report its ID and preparation commit. Review its notes, channel, commit and assets. An interrupted preparation may resume a matching `draft_release_id`. |
| `publish` | Same build/channel, exact `draft_release_id` and `preparation_commit` from the prepare summary. | Verify existing draft metadata, acceptance, files, sizes and remote digests, then publish. Missing or altered assets stop publication. |

Both routes serialize publication. Preparation uses the release notes of the preparation commit. The built source commit and preparation commit can be different. Publication preserves the verified draft notes and assets. A plain push of an application branch or tag does not authorize a release.

## Public assets and updates

The published release includes the four platform installers, Windows installation ZIP/payload, manifests, runtime archive assets, checksums and evidence. Look for `desktop-acceptance.json`, `baseline-source-check.json`, `release-provenance.json`, `linux-upgrade-check.json` and `qualification-evidence.json`/`.zip`. Public installers use NewPat names. Internal artifacts, compatibility aliases and existing clients can reference NIPAT names. Users only need the installer for their platform.

| Update feed | Consumers |
| --- | --- |
| `update-manifest-windows-bootstrap-v2.json` | Windows guided setup from 0.9.10, using bootstrap 1.2.0 and its verified release payload |
| `update-manifest-windows-zip-v2.json` | Windows complete ZIP installations from 0.9.10 |
| `update-manifest.json` | Compatible legacy Windows clients and Ubuntu |
| `update-manifest-macos.json` | Apple Silicon and Intel packages |

Clients check the release, version, source commit, channel, platform, size and SHA-256. On macOS the user closes NewPat and opens the verified PKG. Check availability of the published assets and update feeds, and verify that GitHub **Latest** resolves to the expected stable version.

Releases through 0.9.9 use `update-manifest-windows-bootstrap.json` and `update-manifest-windows-zip.json`. The first upgrade across the Windows launcher layout change requires the new installer for the same installation method. The v2 feeds are published exclusively for the English package layout.

## Maintenance

Preserve published releases, tags and accepted artifact bytes. Ship corrections as a new version. An expired artifact or rebuilt archive requires qualification of the new bytes and corresponding acceptance. Public notes should describe behavior, requirements and tested scope using generic examples. Retain necessary provenance and attribution. Keep private communications, local samples and machine-specific personal paths out of release documentation and evidence. [CI/CD guide](../docs/CI_CD.md)
