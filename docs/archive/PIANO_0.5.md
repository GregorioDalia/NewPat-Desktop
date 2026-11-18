# Development plan for NIPAT 0.5

Historical status on 23 October 2026, during the sixth increment. This document records decisions, completed work and outstanding acceptance criteria. For current contracts see [Architecture](../ARCHITECTURE.md) and [CI/CD](../CI_CD.md).

## Baseline

Domain testing was using `v0.4.1`, commit `8e1f57d4721d7864051747cb5d5b10cfe8408a77`. Development branched from `main` at `30a623a3133171b9ff5610dffa04d4d3b78e783a`, including subsequent CI/CD checks, into a separate checkout of `feature/0.5-foundation`. Existing 0.4.1 tags, assets, manifests and notes were to remain intact. Future removal of Docker Desktop applied to the new product. Candidate testers needed to retain their 0.4.1 installation, with separate application identity, shortcuts, configuration, WSL distribution and default results directory. Increment six introduced the separate Preview channel. Automatic publication and replacement of existing release assets were outside the plan. Migration from 0.4.1 would require an explicit verified step.

## Design decisions

1. R remains the scientific core. Preserve the R files and SHA-256 manifest during packaging.
2. Windows uses dedicated WSL2 with NIPAT-managed Docker Engine. Remove the Docker Desktop edition from the active application, installers and distribution.
3. The image already provides R and samtools. Include the scripts and preparation for all four workflows so that the engine can run independently of the checkout and Windows application directory.
4. Python adapters may run inside the engine. The scientific algorithms remain in R.
5. The desktop interface stays outside the engine. The existing guided CLI supports independent infrastructure work.
6. GitHub will provide a Windows installer and a Linux installer using the same engine archive for the supported architecture, built and verified once.
7. Linux continues to require native Docker Engine. Its Docker transport remains available.

Initial Linux support targets **Ubuntu 24.04 LTS x86_64**, with packaging and dependencies selected for that system. The 0.5 interface is a guided CLI. A future external GUI can use the same execution contract.

## Increment 1 — package the R code

The Dockerfile installs the four unchanged R scripts, licenses and manifest under `/opt/nipat`. `engine/main.py` verifies hashes and exposes `describe`, `verify` and `run` with native script arguments. Local checks included 204 Python and 37 CI selection/publisher tests. CI and installer review builds run `scripts/verify_engine_package.py` to execute SNPcall, Contamination and CPI without an application or checkout mount, with networking disabled and a read-only image filesystem. It checks numerical expectations from existing regressions.

[CI 39806767798](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39806767798) and [review build 39806767596](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39806767596) passed at `22e0677`. DNPcall was bundled and checked by hash. A BAM regression through the new entry point was still missing. Installer artifacts exercised the existing packaging structure and were unsuitable for installing alongside 0.4.1. Separate product identities and two new installers belonged to later increments.

## Increment 2 — Contamination

The CLI sends a `contamination-v1` request with the original panel, selected files, sample names and destinations. It supports explicit files and recursive directory discovery. The engine validates inputs, normalizes the panel, prepares `.txt` tables and runs the unchanged R script. Client and engine share validators in `nipat_scientific`.

A self-contained Compose document mounts selected inputs read-only and the single run directory writable. It excludes the application and global data directories, disables networking and uses a read-only image filesystem. `runtime.engine` records hashes of the actual scripts and Python preparation code separately from client hashes. Older images lacking the contract are rejected before analysis.

Tests covered preparation, sample names and bytes, invalid requests, tracing and interruption. The image test ran the CLI from an application directory containing only `compose.yaml`. The other three workflows still used their previous paths. Local results were 224 Python and 37 CI/publisher checks passed. Image and packaging checks passed separately in [CI 39812476371](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39812476371) and [review build 39812476253](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39812476253) on `56701ee`. Published installers remained unchanged.

## Increment 3 — SNPcall

`snp-call-v1` accepts an existing pileup with a QNAME column or a BAM with FASTA. In BAM mode the engine validates inputs and reference indexes, generates three-base BED windows and a samtools pileup, and starts R only after samtools succeeds. A BAM index is optional. BGZF references retain `.fai` and `.gzi` support.

The CLI uses the Contamination isolation and mount contract. `work/snp_regions.bed` and `work/pileup.txt` remain available, and results are written to `output/SNPcall_output.txt`. SNPcall self-test uses the full execution path. R and the scientific manifest were unchanged.

Tests covered the nine distributed reference rows, a synthetic BAM with independent expected counts, both CLI modes without local scientific sources, invalid inputs, samtools failure and interruption. Local results were 243 Python and 37 CI/publisher tests passed. [CI 39940948277](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39940948277) and [review build 39940948282](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39940948282) passed on `aad3002`; the development PR records numerical and packaging outcomes.

## Increment 4 — DNPcall

`dnp-call-v1` carries the original panel, ordered BAM list, reference and serial/parallel choice. The client accepts a single BAM, multiple BAMs or a list with entries relative to the list file. `run.json` maps safe aliases to original files. The engine writes `work/DNP_list.txt` and `work/bamlist.txt`, then runs R from the run root with relative arguments compatible with its output filenames. BAM and FASTA inputs are read-only mounts and require no copies.

Image tests create synthetic BAMs from readable SAM and FASTA, with independent expected counts and genotypes. They cover the full engine and CLI without source mounts, one or multiple samples, relative lists, sample association and serial/parallel agreement. Direct native R execution checks preservation of outputs. Local tests passed 266 Python and 37 CI/publisher checks. [CI 39946173365](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39946173365) and [review build 39946173352](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39946173352) passed on `2592935`. The PR identifies outcomes and limitations.

The R code and manifest remained unchanged. DNPcall still removed pileup and BED files on completion, suppressed samtools stderr and lacked an explicit samtools exit status check. A successful process exit alone could not establish scientific output correctness.

## Increment 5 — CPI

`cpi-v1` transfers selected parental tables, pairs, prefixes, population frequencies, error constant and panels to the engine. The engine validates inputs, retains byte-identical tables in `work/inputs`, normalizes panels and runs R. Shared pair members are prepared once. The CLI uses the same isolated execution and engine metadata as the other workflows.

Supported choices include ALL without a panel, `--panel`, repeated `--cutoff` and `--cutoff-map`. A single panel can retain its path as its label. Explicit cutoff labels, custom or empty prefixes and a zero error constant remain supported. Staging and pair-PDF filename collisions, including case-only differences on Windows, are rejected before writing.

Image regressions covered known analytical values, no informative sites, CSV and PDF output, mount isolation, original input preservation and CLI operation without local scientific sources. A paternal incompatibility fixture yields two-site CPI products `20e²` and `4e`, tested with `e = 0.01`, `0.1` and `0`. The 293 Python and 37 CI/publisher tests passed locally. [CI 39949743382](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39949743382) and [review build 39949743373](https://github.com/GregorioDalia/nipat-desktop/actions/runs/39949743373) passed on `29fc5be`, with actual R numerical checks in CI.

All four scientific workflows now used the new path. Diagnostics, the Windows client, separate installation identities, Docker Desktop retirement and the new installers were outstanding. Review builds were not distributable 0.5 candidates and must not replace 0.4.1. R sources and their manifest were unchanged.

## Increment 6 — isolated Windows Preview

The internal version became `0.5.0a1` without a release. The `preview-0.5` profile has a stable identity across candidate updates: **NIPAT 0.5 Preview**, application directory `%LOCALAPPDATA%\Programs\NIPAT-0.5-Preview`, and data directory `%LOCALAPPDATA%\NIPAT-0.5-Preview` containing `data`, `runs`, `cache` and `wsl`. AppId, shortcuts, uninstall entry, mutex and RunOnce are separate from 0.4.1. An alternative application destination is rejected before copying.

WSL names begin with `NIPAT-05-Preview-` followed by the first 40 hexadecimal digits of the rootfs hash. The candidate avoids legacy 0.4.1 registries even for identical rootfs bytes. Manifest, state, backend, ownership and recovery record the channel. A missing channel is rejected. Preview updates preserve paths, resumption and activation guarantees.

The installed launcher selects its own environment even when the calling shell supplies stable NIPAT variables. Users can select supported local input paths and override destinations explicitly in the CLI. Uninstall preserves data, results, cache and distributions. The host WSL prerequisite is shared.

Checks cover manifests, packages, identity isolation, same-channel resume/upgrade and launcher startup. Local results were 300 Python and 43 CI/publisher tests passed. The development PR records actual outcomes. Simulated WSL boundaries in PowerShell cannot establish a real installation. Final client changes, Docker Desktop removal, Ubuntu packaging and package tests remained. The transitional Docker Desktop installer still had the previous identity and was unsuitable for installation or domain testing.

## Completion criteria at the time

Each increment required scoped changes, applicable local tests and a separate review before integration.

1. **Self-contained engine.** Specify input, parameter, state and output contracts. Bundle R and preparation adapters with baseline dependencies. Separate calculation from Windows path selection and Docker launch. First embed scripts, resources, manifest and engine identity where mounts cannot hide them. Then migrate one workflow at a time, beginning with existing numerical regressions. Completion requires four workflows using only selected inputs, configuration and work/output mounts, numerical expectations and stated tolerances, missing-informative-site cases, supported input modes, sample identities, run metadata, unchanged R/manifest bytes and verifiable engine version and contract.
2. **Windows WSL-only client.** Connect the CLI to the new engine and remove Docker Desktop launchers, preparation, installers and user-facing recommendations while preserving native Linux execution. Verify separation from 0.4.1's mutable state, start, analysis, cancellation, diagnosis and restart after stopping the runtime, paths containing spaces or on different local disks, one setup procedure and one icon. A physical Windows/WSL test is separate from CI simulation.
3. **Linux installer.** Deliver one package for the supported system with the same engine archive and a defined dependency procedure. Verify clean installation, archive identity and import, workflow execution, user access to results, error handling and uninstallation that preserves user data.
4. **CI/CD and release preparation.** Add engine tests without source mounts, which the earlier Compose self-tests did not cover. Make CI selection and build triggers follow embedded files. Replace Docker Desktop tests and artifacts with Linux coverage. Keep the aggregate `required` gate and failure on missing required checks. Update the publisher, which then required a Docker Desktop installer for releases after 0.4.1. Require paired Windows and Linux installers with manifests and checksums tied to one commit and scientific archive. Publish the verified artifacts manually, preserving their bytes and earlier releases.

Engine CI, Windows/Linux installation and scientific domain evaluation are distinct observations. A proposed 0.5 candidate required an explicit result and scope for each.
