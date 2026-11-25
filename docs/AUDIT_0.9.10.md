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

The archived 0.8.99 M1 run used nine BAMs totaling 20,443,505,239 bytes and produced a 3,212,502,181-byte pileup. Its completed chromosome pileup phase took 2,318.457 seconds for 22 chromosome tasks. Indexing the pileup for the R block reader took another 237.357 seconds. Its overall run lacks a completion record. This motivated eliminating a full temporary write and read on the single-worker chromosome path. When multiple chromosomes are processed concurrently, NewPat still assembles them in BAM dictionary order. The initial candidate selected this tuning on Apple Silicon with known physical memory of at most 8 GiB and effective Lima memory of at most 4 GiB. The subsequent portability checks below describe how the current candidate selects it. The automatic cap applies to the R block pool, and explicit process limits still follow the ordinary memory and CPU checks. The original tuning preserved Windows single-experiment sizing at the tested allocations. [Mac implementation and benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac)

## Measurements and verification boundaries

The historical nine-BAM M1 worker log contains 136 completed R tasks out of 918. Between the first and 137th task starts, 47,166.5 seconds elapsed. One interval accounts for 11,131 seconds. The records capture elapsed time and do not distinguish active CPU work from sleep or other delays. A separate completed DNP and contamination run with two real BAMs on an M3 took 596.22 seconds overall, including 449.62 seconds in DNP R processing. The two machines used different memory budgets and inputs.

| Workload | Comparison | What was verified |
| --- | --- | --- |
| Export one 100,000-row table on Linux | Peak Python allocations fell from 46,689,764 to 194,417 bytes. Both runs took about 1.28 seconds. | Identical 4,188,953-byte output, SHA-256 `889c06fe9f8cfd04d532aab145fdc390c5c168bed5e688eceb072ff0fb8c80f4`. The measurement is for the presentation copy. |
| Export a 100-member synthetic ZIP on Linux | 101 catalog scans fell to one. Median wall time over three runs fell from 0.742 to 0.016 seconds. | Same member names and file bytes, aggregate content digest `e384dc9274a0c2366576c5f921d1add92c966fab8c66cae9dbfb3d37115ded07`. |
| DNP acquisition and worker selection | 24 scenarios with ordinary settings and again with the small-ARM policy flag. GNU R 4.5.0 also ran the resource-policy fixture with real worker processes on Linux. | 16 successful output scenarios matched the samtools oracle byte for byte. The other eight exercised errors or cancellation. The native resource-policy test passed 60 checks. Linux exercises the algorithm and output identity. Real elapsed time on the M1 still needs to be measured. |
| Desktop rendering | Actual service, bundled IGV, production frontend and synthetic indexed BAM. Eight screens checked at widths of 390, 768, 1,024 and 1,440 pixels with reduced motion. | Back navigation, archive/detail actions, the single primary Home action, status indicators, small-width table behavior and the original Intreccio assets. Windows taskbar and macOS Dock appearance still require native visual inspection. |

At `a771bd9` all five distributed scientific entry scripts matched 0.9.9 byte for byte. The subsequent DNP entry-script changes export block measurements and the memory estimate used for scheduling. At that review point its genotype calculations and the four other entry scripts retained their earlier behavior. The observations below describe the previous CPI models. The [candidate release notes](RELEASE_0.9.10.md) document the subsequent integration of the November 24–25 CPI revisions.

## Follow-up checks on result summaries and reference genomes

The distributed synthetic trio exercised all five modules. Starting from its three BAMs reproduced all 18 native per-locus count rows in the supplied tables. The six downstream summaries were byte-identical across the BAM and count-table paths. The desktop displayed three assigned genotypes per sample and marker, prenatal log₁₀(CPI) of 0.903 and 0.301 for the full and single-site panels, and postnatal CPI of 8 for both site selections. The mother had 4% mean contamination. The other two samples had no informative sites.

For the separate timing sample, three warm, alternating Linux AMD64 engine runs gave medians of 18.451 s in serial and 15.682 s in automatic mode with a ceiling of two workers. The first run per condition was excluded. The complete DNP and SNP call tables matched across all eight executions, including warm-up. This measures the engine using the 0.9.9 scientific image with candidate source and performance diagnostics active. The desktop timing protocol is included with the example. [Dataset and instructions (ZIP)](../examples/newpat-synthetic-trio.zip)

The human-reference qualification used the complete initial UCSC FASTAs. The hg19 archive contained 93 contigs and hg38 contained 455. Both compressed files matched UCSC's published MD5 digests. The downloader also checks independent SHA-256 pins for the archives and the decompressed FASTAs. For each assembly, a synthetic BAM with its full sequence dictionary and a two-site panel produced two heterozygous calls in each caller, each with 60 reference and 40 alternate reads. Switching assemblies failed in both directions for each caller before it returned any genotypes. In the offline desktop viewer, each matching BAM displayed the expected reads. Four sequence intervals per assembly, including a mitochondrial interval, matched samtools. [Reference sources and variants](GUI.md#choose-a-reference-genome)

## Multi-sample DNP follow-up

The comparison used the 0.9.10 candidate at `a771bd9` and its updated DNP reader and scheduler. Both ran in the released Linux AMD64 scientific userspace with R 4.4.2 and samtools 1.21. The planner saw four CPUs, 3,905 MiB and the small Apple Silicon profile. Each sample used a distinct path to the same distributed timing BAM. Both panels have 128 loci with 1,000 observations per locus. The table gives one complete DNP and SNP run per revision and sample count. It excludes desktop startup and represents this Linux setup. Hardware timings for the updated engine on the physical M1 are still outstanding.

| BAMs | Workflow before → after (s) | DNP step before → after (s) | DNP R block phase before → after (s) |
| ---: | ---: | ---: | ---: |
| 1 | 16.47 → 16.71 | 7.77 → 8.73 | 2.51 → 2.95 |
| 2 | 33.70 → 31.81 | 15.31 → 13.47 | 5.76 → 4.32 |
| 9 | 254.17 → 133.13 | 177.81 → 51.46 | 152.61 → 24.68 |

The updated reader is enabled for joint pileups. Twelve DNP-only single-BAM trials compared the readers and the previous implementation. With two R workers, median DNP time on the updated scheduler was 7.95 seconds using the experimental parser and 8.01 seconds using the established parser. The corresponding sampled process-tree peaks were 638 and 608 MiB. The final candidate therefore uses the established parser for one BAM and retains the two-worker automatic ceiling. The two- and nine-BAM timing pairs preceded this single-sample condition and exercise the same joint-pileup path. The one-BAM timing and the nine-distinct-BAM comparison were repeated on the final source.

At nine BAMs the previous engine read 984,040,560 logical bytes from the joint pileup. The updated engine read 328,013,520 bytes in 21 scheduled groups and returned 63 sample/block results. A separate DNP-only pair using the same four CPUs gave 185.80 and 55.07 seconds for the DNP step. Peak sampled proportional memory across the DNP process tree was 571.8 and 563.5 MiB, respectively. These observations do not establish the maximum resident memory on macOS. The source tree contains individual timings, affinity, hashes and the memory measurement method in `docs/validation/0.9.10-dnp-scaling.json`.

Two additional nine-BAM DNP-only comparisons isolated the changes on that CPU set. Grouping with the previous parser took 102.30 seconds. The new parser with individual reads per sample took 65.31 seconds. All four configurations produced the same native tables and genotype matrix.

All 24 native individual tables from the 1/2/9 comparison and their genotype summaries matched the prior candidate byte for byte. Nine distinct synthetic BAMs gave the expected sample-specific counts at all three loci and identical native output across revisions. The ordinary resource profile kept the same task and worker counts on the heterogeneous trio. Reader tests also covered repeated and reversed rows, overlapping windows, repeated read names, numeric contigs, malformed fields and oversized blocks.

The indexed pileup comparison used samtools 1.21 on 25 scenarios under each of two resource profiles. In a concentrated panel with six target sites and nine synthetic BAMs, median acquisition fell from about 127 to 8 ms in five Linux runs. Whole-contig and restricted scans preserved the pileup bytes across capped depth, indels and overlapping read pairs. Each interval on the historical M1 panel spans more than half of its target chromosome, so its acquisition still uses the previous scan.

The ZIP upgrade fixture now recreates the 0.9.9 launcher and keeps historical results through a failed and a successful upgrade. A desktop service integration test starts two experiments, stops and removes the first, reopens the archive and verifies that the second succeeded and both output files remain intact. That test substitutes a controlled engine command. A real Windows installation upgrade and direct visual inspection of the taskbar and macOS Dock remain final device checks. [Installed upgrade procedure](WINDOWS_INSTALLER.md#verify-an-installed-099-upgrade)

## Portable CPU and memory policy

The Windows 0.9.9 Sapienza archive records three completed DNP and contamination runs. The median workflow took 195.688 seconds, including 72.705 seconds of pileup. A separate Windows 0.9.7 experiment limited the same computer to four CPUs and 3,905 MiB. Acquisition of one BAM took 100.66 and 100.17 seconds with two samtools processes, and 186.53 and 402.97 seconds with one. The M1 high-depth comparison above measured the R phase under a similar VM allocation. These experiments inform separate decisions for acquisition, R memory and multi-sample I/O.

The current candidate was compared with `4c01a36` using the Linux AMD64 scientific userspace, four CPUs, software memory budgets and the desktop-generated environments for WSL and Lima. Each timing is one execution per condition. The 128-locus workload uses distinct input paths to copies of the distributed timing BAM. All individual SNP and DNP tables and genotype summaries matched. Nine additional BAMs with different contents also retained the expected sample-specific results. The timing data below are workflow elapsed seconds. The final two-BAM small-budget run exercised the last block-sizing change. The other measured configurations were checked for equivalent block targets on both versions of the candidate planner. [Run results, platform simulations, source hashes and test scope](https://github.com/GregorioDalia/nipat-desktop/blob/f5b837ebb0f5b2c9a1a39299e5c1aca879fb3d3d/docs/validation/0.9.10-resource-portability.json)

| Declared memory | BAMs | Prior candidate (s) | Updated candidate (s) |
|---|---:|---:|---:|
| 3,905 MiB | 1 | 16.71 | 16.07 |
| 3,905 MiB | 2 | 31.81 | 32.09 |
| 3,905 MiB | 9 | 133.13 | 133.43 |
| 8,192 MiB | 1 | 16.71 | 18.74 |
| 8,192 MiB | 2 | 23.82 | 23.56 |
| 8,192 MiB | 9 | 141.52 | 72.36 |

The earlier candidate already used shared DNP reads on the small translated profile. At 8,192 MiB, extending that path reduced the nine-BAM DNP step from 108.17 to 39.08 seconds. The WSL single-BAM simulation kept its ordinary reader and comparable scientific output. The physical M1 and Windows installation times for this revision remain unmeasured.

The planner was exercised over 756 capacity/workload combinations per policy and 672 launcher combinations per revision. The ordinary WSL plans matched their baseline across the tested range (unknown capacity or 2–32 GiB). For an eight-CPU workload with 844 loci, increasing the translated run allocation from 4,096 to 4,097 MiB now retains two R workers and 22 blocks. The earlier planner jumped to 844 blocks. With only 700 MiB declared, the conservative minimum block reduced sampled DNP process-tree PSS from 283.6 to 177.8 MiB in a Linux single-BAM test. Time increased from 10.40 to 39.03 seconds. Data and genotypes agreed. This low-memory safeguard applies across platforms.

Additional checks exercised the following cases.

- Two simulated cgroup layouts with 2 CPUs and 1 GiB now report those limits. The v1 PID allowance leaves one R worker and v2 allows two.
- Three pending desktop requests on a four-CPU, 3,905 MiB runtime received 1,301, 1,302 and 1,302 MiB of container capacity. Crash, stop, failed cleanup and waiting-job tests check that a later run cannot claim an active container's reservation. The desktop registry covers sessions of one user on the same runtime. CLI runs and other applications can consume resources outside it.
- In a mixed SNP workflow an unindexed sample ran alone and the two smaller samples overlapped. With all tables verified, the workflow took 21.48 seconds before and 18.67 seconds after. In a separate 32-sample, 3,000-locus summary test, peak traced Python allocations fell from 20,269 to 7,497 KiB. At renderer entry the live allocations fell from 16,564 to 196 KiB. The merged TSV was byte-identical. These numbers cover Python allocations only.

The local application suite for that revision passed 1,776 tests and skipped 46 platform- or dependency-specific checks. The CI helper suite passed 404 tests, all 25 native R checks passed inside the released scientific userspace, and desktop frontend checks exercised 636 assertions.

## Submitting additional experiments during calculation

The desktop now accepts new submissions while other experiments are running. A pending submission takes no worker thread until input preparation starts. A completed preparation releases its slot as soon as calculation is admitted. Each calculation can then use the resources allocated to it. The desktop and compatible engine exchange a new CPU and memory budget only after all workers from the preceding step or group of SNP samples have finished. A single indivisible step can occupy its original allocation until completion. The host accounts for the sum of allocations. The operating system retains each container's original limits.

Regression tests cover bursts and staggered submissions of 3, 5 and 13 jobs with default settings. Another test submits 104 requests, cancels one in the queue and verifies completion of the remaining 103. Waiting cards identify input preparation or CPU and memory availability. Checks in English and Italian at 800 and 1,024 pixels exercised the Activity view with two running and six waiting, including cancellation of an individual queued job.

The scientific comparison used a Linux runtime with four available CPUs, 8,192 MiB of declared capacity and four distinct synthetic BAM files per experiment. Each experiment ran one joint DNP step followed by four SNP samples. The baseline was commit `f5b837e`.

| Staggered experiments | Observed execution |
| --- | --- |
| 1 | The experiment retained the full allocation, with four concurrent SNP samples and no budget exchange. |
| 2 | After the first DNP step, each experiment had 2 CPUs and 4,096 MiB. Each processed two SNP samples concurrently. |
| 3 | After the first DNP step, the engine assigned approximately 1.33 CPUs per experiment and 2,730, 2,731 and 2,731 MiB. Each experiment processed one SNP sample at a time. Sampled process CPU counters advanced for all three within the same interval. |

Fifteen scientific tables and sample-label files per completed experiment matched the baseline byte for byte. An additional run recovered its original four CPUs and 8,192 MiB for the SNP summary after cancellation of the other experiment. When the host disappeared after the engine acknowledged a change and before the host published the new budget, the engine timed out without starting the next SNP step. SIGTERM at the same point also stopped the engine. These local runs cover scheduling and output equivalence. Timings on physical Windows and Apple Silicon systems require separate measurements.

The local application suite for that revision passed 1,789 tests, with 46 skips. The CI helper suite passed 404 tests, the native R suite passed 25 tests and the desktop frontend passed 637 assertions. The validation record identifies the exact source digests, fixtures, overlap measurements and comparisons for each scheduling scenario. [Desktop scheduling measurements](validation/0.9.10-desktop-scheduling.json)

## Cancellation, resource recovery and reopening results

The follow-up started from `c1ae3ae`. Tests reproduced the following cases through the desktop service, scientific executor and resource scheduler.

| Observed problem | Correction and verification |
| --- | --- |
| A replacement input could retain the reviewed file's size and modification time. | Compare file identity and change timestamps at submission and again when the prepared run is about to launch. A regression replaces a sample between the two checks and verifies that the job records a failure before issuing a scientific command. |
| An accepted stop at the end of input verification could be lost. During final report writing, the activity card could still accept a stop after the core had decided the outcome. A signal during assembly of the scientific index could leave a completed step inside a workflow still marked as running. | The desktop serializes cancellation and the final status decision. The engine keeps its signal handlers through publication. Tests check the JSON status, HTML index, completed outputs and pre-existing errors for SIGINT and SIGTERM. |
| A waiting experiment with explicit resource limits could leave part of the machine idle. A surviving workflow could keep a reduced quota indefinitely after another session exited with unconfirmed cleanup. | When all ready requests fit, use their recorded limits to size the next allocation. A surviving job can recover capacity after two spaced confirmations that the old container is idle. With 8 CPUs and 8,192 MiB, a local multiprocess test assigned 7 CPUs and 7,680 MiB to the original experiment and 1 CPU and 512 MiB to the capped one. |
| Reopening a job after switching results folders could select an unrelated experiment with the same directory name. A results page could keep displaying a running state after a detail dialog closed. | Resolve session jobs using the recorded results directory. The rendered desktop test opened and removed the intended job while preserving both same-named folders. Frontend tests cover the final status arriving during an open dialog. |
| A reconstructed rerun could inherit a temporary CPU allocation, and a follow-up could use changed counts or silently omit a sample whose recorded table had disappeared. | Restore the requested execution settings and bound the generated name to the desktop field length. Preparing a follow-up checks that each recorded count table exists, verifies its digest when available and inventories caller outputs once for all selected samples. Older runs with no recorded hash remain usable. |

In a separate Linux run, three DNP+SNP experiments on four distinct synthetic BAMs received CPU in the same sampling interval. For each completed experiment, 15 scientific tables and sample-label files matched the baseline byte for byte. The SNP index also avoids rereading the contents of summary files that have already been hashed. In a 128 MiB fixture its HTML remained byte-identical.

The final Linux verification passed 1,800 application tests with 46 skips, 404 CI helper tests and 25 tests with the packaged R runtime. The frontend suite passed 641 assertions. The desktop service and Chromium passed 84 interaction checks.

## Scope and how to verify

The review covered the client and desktop GUI, engine and scientific adapters, vendored entry points, operating-system launchers, update and release logic, installers, packaging inputs, performance verification and installed acceptance. Source enumeration and parsing covered complete files. Semantic review followed the jobs, inputs, calculations, cleanup, exports and installation paths listed above. A passing parser or unit test does not establish that every line or hardware-specific behavior was exercised.

The inventory below identifies the reviewed code by filename and line count. Documentation, third-party licenses, compiled third-party binaries and historical evidence are not application code. The third-party IGV distribution was checked against its pinned inventory and used in the rendered test. Third-party internals and frozen scientific reference files were not independently re-derived.

The audit used the native PowerShell parser on all 51 PowerShell scripts, GNU R on all 40 R files, the Python compiler on tracked Python, Node syntax checks on tracked JavaScript, and parsers for the package configuration, CI workflows and SVGs. Manual reading included the 62 Windows packaging/runtime files, the release gates and workflows, and the verification harnesses. The application and engine reviews paired full-file inspection with targeted reasoning and regression tests. Historical macOS measurements are kept separate from Linux test fixtures.

The installed workflow checks now compare aggregate REF/ALT values to the existing DNP and SNP fixtures and verify both expected SNP plot files. Their inventory and PDF signature checks complement the separate scientific-equivalence suite. The release pipeline's internal scientific-evidence downloader expects a new, private temporary destination; both call sites create one. A replay using the new DEB builder against a historical 0.9.9 source tree would also require its historical artwork inventory. The original tag and its published assets are preserved.

The ordinary checks are `python -m pytest tests`, `node scripts/test_gui_frontend.cjs` and `python -m unittest discover -s .github/scripts` with the official repository identity in CI. Use `scripts/verify_gui_interactions.py` for the rendered checks. The indexed-pileup qualification and the R budget fixture belong to the scientific test path. CI uses the pinned release image, including R 4.4.2. [Original audit PR #79](https://github.com/GregorioDalia/nipat-desktop/pull/79)

### File inventory

This inventory records the original audit snapshot, including comments and blank lines. Later checks on results, reference genomes and DNP performance are reported separately above. Each file appears once. Standalone test sources and frozen reference fixtures are grouped separately. Platform-specific checks shipped alongside their launchers are listed under the corresponding platform or build area. Package locks, datasets, third-party bundled JavaScript and native binaries are outside these line counts.

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

The [original file inventory](https://github.com/GregorioDalia/nipat-desktop/blob/c2b936b6d581137746b372b9bbade2318bae716c/docs/AUDIT_0.9.10.md#file-inventory) lists paths and line counts at the time of this audit.
