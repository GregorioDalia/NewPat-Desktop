# NewPat 0.9.5 Testing

NewPat is the public name of the application previously distributed as NIPAT Desktop. These notes were prepared for research distribution on the **Testing** channel after the CI checks below passed. At the time of writing, the final installers still required a build and verification before publication. NIPAT 0.8.99 was the stable release. Packages and release evidence are listed under [Releases](https://github.com/GregorioDalia/nipat-desktop/releases).

## Experiments and messages

- **New experiment** opens an empty draft and restores saved preferences. It clears the previous name, files, samples, families, summary and errors. A late response to an earlier request must leave the new draft empty.
- **Rerun** and **Prepare analysis** explicitly reuse relevant settings and inputs. Each execution creates a new run.
- Validation errors display their explanations, including errors from the scientific engine.
- IGV distinguishes a missing reference, unloaded samples, an overly broad region and incompatible files. For a chromosome length mismatch it shows the files and the lengths compared. It rejects the incompatible pair to avoid displaying a misleading alignment.

## macOS environment

Preparation verifies that the application directory is visible inside the VM. Moving the app from Desktop to Applications or renaming it **NewPat.app** requires a share matching its current path. Recovery preserves the VM and user directories, verifies ownership and saves the configuration before changing it. An active session prevents maintenance that would interfere with the analysis.

The standard application path is `/Applications/NewPat.app`. The data directory `~/Library/Application Support/NIPAT-Desktop` and the VM's technical identity remain compatible with earlier installations.

## Resources and reproducibility

The CPU and memory budget comes from the resources assigned to the environment and container limits. NewPat records this budget at the start of a run. Changes in other applications' memory usage do not change it mid-run. The global process ceiling is fixed for the analysis. A phase with fewer independent tasks can use fewer workers.

The scheduler replaces the universal 2 GiB allowance per worker with estimates for the assigned resources, coordinator and expected workload. DNP block targets respect the selected limits, keep indivisible groups together and preserve the scientific filters. Local fixtures check numerical equivalence and ordering. Real-data measurements and tests of the distributed runtime are separate qualification steps. DNP acquisition and the outer loops over SNP samples and contamination tables run serially when their memory requirements have not been observed. Inner phases can use parallelism once the data are loaded. The policy change alone provides no timing evidence.

## Diagnostics

The GUI can open the experiment directory and export a size-limited diagnostic archive with version and environment details and relevant logs. BAMs, FASTAs and genetic result tables require a separate, explicit results export.

## CPI and CPIN plots

Prenatal and postnatal results provide interactive access to calculated values. The **Combined view** reproduces three series from the original scripts. Black shows log₁₀(CPI), green shows compatible sites and a dashed orange line shows incompatible sites. Separate axes distinguish the index from site counts. Point details show the original values even when the drawing uses a scale transformation. Separate views remain available.

Static exports and original tables are preserved. The combined HTML view renders the recorded data alongside the PDF produced by the run. Interactive views work locally. If the series is too large or required columns are missing, an explanatory message directs the user to the original files.

## Name, packages and compatibility

Windows, shortcuts, installers, icons and current guides use **NewPat**. The primary command is `newpat`. Existing scripts can still invoke `nipat`. Installation identifiers and configured paths can retain NIPAT so users can upgrade and reopen experiments without moving data.

The public package names are `NewPat-Setup.exe`, `NewPat-0.9.5-Testing-installazione.zip`, `NewPat-0.9.5-Windows-completo.zip`, `NewPat-0.9.5-macos-arm64.pkg`, `NewPat-0.9.5-macos-x86_64.pkg` and `newpat-desktop_0.9.5_amd64.deb`. Aliases for earlier clients must have the same bytes and checksums as the corresponding packages.

The repository retains its historical URL. Attributions, licenses, frozen references, experiment records and earlier release notes keep their original names and identify the provenance of the scientific modules. Recompiling Windows setup creates a different binary. Smart App Control behavior observed for an earlier executable cannot establish acceptance of the new one. System protections remain enabled.

## Completed checks

[CI run 43904019136](https://github.com/GregorioDalia/nipat-desktop/actions/runs/43904019136) passed on commit `c0cb823602d69fe4998c550b8bd5a560d659655c`. All applicable Windows, Linux, macOS ARM64 and Intel, runtime, packaging and scientific qualification checks passed, including the aggregate gate. Native windows opened using WebView2 on Windows, WKWebView on both Mac architectures and GTK on Linux.

The **seven scientific checks** passed in the exact Linux AMD64 Docker image identified in the CI reports. They covered bundled scripts, labels and results, regressions and input modes, DNP performance measurements and results, edge cases and parameters, updated models, and comparison with immutable references. Five-module qualification recorded **86 successful executions out of 86**. Reports are retained as CI artifacts. Reuse during the installer build requires both the same source tree and the same immutable scientific image ID.

Checks included application Python and JavaScript tests, simulated launcher and migration regressions, R budget checks and numerical comparisons for DNP, SNP and contamination against frozen references. Synthetic DNP profiles of 2, 4 and 8 GiB checked values, read identity and ordering. Timing on user BAMs requires separate measurement.

Local R comparisons used R 4.4.2 and test dependencies that can differ from the scientific image. CI records qualification in the actual image separately. On Windows the installer fixture compiled, installed, upgraded and uninstalled successfully, preserving the test data.

## Package checks and testing on physical devices

The installer build binds the four final packages to the same commit and scientific archive, verifies their contents and retains checksums and reports. Publication requires a successful build and its acceptance record. Source CI alone does not verify installer bytes.

Outstanding physical tests included final installation and Lima/Rosetta operation on M1 and M3 Macs, upgrades from NIPAT, environment recovery and complete WSL setup on Windows 10/11. Windows Server 2022 CI cannot establish Smart App Control acceptance on a user's computer. WKWebView tests on Mac runners cannot establish Gatekeeper acceptance or VM startup on the target Mac.

The pre-1.0 acceptance record lists deferred desktop scenarios. Domain researchers retain responsibility for scientific evaluation on real data. This release was designated **Testing** independently of the outcome of automated checks.
