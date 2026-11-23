# NewPat Desktop 0.9.10 candidate audit

The starting point was the first candidate on PR #79, commit `20083fd0d7f069847366f0f17694ddad1730b5e9`. NewPat 0.9.9 is the comparison for platform behavior, scientific entry points and postnatal CPI output. This report covers the follow-up review on the development branch.

## Findings and corrections

| Component | Reproduced behavior | Correction and evidence |
| --- | --- | --- |
| Windows maintenance | Guided and ZIP installations share a layout history. Cleanup could select another installation's cache or runtime. | Limit selection to the installation being maintained and preserve foreign resources. The Windows regression sets up two ZIP layouts and a guided installation. The Testing helper also checks channel identity before adopting an existing ZIP root. See `installer/windows/test-uninstall.ps1`. |
| Windows bootstrap and Testing ZIP | A failed exclusive download could remove a pre-existing destination. The Testing ZIP could start a setup script without its imported dependency. | Only clean up a partial created by the current call. Include the dependency and verify the generated ZIP and its entry points. See `tests/test_windows_bootstrap_download.py` and `tests/test_windows_testing_package.py`. |
| Scientific job state | Cancellation during final output validation could return success. Cancellation during SNP batch plot generation could be recorded as failure. Recovery could inspect a different Lima instance from the one used by the experiment. | Preserve the interrupted state through finalization and check the recorded Lima home and instance. See `tests/test_engine_progress.py`, `tests/test_workflow_execution.py` and `tests/test_run_recovery.py`. |
| Workflow inputs | An incompatible caller/marker pairing could pass plan validation. A malformed reference to a previous output could raise an unhandled exception. | Validate both at plan preparation and exercise invalid and valid requests in `tests/test_workflow_plan.py`. |
| Result export and archive | Saving over an original output could overwrite it. A failed copy could truncate a previously exported file. Separate windows could lose a concurrent archive edit. Some unavailable imported folders could no longer be removed from the listing. | Protect originals, publish exports only after a complete write and serialize registry updates across windows. Removing an unavailable entry only updates the registry. See `tests/test_gui_app.py`, `tests/test_gui_results.py` and `tests/test_gui_lifecycle.py`. |
| Results, wizard and retry | A CLI plan with a recorded FASTA and BAMs could lack its IGV action. Changing marker branches in the wizard could fail. An incomplete HTML report could prevent retry after writing the sample map. SNP-only HTML reports could display DNP block settings. | Use the same IGV eligibility check as the service, preserve branch choices across review, allow the report write to be retried and show caller-specific settings. See `tests/test_gui_service.py`, `tests/test_five_module_client.py` and `tests/test_run_report.py`. |
| Presentation and memory | Readable table copies loaded all rows at once. PDF signature checks loaded the whole file. ZIP export rebuilt the file catalog for every member. | Stream the tables, inspect the five-byte PDF signature and resolve archive membership once per export. Check failures, original rows and final members. |
| Qualification | An empty source checksum list, or a scientific task whose start and end records were both absent, could pass their respective checks. Some non-finite telemetry values could qualify as valid measurements. Windows installed-ZIP acceptance could read preferences for the guided installation. | Validate the evidence and its expected coverage, distinguish a single-worker admission decision from an executed task, and resolve the preferences path through the installed client. See `tests/test_validation.py`, `tests/test_r_equivalence.py`, `tests/test_performance_verification.py` and `tests/test_installed_suite.py`. |
| Release package | Publication reads a version-specific release note. The first candidate did not include one. | Include the note in the distribution and update the allowed inventory for the Intreccio artwork. The change validator also originally blocked removal of the Italian launcher. The 0.9.10 transition permits deleting that legacy path and adding the English launcher, while older release contracts retain their historical inventories. The old and new repository names are exercised against the same official repository identity. |

The installed DEB qualification now requires two distinct contamination tables with the two expected sample identities. The engine-package tests check the banner actually emitted by SNPcall 2.0 when distinguishing validation before R startup from failures after startup. The worker-evidence checks associate events with the active invocation of a stage, including repeated labels with different worker counts.

The Mac review also addressed concurrent Lima startup and a Cocoa shutdown race. A request arriving during shutdown can now complete or receive an explicit closure response. The Mac runtime verifier preserves earlier reports and logs when the output directory is reused.

## Apple Silicon

Archived runs distinguish the 8 GiB M1 system with a 4-vCPU, 3,905 MiB guest from a separate M3 system. Three M1 0.9.5 suites recorded 82 completed case executions (45, 10 and 27, including repetitions and modes). The high-depth synthetic workload had three repetitions per setting. Median total time was 36.09 seconds with four automatic R workers, 27.84 seconds with two and 29.87 seconds in serial mode. The respective R-phase medians were 23.449, 15.570 and 17.550 seconds. Acquisition used one samtools worker in all three settings. These measurements isolate a meaningful difference in the R phase but cannot quantify the effect of the acquisition changes made since 0.9.5.

The archived 0.8.99 M1 run used nine BAMs totaling 20,443,505,239 bytes and produced a 3,212,502,181-byte pileup. Its completed chromosome pileup phase took 2,318.457 seconds for 22 chromosome tasks. Indexing the pileup for the R block reader took another 237.357 seconds. Its overall run lacks a completion record. This motivated eliminating a full temporary write and read on the single-worker chromosome path. When multiple chromosomes are processed concurrently, NewPat still assembles them in BAM dictionary order. The small-guest tuning applies only to Apple Silicon with known physical memory of at most 8 GiB and effective Lima memory of at most 4 GiB. The automatic cap applies to the R block pool, and explicit process limits still follow the ordinary memory and CPU checks. Windows single-experiment sizing retains the 0.9.9 policy. [Mac implementation and benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac)

## Measurements and verification boundaries

| Workload | Comparison | What was verified |
| --- | --- | --- |
| Export one 100,000-row table on Linux | Peak Python allocations fell from 46,689,764 to 194,417 bytes. Both runs took about 1.28 seconds. | Identical 4,188,953-byte output, SHA-256 `889c06fe9f8cfd04d532aab145fdc390c5c168bed5e688eceb072ff0fb8c80f4`. The measurement is for the presentation copy. |
| Export a 100-member synthetic ZIP on Linux | 101 catalog scans fell to one. Median wall time over three runs fell from 0.742 to 0.016 seconds. | Same member names and file bytes, aggregate content digest `e384dc9274a0c2366576c5f921d1add92c966fab8c66cae9dbfb3d37115ded07`. |
| DNP acquisition and worker selection | 24 scenarios with ordinary settings and again with the small-ARM policy flag. GNU R 4.5.0 also ran the resource-policy fixture with real worker processes on Linux. | 16 successful output scenarios matched the samtools oracle byte for byte. The other eight exercised errors or cancellation. The native resource-policy test passed 60 checks. Linux exercises the algorithm and output identity. Real elapsed time on the M1 still needs to be measured. |
| Desktop rendering | Actual service, bundled IGV, production frontend and synthetic indexed BAM. Eight screens checked at widths of 390, 768, 1,024 and 1,440 pixels with reduced motion. | Back navigation, archive/detail actions, the single primary Home action, status indicators, small-width table behavior and the original Intreccio assets. Windows taskbar and macOS Dock appearance still require native visual inspection. |

The five distributed scientific entry scripts match the 0.9.9 versions byte for byte. The DNP resource and acquisition changes reside in the surrounding helpers. In the desktop results view, postnatal CPI retains the 0.9.9 curve and summary behavior pending the original researcher's update. This audit does not establish a new scientific interpretation of the CPI values.

## Follow-up checks on result summaries and reference genomes

The distributed synthetic trio exercised all five modules. Starting from its three BAMs reproduced all 18 native per-locus count rows in the supplied tables. The six downstream summaries were byte-identical across the BAM and count-table paths. The desktop displayed three assigned genotypes per sample and marker, prenatal log₁₀(CPI) of 0.903 and 0.301 for the full and single-site panels, and postnatal CPI of 8 for both site selections. The mother had 4% mean contamination. The other two samples had no informative sites.

For the separate timing sample, three warm, alternating Linux AMD64 engine runs gave medians of 18.451 s in serial and 15.682 s in automatic mode with a ceiling of two workers. The first run per condition was excluded. The complete DNP and SNP call tables matched across all eight executions, including warm-up. This measures the engine using the 0.9.9 scientific image with candidate source and performance diagnostics active. The desktop timing protocol is included with the example. [Dataset and instructions](../examples/synthetic-trio/README.md)

The human-reference qualification used the complete initial UCSC FASTAs. The hg19 archive contained 93 contigs and hg38 contained 455. Both compressed files matched UCSC's published MD5 digests. The downloader also checks independent SHA-256 pins for the archives and the decompressed FASTAs. For each assembly, a synthetic BAM with its full sequence dictionary and a two-site panel produced two heterozygous calls in each caller, each with 60 reference and 40 alternate reads. Switching assemblies failed in both directions for each caller before it returned any genotypes. In the offline desktop viewer, each matching BAM displayed the expected reads. Four sequence intervals per assembly, including a mitochondrial interval, matched samtools. [Reference sources and variants](GUI.md#choose-a-reference-genome)

## Scope and how to verify

The review covered the client and desktop GUI, engine and scientific adapters, vendored entry points, operating-system launchers, update and release logic, installers, packaging inputs, performance verification and installed acceptance. Source enumeration and parsing covered complete files. Semantic review followed the jobs, inputs, calculations, cleanup, exports and installation paths listed above. A passing parser or unit test does not establish that every line or hardware-specific behavior was exercised.

The inventory below identifies the reviewed code by filename and line count. Documentation, third-party licenses, compiled third-party binaries and historical evidence are not application code. The third-party IGV distribution was checked against its pinned inventory and used in the rendered test. Third-party internals and frozen scientific reference files were not independently re-derived.

The audit used the native PowerShell parser on all 51 PowerShell scripts, GNU R on all 40 R files, the Python compiler on tracked Python, Node syntax checks on tracked JavaScript, and parsers for the package configuration, CI workflows and SVGs. Manual reading included the 62 Windows packaging/runtime files, the release gates and workflows, and the verification harnesses. The application and engine reviews paired full-file inspection with targeted reasoning and regression tests. Historical macOS measurements are kept separate from Linux test fixtures.

The installed workflow checks now compare aggregate REF/ALT values to the existing DNP and SNP fixtures and verify both expected SNP plot files. Their inventory and PDF signature checks complement the separate scientific-equivalence suite. The release pipeline's internal scientific-evidence downloader expects a new, private temporary destination; both call sites create one. A replay using the new DEB builder against a historical 0.9.9 source tree would also require its historical artwork inventory. The original tag and its published assets are preserved.

The ordinary checks are `python -m pytest tests`, `node scripts/test_gui_frontend.cjs` and `python -m unittest discover -s .github/scripts` with the official repository identity in CI. Use `scripts/verify_gui_interactions.py` for the rendered checks. The indexed-pileup qualification and the R budget fixture belong to the scientific test path. CI uses the pinned release image, including R 4.4.2. [PR #79 and its current checks](https://github.com/GregorioDalia/nipat-desktop/pull/79)
### File inventory

These are physical source lines in the candidate, including comments and blank lines. Each file appears once. Standalone test sources and frozen reference fixtures are grouped separately. Platform-specific checks shipped alongside their launchers are listed under the corresponding platform or build area. Package locks, datasets, third-party bundled JavaScript and native binaries are outside these line counts.

| Reviewed area | Files | Source lines |
| --- | ---: | ---: |
| Build, launch, configuration and supporting tools | 37 | 6,538 |
| Client, CLI and validation | 30 | 6,460 |
| Engine and scientific components | 53 | 20,742 |
| Installed acceptance and verification harnesses | 30 | 9,104 |
| Native frontend, GUI service and embedded web interface | 19 | 5,810 |
| Tests and reference fixtures (syntax/inventory, selected regression and execution tests) | 168 | 42,905 |
| Windows installation, release and CI | 91 | 17,291 |
| macOS integration and resource configuration | 14 | 2,742 |
| **Total** | **442** | **111,592** |

<details>
<summary>Build, launch, configuration and supporting tools</summary>

| File | Lines |
| --- | ---: |
| `.github/dependabot.yml` | 20 |
| `1_SETUP.cmd` | 7 |
| `2_LAUNCH.cmd` | 7 |
| `assets/branding/build_assets.py` | 50 |
| `compose.yaml` | 20 |
| `config/defaults.toml` | 13 |
| `distribution-files.txt` | 592 |
| `installer/linux/launch.py` | 462 |
| `installer/windows/test-activity-lock.ps1` | 123 |
| `installer/windows/test-bootstrap.ps1` | 334 |
| `installer/windows/test-compiled-installer.ps1` | 253 |
| `installer/windows/test-install-layout.ps1` | 348 |
| `installer/windows/test-installer-layout.ps1` | 215 |
| `installer/windows/test-launcher.ps1` | 571 |
| `installer/windows/test-maintenance.ps1` | 153 |
| `installer/windows/test-migration.ps1` | 409 |
| `installer/windows/test-native-build.ps1` | 41 |
| `installer/windows/test-packaged-client.ps1` | 101 |
| `installer/windows/test-repair-installation.ps1` | 273 |
| `installer/windows/test-runtime-image.ps1` | 69 |
| `installer/windows/test-scientific-image.ps1` | 130 |
| `installer/windows/test-self-test-hotfix.ps1` | 155 |
| `installer/windows/test-testing-install.ps1` | 163 |
| `installer/windows/test-trust-report.ps1` | 88 |
| `installer/windows/test-uninstall.ps1` | 308 |
| `installer/windows/test-update-handoff.ps1` | 337 |
| `installer/windows/test-windows-environment.ps1` | 95 |
| `installer/windows/test-zip-install.ps1` | 211 |
| `installer/windows/test-zip-package.ps1` | 29 |
| `newpat.cmd` | 4 |
| `nipat.cmd` | 4 |
| `pyproject.toml` | 64 |
| `scripts/build_linux_installer.py` | 380 |
| `scripts/distribution_support.py` | 102 |
| `scripts/scientific_worker_evidence.py` | 156 |
| `scripts/windows/test-installed-0850.ps1` | 125 |
| `scripts/windows/test-installed.ps1` | 126 |

</details>

<details>
<summary>Client, CLI and validation</summary>

| File | Lines |
| --- | ---: |
| `src/nipat/__init__.py` | 3 |
| `src/nipat/__main__.py` | 5 |
| `src/nipat/activity.py` | 146 |
| `src/nipat/adapters/__init__.py` | 1 |
| `src/nipat/adapters/panels.py` | 11 |
| `src/nipat/analysis_forms.py` | 300 |
| `src/nipat/catalog_ui.py` | 123 |
| `src/nipat/cli.py` | 562 |
| `src/nipat/distribution.py` | 18 |
| `src/nipat/errors.py` | 13 |
| `src/nipat/i18n.py` | 50 |
| `src/nipat/paths.py` | 109 |
| `src/nipat/preferences.py` | 457 |
| `src/nipat/processes.py` | 17 |
| `src/nipat/recovery_ui.py` | 83 |
| `src/nipat/resource_ui.py` | 178 |
| `src/nipat/resources.py` | 641 |
| `src/nipat/results.py` | 367 |
| `src/nipat/run_report.py` | 575 |
| `src/nipat/scientific_options.py` | 144 |
| `src/nipat/storage.py` | 125 |
| `src/nipat/terminal.py` | 379 |
| `src/nipat/validation/__init__.py` | 1 |
| `src/nipat/validation/files.py` | 13 |
| `src/nipat/validation/integrity.py` | 39 |
| `src/nipat/validation/self_test.py` | 123 |
| `src/nipat/wizard.py` | 411 |
| `src/nipat/wizard_forms.py` | 644 |
| `src/nipat/wizard_settings.py` | 433 |
| `src/nipat/workflow_forms.py` | 489 |

</details>

<details>
<summary>Engine and scientific components</summary>

| File | Lines |
| --- | ---: |
| `docker/scientific-runtime/Dockerfile` | 101 |
| `docker/scientific-runtime/verify-packages.R` | 33 |
| `engine/main.py` | 479 |
| `scientific/vendor/DNPcall/DNPcall.R` | 913 |
| `scientific/vendor/NEWPAT/CPI_from_cffDNA/cfDNA_CPI_estimator.R` | 774 |
| `scientific/vendor/NEWPAT/CPI_postnatal/Postnatal_CPI.R` | 566 |
| `scientific/vendor/NEWPAT/SNPcall/SNPcall.R` | 533 |
| `scientific/vendor/NEWPAT/contamination/detect_contamination.R` | 319 |
| `src/nipat/execution/__init__.py` | 1 |
| `src/nipat/execution/analysis_plan.py` | 245 |
| `src/nipat/execution/diagnostics.py` | 154 |
| `src/nipat/execution/mounts.py` | 103 |
| `src/nipat/execution/options.py` | 65 |
| `src/nipat/execution/performance.py` | 320 |
| `src/nipat/execution/progress.py` | 225 |
| `src/nipat/execution/recovery.py` | 194 |
| `src/nipat/execution/runner.py` | 987 |
| `src/nipat/execution/tracking.py` | 336 |
| `src/nipat/execution/workflows.py` | 852 |
| `src/nipat_scientific/__init__.py` | 1 |
| `src/nipat_scientific/catalog.py` | 227 |
| `src/nipat_scientific/catalog_data/contamination.json` | 664 |
| `src/nipat_scientific/catalog_data/cpi.json` | 1026 |
| `src/nipat_scientific/catalog_data/cpin.json` | 842 |
| `src/nipat_scientific/catalog_data/dnp-call.json` | 2114 |
| `src/nipat_scientific/catalog_data/snp-call.json` | 1414 |
| `src/nipat_scientific/contamination.py` | 116 |
| `src/nipat_scientific/cpi.py` | 209 |
| `src/nipat_scientific/cpin.py` | 155 |
| `src/nipat_scientific/dnp.py` | 149 |
| `src/nipat_scientific/dnp_blocks.R` | 470 |
| `src/nipat_scientific/dnp_pileup.py` | 567 |
| `src/nipat_scientific/errors.py` | 14 |
| `src/nipat_scientific/executor.py` | 549 |
| `src/nipat_scientific/files.py` | 301 |
| `src/nipat_scientific/outputs.py` | 500 |
| `src/nipat_scientific/panels.py` | 278 |
| `src/nipat_scientific/parallel.R` | 267 |
| `src/nipat_scientific/parallel.py` | 44 |
| `src/nipat_scientific/performance.py` | 411 |
| `src/nipat_scientific/plan.py` | 370 |
| `src/nipat_scientific/plots.R` | 183 |
| `src/nipat_scientific/presentation.R` | 163 |
| `src/nipat_scientific/presentation.py` | 395 |
| `src/nipat_scientific/progress.R` | 53 |
| `src/nipat_scientific/progress.py` | 199 |
| `src/nipat_scientific/scratch.py` | 51 |
| `src/nipat_scientific/settings.R` | 96 |
| `src/nipat_scientific/settings.py` | 197 |
| `src/nipat_scientific/settings_data.json` | 631 |
| `src/nipat_scientific/snp.py` | 298 |
| `src/nipat_scientific/snp_parallel.py` | 446 |
| `src/nipat_scientific/snp_summary.py` | 142 |

</details>

<details>
<summary>Installed acceptance and verification harnesses</summary>

| File | Lines |
| --- | ---: |
| `scripts/acceptance/bundle-manifest.json` | 9 |
| `scripts/acceptance/fixtures.json` | 147 |
| `scripts/acceptance/installed_models.py` | 412 |
| `scripts/acceptance/installed_suite.py` | 531 |
| `scripts/acceptance/installed_workflows.py` | 481 |
| `scripts/benchmark_workflows.py` | 275 |
| `scripts/test_gui_frontend.cjs` | 280 |
| `scripts/test_gui_windows_native.py` | 72 |
| `scripts/verify_caller_acquisition.py` | 119 |
| `scripts/verify_contamination_update.py` | 184 |
| `scripts/verify_cpi_engine.py` | 296 |
| `scripts/verify_cpi_update.py` | 128 |
| `scripts/verify_cpin_update.py` | 95 |
| `scripts/verify_dnp_engine.py` | 302 |
| `scripts/verify_engine_package.py` | 707 |
| `scripts/verify_five_module_workflow.py` | 264 |
| `scripts/verify_five_modules.py` | 635 |
| `scripts/verify_gui_app.py` | 67 |
| `scripts/verify_gui_distribution.py` | 95 |
| `scripts/verify_gui_interactions.py` | 547 |
| `scripts/verify_input_modes.py` | 264 |
| `scripts/verify_linux_dependencies.py` | 191 |
| `scripts/verify_linux_installer.py` | 512 |
| `scripts/verify_linux_upgrade.py` | 161 |
| `scripts/verify_performance.py` | 231 |
| `scripts/verify_presentation.py` | 262 |
| `scripts/verify_r_equivalence.py` | 730 |
| `scripts/verify_snp_example.py` | 33 |
| `scripts/verify_snp_workflow.py` | 492 |
| `scripts/verify_workflow_execution.py` | 582 |

</details>

<details>
<summary>Native frontend, GUI service and embedded web interface</summary>

| File | Lines |
| --- | ---: |
| `src/nipat/gui/__init__.py` | 1 |
| `src/nipat/gui/app.py` | 246 |
| `src/nipat/gui/diagnostics.py` | 215 |
| `src/nipat/gui/host.py` | 15 |
| `src/nipat/gui/igv.py` | 274 |
| `src/nipat/gui/jobs.py` | 388 |
| `src/nipat/gui/lifecycle.py` | 119 |
| `src/nipat/gui/linux_host.py` | 239 |
| `src/nipat/gui/plan.py` | 152 |
| `src/nipat/gui/results.py` | 1040 |
| `src/nipat/gui/server.py` | 273 |
| `src/nipat/gui/service.py` | 484 |
| `src/nipat/gui/startup.py` | 76 |
| `src/nipat/gui/web/app.js` | 775 |
| `src/nipat/gui/web/i18n.js` | 120 |
| `src/nipat/gui/web/igv-view.js` | 398 |
| `src/nipat/gui/web/index.html` | 24 |
| `src/nipat/gui/web/style.css` | 82 |
| `src/nipat/gui/windows_host.py` | 889 |

</details>

<details>
<summary>Tests and reference fixtures (syntax/inventory, selected regression and execution tests)</summary>

| File | Lines |
| --- | ---: |
| `.github/scripts/test_check_docs.py` | 77 |
| `.github/scripts/test_ci_changes.py` | 288 |
| `.github/scripts/test_ci_control.py` | 242 |
| `.github/scripts/test_component_inventory.py` | 61 |
| `.github/scripts/test_documentation_package.py` | 57 |
| `.github/scripts/test_experimental_ci.py` | 197 |
| `.github/scripts/test_five_module_acceptance.py` | 502 |
| `.github/scripts/test_installer_science_wait.py` | 119 |
| `.github/scripts/test_macos_release.py` | 113 |
| `.github/scripts/test_official_delivery.py` | 149 |
| `.github/scripts/test_publish_windows_release.py` | 1599 |
| `.github/scripts/test_qualification_evidence.py` | 213 |
| `.github/scripts/test_r_equivalence_ci.py` | 141 |
| `.github/scripts/test_release_acceptance.py` | 709 |
| `.github/scripts/test_release_handoff.py` | 362 |
| `.github/scripts/test_release_inputs.py` | 147 |
| `.github/scripts/test_revised_r_acceptance.py` | 490 |
| `.github/scripts/test_scientific_reuse.py` | 427 |
| `.github/scripts/test_scientific_reuse_workflows.py` | 182 |
| `.github/scripts/test_security_inventory.py` | 128 |
| `.github/scripts/test_update_manifest_contract.py` | 137 |
| `.github/scripts/test_verify_installer_set.py` | 537 |
| `.github/scripts/test_windows_bootstrap.py` | 96 |
| `.github/scripts/test_windows_trust.py` | 143 |
| `tests/native_r_helpers.py` | 26 |
| `tests/r_optimization/capture.R` | 126 |
| `tests/r_optimization/compare.R` | 10 |
| `tests/r_optimization/contamination/check_parallel.R` | 144 |
| `tests/r_optimization/cpi/benchmark_summary.R` | 139 |
| `tests/r_optimization/cpi/check_core.R` | 233 |
| `tests/r_optimization/dnp/benchmark_reader.R` | 123 |
| `tests/r_optimization/dnp/check_block_planning.R` | 83 |
| `tests/r_optimization/dnp/check_blocks.R` | 247 |
| `tests/r_optimization/dnp/check_parallel_blocks.R` | 264 |
| `tests/r_optimization/dnp/check_parallel_samples.R` | 226 |
| `tests/r_optimization/dnp/check_reader.R` | 80 |
| `tests/r_optimization/dnp/check_reader_ranges.R` | 119 |
| `tests/r_optimization/parallel/check_acquisition_budget.R` | 175 |
| `tests/r_optimization/parallel/check_budget.R` | 225 |
| `tests/r_optimization/performance/check_costs.R` | 105 |
| `tests/r_optimization/presentation/check_plots.R` | 56 |
| `tests/r_optimization/settings/check_callers.R` | 58 |
| `tests/r_optimization/snp/check_reads.R` | 181 |
| `tests/r_optimization/verify_dnp_cancellation.py` | 189 |
| `tests/r_optimization/verify_indexed_pileup.py` | 450 |
| `tests/reference_r/0.8.5/docker/scientific-runtime/verify-packages.R` | 33 |
| `tests/reference_r/0.8.5/scientific/vendor/DNPcall/DNPcall.R` | 831 |
| `tests/reference_r/0.8.5/scientific/vendor/NEWPAT/CPI_from_cffDNA/cfDNA_CPI_estimator.R` | 510 |
| `tests/reference_r/0.8.5/scientific/vendor/NEWPAT/SNPcall/SNPcall.R` | 156 |
| `tests/reference_r/0.8.5/scientific/vendor/NEWPAT/contamination/detect_contamination.R` | 293 |
| `tests/reference_r/0.8.5/src/nipat_scientific/presentation.R` | 147 |
| `tests/reference_r/2.0/SNPcall.R` | 644 |
| `tests/reference_r/NEWPAT_20261113/CPI_from_cffDNA/cfDNA_CPI_estimator.R` | 502 |
| `tests/reference_r/NEWPAT_20261113/CPI_postnatal/Postnatal_CPI.R` | 487 |
| `tests/reference_r/NEWPAT_20261113/contamination/detect_contamination.R` | 273 |
| `tests/snp_output_helpers.py` | 34 |
| `tests/test_activity.py` | 75 |
| `tests/test_background_processes.py` | 32 |
| `tests/test_benchmark_workflows.py` | 244 |
| `tests/test_bundled_runner.py` | 638 |
| `tests/test_cli_validation.py` | 605 |
| `tests/test_client_reliability.py` | 396 |
| `tests/test_contamination_engine.py` | 162 |
| `tests/test_contamination_workflow.py` | 91 |
| `tests/test_cpi_contamination_0850.py` | 105 |
| `tests/test_cpi_contamination_native_settings.py` | 84 |
| `tests/test_cpi_engine.py` | 288 |
| `tests/test_cpi_package_staging.py` | 71 |
| `tests/test_cpin_engine.py` | 130 |
| `tests/test_cpin_scientific.py` | 110 |
| `tests/test_desktop_payload.py` | 72 |
| `tests/test_distribution.py` | 157 |
| `tests/test_dnp_engine.py` | 316 |
| `tests/test_dnp_pileup.py` | 453 |
| `tests/test_dnp_workflow.py` | 252 |
| `tests/test_engine_package.py` | 1029 |
| `tests/test_engine_performance.py` | 250 |
| `tests/test_engine_progress.py` | 184 |
| `tests/test_execution_diagnostics.py` | 347 |
| `tests/test_execution_policy.py` | 163 |
| `tests/test_execution_progress.py` | 211 |
| `tests/test_experimental_distribution.py` | 96 |
| `tests/test_five_module_client.py` | 423 |
| `tests/test_five_module_package.py` | 70 |
| `tests/test_five_modules_qualification.py` | 255 |
| `tests/test_fixed_resource_budget.py` | 90 |
| `tests/test_gui_app.py` | 159 |
| `tests/test_gui_app_verification.py` | 73 |
| `tests/test_gui_diagnostics.py` | 250 |
| `tests/test_gui_distribution.py` | 129 |
| `tests/test_gui_frontend.py` | 22 |
| `tests/test_gui_igv.py` | 257 |
| `tests/test_gui_igv_adapter.cjs` | 190 |
| `tests/test_gui_lifecycle.py` | 319 |
| `tests/test_gui_macos_host.py` | 110 |
| `tests/test_gui_results.py` | 499 |
| `tests/test_gui_server.py` | 268 |
| `tests/test_gui_service.py` | 689 |
| `tests/test_gui_smoke.py` | 65 |
| `tests/test_gui_windows_host.py` | 136 |
| `tests/test_gui_windows_launcher.py` | 126 |
| `tests/test_input_modes.py` | 356 |
| `tests/test_input_mounts.py` | 182 |
| `tests/test_installation_client.py` | 143 |
| `tests/test_installed_models.py` | 250 |
| `tests/test_installed_suite.py` | 350 |
| `tests/test_installed_workflows.py` | 282 |
| `tests/test_installer_assets.py` | 656 |
| `tests/test_lima_transport.py` | 69 |
| `tests/test_linux_dependencies.py` | 112 |
| `tests/test_linux_installation_check.py` | 321 |
| `tests/test_linux_installer.py` | 268 |
| `tests/test_linux_launcher.py` | 522 |
| `tests/test_linux_updates.py` | 440 |
| `tests/test_linux_upgrade.py` | 35 |
| `tests/test_macos_installer.py` | 266 |
| `tests/test_macos_launcher.py` | 178 |
| `tests/test_macos_runtime.py` | 524 |
| `tests/test_native_r_caller_inputs.py` | 236 |
| `tests/test_native_r_cpin_parameters.py` | 97 |
| `tests/test_native_r_edge_cases.py` | 196 |
| `tests/test_newpat_branding.py` | 143 |
| `tests/test_panels.py` | 87 |
| `tests/test_parallel_client.py` | 169 |
| `tests/test_parallel_runtime.py` | 116 |
| `tests/test_paths.py` | 125 |
| `tests/test_performance_observer.py` | 424 |
| `tests/test_performance_options.py` | 185 |
| `tests/test_performance_verification.py` | 128 |
| `tests/test_preferences.py` | 425 |
| `tests/test_r_equivalence.py` | 453 |
| `tests/test_resource_ui.py` | 251 |
| `tests/test_resources.py` | 365 |
| `tests/test_results.py` | 548 |
| `tests/test_run_recovery.py` | 227 |
| `tests/test_run_report.py` | 326 |
| `tests/test_run_tracking.py` | 364 |
| `tests/test_runtime_component.py` | 171 |
| `tests/test_scientific_catalog.py` | 260 |
| `tests/test_scientific_outputs.py` | 237 |
| `tests/test_scientific_preflight.py` | 158 |
| `tests/test_scientific_presentation.py` | 203 |
| `tests/test_scientific_scratch.py` | 64 |
| `tests/test_scientific_settings.py` | 210 |
| `tests/test_snp_acquisition.py` | 183 |
| `tests/test_snp_engine.py` | 188 |
| `tests/test_snp_parallel.py` | 509 |
| `tests/test_snp_summary.py` | 120 |
| `tests/test_snp_workflow_execution.py` | 441 |
| `tests/test_terminal.py` | 330 |
| `tests/test_update_handoff.py` | 261 |
| `tests/test_update_ui.py` | 217 |
| `tests/test_updates.py` | 475 |
| `tests/test_validation.py` | 77 |
| `tests/test_windows_bootstrap_download.py` | 271 |
| `tests/test_windows_install_activity.py` | 43 |
| `tests/test_windows_payload.py` | 194 |
| `tests/test_windows_testing_package.py` | 85 |
| `tests/test_windows_wsl_prerequisites.py` | 128 |
| `tests/test_windows_zip.py` | 182 |
| `tests/test_wizard_guidance.py` | 275 |
| `tests/test_wizard_settings.py` | 309 |
| `tests/test_workflow_client.py` | 589 |
| `tests/test_workflow_execution.py` | 658 |
| `tests/test_workflow_five_modules.py` | 147 |
| `tests/test_workflow_plan.py` | 272 |
| `tests/test_workflow_wizard.py` | 495 |
| `tests/test_wsl_transport.py` | 358 |

</details>

<details>
<summary>Windows installation, release and CI</summary>

| File | Lines |
| --- | ---: |
| `.github/scripts/acceptance_ci.py` | 120 |
| `.github/scripts/automatic_release.py` | 187 |
| `.github/scripts/check_docs.py` | 150 |
| `.github/scripts/check_documentation_package.py` | 130 |
| `.github/scripts/check_macos.py` | 43 |
| `.github/scripts/check_native_r.py` | 39 |
| `.github/scripts/check_windows.ps1` | 53 |
| `.github/scripts/ci_changes.py` | 156 |
| `.github/scripts/ci_control.py` | 192 |
| `.github/scripts/component_inventory.py` | 93 |
| `.github/scripts/experimental_downloads.py` | 46 |
| `.github/scripts/install_inno.ps1` | 21 |
| `.github/scripts/installer_downloads.py` | 41 |
| `.github/scripts/installer_science_wait.py` | 117 |
| `.github/scripts/macos_release.py` | 112 |
| `.github/scripts/publish_windows_release.py` | 1033 |
| `.github/scripts/qualification_evidence.py` | 205 |
| `.github/scripts/release_acceptance.py` | 1310 |
| `.github/scripts/release_inputs.py` | 159 |
| `.github/scripts/scientific_reuse.py` | 625 |
| `.github/scripts/security_inventory.py` | 125 |
| `.github/scripts/verify_experimental_installers.py` | 184 |
| `.github/scripts/verify_experimental_source.py` | 29 |
| `.github/scripts/verify_installer_set.py` | 408 |
| `.github/scripts/verify_release_source.py` | 42 |
| `.github/scripts/windows-python-trust-input.json` | 163 |
| `.github/scripts/windows_bootstrap.py` | 189 |
| `.github/scripts/windows_trust.py` | 144 |
| `.github/workflows/ci.yml` | 517 |
| `.github/workflows/publish-accepted-release.yml` | 71 |
| `.github/workflows/publish-windows-release.yml` | 81 |
| `.github/workflows/security-monitoring.yml` | 61 |
| `.github/workflows/windows-installer.yml` | 816 |
| `installer/runtime/Dockerfile` | 63 |
| `installer/runtime/component.py` | 33 |
| `installer/runtime/nipat-engine` | 73 |
| `installer/runtime/write-provenance.py` | 78 |
| `installer/runtime/wsl.conf` | 11 |
| `installer/windows/ActivityNative.cs` | 74 |
| `installer/windows/EnableWsl.cs` | 121 |
| `installer/windows/EnableWsl.manifest` | 10 |
| `installer/windows/NIPAT.iss` | 1088 |
| `installer/windows/NipatLauncher.cs` | 106 |
| `installer/windows/NipatLauncher.manifest` | 11 |
| `installer/windows/activity-lock.ps1` | 146 |
| `installer/windows/bootstrap-common.ps1` | 454 |
| `installer/windows/bootstrap-migration.ps1` | 302 |
| `installer/windows/bootstrap-profile.iss` | 8 |
| `installer/windows/bootstrap.ps1` | 193 |
| `installer/windows/bootstrap_download.py` | 381 |
| `installer/windows/build-compiler.ps1` | 18 |
| `installer/windows/build-launcher.ps1` | 43 |
| `installer/windows/build-native.ps1` | 12 |
| `installer/windows/build-wsl-helper.ps1` | 13 |
| `installer/windows/collect-windows-security.ps1` | 101 |
| `installer/windows/desktop_payload.py` | 110 |
| `installer/windows/install-layout.ps1` | 369 |
| `installer/windows/install-profile.json` | 11 |
| `installer/windows/install-profile.ps1` | 101 |
| `installer/windows/install-testing.ps1` | 275 |
| `installer/windows/install-zip.ps1` | 96 |
| `installer/windows/launch.ps1` | 33 |
| `installer/windows/maintenance.ps1` | 289 |
| `installer/windows/repair-installation.ps1` | 316 |
| `installer/windows/testing-install.cmd` | 9 |
| `installer/windows/testing_package.py` | 91 |
| `installer/windows/uninstall-runtime.ps1` | 323 |
| `installer/windows/update-handoff.ps1` | 229 |
| `installer/windows/validate-install-layout.ps1` | 48 |
| `installer/windows/write-trust-report.ps1` | 149 |
| `installer/windows/zip-common.ps1` | 231 |
| `installer/windows/zip-entry.ps1` | 44 |
| `installer/windows/zip-install.cmd` | 9 |
| `installer/windows/zip_package.py` | 186 |
| `scripts/build_windows_installer_assets.py` | 539 |
| `scripts/verify_windows_payload.py` | 343 |
| `scripts/windows/common.ps1` | 180 |
| `scripts/windows/gui-launch.py` | 47 |
| `scripts/windows/repair-0850-self-test.ps1` | 123 |
| `scripts/windows/run.ps1` | 51 |
| `scripts/windows/setup.ps1` | 47 |
| `src/nipat/branding.py` | 49 |
| `src/nipat/installation.py` | 213 |
| `src/nipat/linux_update.py` | 331 |
| `src/nipat/repository.py` | 26 |
| `src/nipat/update_handoff.py` | 258 |
| `src/nipat/update_ui.py` | 163 |
| `src/nipat/updates.py` | 524 |
| `src/nipat/windows_install_activity.py` | 105 |
| `src/nipat/windows_setup_check.py` | 167 |
| `src/nipat/windows_wsl_prerequisites.py` | 205 |

</details>

<details>
<summary>macOS integration and resource configuration</summary>

| File | Lines |
| --- | ---: |
| `installer/macos/NIPAT.command` | 10 |
| `installer/macos/dependencies.json` | 36 |
| `installer/macos/launch.py` | 187 |
| `installer/macos/launcher.c` | 27 |
| `installer/macos/migrate_legacy.py` | 114 |
| `installer/macos/package-guard.c` | 81 |
| `scripts/benchmark_macos_dnp.py` | 120 |
| `scripts/build_macos_installer.py` | 371 |
| `scripts/test_gui_macos_native.py` | 6 |
| `scripts/verify_macos_package.py` | 200 |
| `scripts/verify_macos_runtime.py` | 117 |
| `src/nipat/execution/transport.py` | 252 |
| `src/nipat/gui/macos_host.py` | 580 |
| `src/nipat/macos_runtime.py` | 641 |

</details>
