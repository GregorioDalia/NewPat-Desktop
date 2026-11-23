# NIPAT Desktop 0.7.0a1 — installer qualification candidate

This candidate introduced automatic workflows and a scientific catalog in the text menu. It retained the four scientific R algorithms and their adapters. There was no GUI. Building a candidate in GitHub Actions did not replace the official 0.6.0 release, publish a package or validate the scientific method. [Published releases](https://github.com/GregorioDalia/nipat-desktop/releases)

## Workflows and controls

| **W — Workflow automatici** | Behavior |
| --- | --- |
| **1 — DNPcall → Contamination** | Produces DNP tables and passes them to Contamination. |
| **2 — DNPcall → CPI** | Processes the BAMs in declared pairs and passes their tables to CPI. |
| **3 — DNPcall → Contamination and CPI** | Both downstream analyses read the original DNP tables. Contamination estimates do not filter CPI. |
| **4 — Multi-sample SNPcall** | Runs a separate SNPcall analysis for each selected BAM or pileup within the same run. |

An explicit SNP panel enables optional SNPcall on the same BAMs in workflows 1–3. SNPcall results are independent of the Contamination and CPI inputs. A single review and confirmation starts the selected steps. Execution is sequential. An error or cancellation stops remaining steps. Interrupted runs require a new destination.

For CPI, assign each pair an ID, a maternal cfDNA BAM and a paternal BAM. Shared samples are processed once and retain their declared role. ALL, single-panel and labeled-panel modes and the error constant remain available. All four standalone commands are still supported.

**Guida e informazioni → Catalogo scientifico** and `nipat parameters` describe public script options, internal rules and input preparation in Italian and English. Reading the catalog leaves settings and analyses untouched. Full interface and documentation translation was planned.

In text fields and menus, `:annulla` returns to the main menu. Ctrl+C also does so during an analysis, stopping processing and preserving logs and partial results. The remaining workflow steps do not start. Unsaved configuration changes are discarded. Esc and `:indietro` go back one step. **0 — Esci** closes NIPAT from the main menu.

## Installing and obtaining a review build

| Platform | Package | Requirements |
| --- | --- | --- |
| Windows 11 x64 | `NIPAT-Setup.exe` | WSL2 and virtualization. Enabling WSL2 may require internet access, administrator authorization and restart. |
| Ubuntu 24.04 LTS x86_64 | `nipat-desktop_0.7.0~a1_amd64.deb` | Python 3.12, local Docker Engine and Compose v2. APT resolves missing dependencies. Docker access requires separate authorization. |

Both packages embed the same scientific archive, including R, samtools, dependencies, input preparation and plan execution. Windows also includes portable Python and dedicated WSL. Docker Desktop and separate scientific tools are unnecessary.

For a review build, open the successful [Installers (review build) workflow](https://github.com/GregorioDalia/nipat-desktop/actions/workflows/windows-installer.yml) on the selected commit and check `installer-required`. Its summary provides directly executable **NIPAT-Setup.exe** and installable **nipat-desktop_0.7.0~a1_amd64.deb** downloads. Ordinary installation needs only the platform installer. Keep the manifest, checksums and build ID as evidence. The **nipat-windows-setup** and **nipat-linux-setup** artifacts contain identical package copies and supporting evidence. Separate runtime archives are unnecessary.

In-app update checks see only approved published releases with manifests. See the [Windows](WINDOWS_INSTALLER.md) and [Ubuntu](LINUX_INSTALLER.md) guides. This candidate shares the 0.6 **NIPAT Desktop** identity and upgrades an existing installation in place. Close NIPAT sessions, check the paths offered by setup and choose a new results directory for testing. Data, results and preferences persist. Keeping files does not roll back the application binary.

## First package test

Record the downloaded version, source commit, checksum, operating system, initial WSL or Docker state and findings in the [validation sheet](VALIDATION.md).

1. Install and prepare the environment. Wait for `NIPAT: ready` on Windows. On Ubuntu run NIPAT from the user account and wait for preparation, diagnostics and self-tests.
2. Open **NIPAT Desktop**, verify its version and select a dedicated results directory under **Configura**.
3. Choose **8 — Verifica ambiente** and inspect the scientific catalog. Record diagnostic and self-test outcomes separately.
4. Under **W**, select a workflow for which suitable inputs and reference results exist. To test the full plan select **3**, declare pairs and add SNPcall with an explicit SNP panel. Obtain biological roles independently of filenames.
5. Review the plan and start once. Verify states, sample associations, counts and the results of every step. Compare standalone analyses on the same inputs and parameters. Evaluating scientific accuracy also requires an independent numerical reference.
6. Use **W → 4** with multiple BAMs. Reuse the saved pileups in pileup mode and compare per-sample results.
7. Reopen the app, verify preferences and access to results, and record the exact text of difficulties, errors and warnings.

This list specifies intended tests. CPI evaluation requires suitable maternal and paternal samples, panels and population frequencies. Record missing prerequisites as a test not performed.

## Results and traceability

Each run saves `run.json`, `execution.log` and the submitted plan. In `output/workflow`, `workflow-state.json` records overall and per-step state. `steps/dnp`, `steps/contamination`, `steps/cpi`, `steps/snp_0001`, `steps/snp_0002` and subsequent directories retain selected steps' own results and logs.

Records identify inputs, parameters, engine, samples, pairs and outputs. BAM-based SNPcall retains its BED, pileup and samtools preparation log. Pileup input reuses those files. A failed run preserves existing evidence and is not reused. See [execution records](RUNS.md).

## Verification scope

Engine regressions cover compositions, known numeric results, agreement with standalone analyses, sample identity and failures. Package checks apply to specific artifacts.

| Evidence | Tested | Coverage limit |
| --- | --- | --- |
| Windows `windows-client-check.json` | The staged client with embedded Python, catalog, menu and simulated plans, including spaces and Unicode in paths. | Inno Setup, WSL and scientific computation on the Windows runner were outside this check. |
| Ubuntu `linux-installation-check.json` | Installed package, individual analyses and the full plan on synthetic BAMs under a non-root account, preserving inputs, results and preferences. | The configured runner did not establish clean desktop installation or a 0.6 → 0.7 upgrade. |

Use each build's Actions results and logs. Workstation testing and domain evaluation apply to their specific versions and datasets. The [distribution procedure](../.github/RELEASE.md) distinguishes build, acceptance and publication.
