# Installer acceptance for research releases

Acceptance identifies a specific source commit, installer build and set of package checksums for Windows x64, Ubuntu 24.04 x86_64, macOS Intel and macOS Apple Silicon. Record automated checks, observations on actual devices and scientific domain validation separately.

## Research distribution

A pre-1.0 research release requires successful applicable CI and installer checks, matching package identities and a reviewed account of source changes and evidence. Extended desktop scenarios can be explicitly deferred. A stable release is the official distribution channel. It does not, by itself, establish fitness for any specific scientific or clinical use.

Use a successful **Installers (review build)** with a passing `installer-required` job. Build the integrated source commit or merge its release branch so that the exact built commit remains an ancestor of `main`. Collect the EXE, DEB, both PKGs, installer set evidence and scientific archive identities from the same run. Keep the build ID and checksums. See the [release procedure](../.github/RELEASE.md) for verifying and publishing the reviewed bytes.

| Schema 7 field | Evidence to record |
| --- | --- |
| `version`, `source_commit`, `build_run_id`, `publication_channel` | Candidate version, exact commit, build and intended channel. |
| `installer_manifest_sha256`, `scientific_archive_sha256` | Installer manifest and common scientific archive digests. |
| `windows_installer_sha256`, `linux_installer_sha256`, `macos_arm64_installer_sha256`, `macos_x86_64_installer_sha256` | The four installer identities. |
| `windows_zip_sha256`, `windows_payload_sha256` | The Windows complete ZIP and the payload used by the guided installation. |
| `decision`, `scope`, `review` | Reviewed `accepted-for-research` decision, `pre-1.0-research` scope, reviewer, UTC date and HTTPS evidence. |
| `observed_baseline` | Actual observed commit and evidence, labeled `historical-platform-evidence`. |
| `observed_baseline.source_comparison_scope`, `reviewed_source_changes` | `reviewed-operative-changes-with-versioned-scientific-models-v1` and ordered path plus before/after hashes, using null for additions/removals. |
| `qualification_evidence_sha256`, `linux_upgrade_check_sha256` | Permanent candidate evidence and the Ubuntu package report for the applicable release contract. |
| `macos_validation` | Separate `arm64` and `x86_64` results. Use `passed` with supporting HTTPS evidence or `not-performed` with an empty list. |
| `scientific_equivalence` | Caller reference commit, report path, report digest and immutable image ID. |
| `scientific_analysis_qualification` | Upstream NEWPAT commit, path/hash for `five-module-qualification.json` and the same immutable image ID. |
| `deferred_desktop_scenarios`, `domain_validation` | Outstanding desktop scenarios and `pending-domain-researchers` status. |

The caller report covers 17 cases against the frozen 0.8.5 DNP implementation and SNPcall 2.0 for SNP. It compares exported tables, unrounded R values and plot checks, including serial/parallel rendering. For 0.9.10 the downstream report uses frozen NEWPAT commit `c753afc4be62dfc0b81b8cb683a6e850516f5ffd`, independent analytical fixtures and explicit numerical tolerances. Its 86 R runs include 16 upstream comparisons and 54 batch runs for 2/3/5 families or samples, both marker types and serial/auto/two-worker configurations. Verify included sources, helpers, fixtures, sample identities, effective settings, preserved inputs and worker budgets. The aggregate result is in `scientific-equivalence-check.json`. The two report identities also appear in `release-provenance.json`.

Starting with 0.9.10, acceptance also verifies the archived `native-r.json` against the suite sources and scientific manifest at the build commit. A missing report, an incomplete or failed suite, or mismatched source digests blocks acceptance.

## Recording desktop tests

For each actual test record UTC time, tester, OS/build, CPU architecture, account type, initial WSL/Docker/Lima state, version, commit, package hash, commands or GUI steps, expected result and observed result. Keep installer logs, runtime state and analysis reports. Share synthetic or authorized inputs only. Review local names and paths in logs before sharing. Mark a scenario passed only after all its steps and output checks succeed.

| Scenario | Procedure and pass criteria |
| --- | --- |
| `windows_clean_wsl` | On a clean Windows 11 x64 device without configured WSL, Docker Desktop, Python or scientific tools, run the EXE, authorize prerequisites, complete any reboot and use the normal shortcut. Verify readiness, diagnostics, self-tests, six modules, composed workflows and another launch after reboot. Results and logs must be accessible from the regular account. |
| `windows_stable_coexistence` | Verify the candidate creates its own application, data, preferences and WSL registration under a fresh account. Repeat with unrelated user files present and verify their contents are intact. |
| `windows_reinstall_removal` | Use the Windows cases below. Reinstallation preserves selected paths and user files. Optional removal acts only on verified owned resources and preserves all data and runs. |
| `ubuntu_clean_dependencies` | On Ubuntu Desktop 24.04 x86_64 without Docker/Compose, install with APT. Record resolved dependencies. Arrange authorized socket access, sign back in if needed, run setup, diagnostics, self-tests and six-module workflows as the regular account. Reboot and repeat launch. Check file ownership and service access. |
| `ubuntu_existing_docker` | With a preconfigured system Docker and unrelated workloads, record before/after endpoint, versions and configuration. Preparation reuses the compatible local daemon and leaves repositories, global context and unrelated containers/images intact. |
| `ubuntu_reinstall_removal` | Save a run and sentinel file, reinstall the same DEB, repeat launch/diagnostics, and remove `newpat-desktop` with APT. Check that app and shortcut are removed while data, runs, preferences and unrelated Docker resources remain. |

Schema 1 required all six scenarios. Research records under schemas 5–7 explicitly identify deferred scenarios. An individual automated check establishes only the specific behavior it exercised.

### Windows path, repair and removal cases

Use a disposable installation with synthetic data and known sentinel files.

- Choose custom fixed-disk paths, including spaces and non-ASCII names. Verify defaults in later sessions and successful analyses. Reject overlapping roots, unsuitable system directories, UNC/network/removable locations and junctions.
- Reinstall into a recognized directory. Verify the inventory, selective backup of replaced or locally edited components, retention of unrelated files and preservation of data and results.
- Select an unrelated nonempty application directory. Verify any suggested empty child requires confirmation. A refusal, occupied child or failed check must leave existing files intact.
- Test a manually removed owned WSL registration. Setup may recreate it only in an empty verified destination; it must preserve the previous receipt and refuse an occupied location. Also verify ordinary reuse of a coherent existing registration.
- Change the WSL destination and verify a separate environment and preservation of the previous one. Change data and results destinations and confirm existing files stay in place while new runs use the new destination.
- Exercise default removal retaining runtime/cache, optional verified cleanup across current and previous recorded destinations, and cancellation before cleanup. Include an ownership/integrity failure and a partial removal failure on a test device. Check logs, remaining files and safe recovery. Confirm sentinel files, other WSL installations, Docker Desktop and user data are intact.

### Application, analyses and updates

Verify saved defaults survive reopening, run-specific overrides reach the summary and `run.json`, and new samples, CPI relationships and run names are requested each time. Exercise cancel, explicit reset, invalid preferences, missing references and a summary submitted without positive confirmation. CLI path overrides take precedence in that session; direct commands remain independent of wizard defaults. Opening help should not start diagnostics. Exercise the explicit environment check separately.

With ordinary system protections enabled, test download, setup, prerequisite elevation, launch and uninstall on Windows. Record browser, SmartScreen, Smart App Control or antivirus messages separately. On Ubuntu include private inputs readable only by the user. On every platform exercise external input locations, spaces, non-ASCII characters and custom results paths. Include a DNP-from-BAM case using an indexed FASTA, a DNP → Contamination chain, SNP, CPI and the other planned cases using known numerical outputs. Verify inputs are unchanged, runs have unique directories, existing run names are protected, and invalid/cancelled runs retain meaningful diagnostics.

For later NewPat releases, test upgrades with two identified builds of the new installation line. Record starting version, channel, proposed release, download hash and end state. Stable excludes prereleases; testing can include approved stable and testing releases. Drafts, CI artifacts, older versions and mismatched manifests must not be offered. Startup notification is initially off and, if enabled, must not download or install anything by itself. Check offline handling, corrupted or incomplete downloads, deferral and explicit confirmation. Windows and Ubuntu have separate download and install confirmations; macOS users open the verified PKG after closing the client. Check active sessions, Ubuntu APT/Polkit and terminal fallback, user data preservation, post-upgrade readiness and the runtime identity in both old and new run records.

### macOS and resource management

Record Intel and Apple Silicon separately, including OS, hardware/RAM, Lima, Rosetta where relevant and PKG digest. Test Finder installation, Gatekeeper prompts, first launch, runtime preparation, analysis, reopening, reinstall and removal. Validate original display names in results, duplicate sample basenames in different directories, `sample-map.tsv`, `run-report.html`, canonical outputs, family relationships and numerical values.

For WSL/Lima, test proposed configuration changes, cancel, backups, unrelated settings, concurrent edits, active-analysis locks and restart confirmation. WSL shutdown affects the account's distributions. Ubuntu settings should apply to NewPat containers. Distinguish a confirmed OOM from a termination of unknown cause.

## Submit the acceptance record

Open the summary of the successful full installer build and download `acceptance-for-review.json` from `newpat-acceptance-template-<attempt>`. Check that its version, source commit and run ID identify the build you reviewed. The template starts with a pending decision, an unset channel and empty review and scientific report details. Complete those entries from the evidence for this build.

If you need to regenerate the template, use the installer set from that same build:

```bash
python .github/scripts/release_acceptance.py \
  --installer-set /path/to/installer-set-check.json \
  --run-id BUILD_RUN_ID \
  --output /path/to/candidate-acceptance.json
```

Complete and review the record using evidence from the candidate. Once the source is integrated, submit `.github/release-acceptance/vVERSION.json` in a separate acceptance-only pull request. After merge, successful verification on `main` can trigger publication of that accepted build. Historical records retain their own schemas and scope. The [domain validation record](VALIDATION.md) is separate from technical release acceptance.
