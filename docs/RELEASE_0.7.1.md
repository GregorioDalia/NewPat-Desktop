# NIPAT Desktop 0.7.1

This research release offered four scientific analyses, automatic workflows and a settings catalog via a guided text menu or CLI. Its scientific core remained the R algorithms. There was no graphical interface or claim of clinical or general scientific validation. The [release list](https://github.com/GregorioDalia/nipat-desktop/releases) identifies installers and evidence. The [user guide](USER_GUIDE.md) describes inputs, parameters and results. Use the [validation sheet](VALIDATION.md) to record outcomes and difficulties.

## Installation

| Platform | Download | Execution |
| --- | --- | --- |
| Windows 11 x64 | `NIPAT-Setup.exe` | Double-click to install, then open **NIPAT Desktop**. Includes dedicated WSL2 and Docker Engine. |
| Ubuntu 24.04 LTS x86_64 | `nipat-desktop_0.7.1_amd64.deb` | Install with APT, then open **NIPAT Desktop** or run `nipat`. Uses local Docker Engine and Compose v2. |

Both packages embed the same archive with R, samtools, dependencies, scripts and workflow handling. Windows includes portable Python. Enabling WSL2 can require permission, internet access and a restart. On Ubuntu APT resolves dependencies, but granting Docker access requires separate administrative action. Run NIPAT without root privileges.

Setup upgrades the existing **NIPAT Desktop** app, preserving data, results and preferences. Existing results retain the producing version. See the [Windows](WINDOWS_INSTALLER.md) and [Ubuntu](LINUX_INSTALLER.md) guides. The Windows package lacks a NIPAT Authenticode signature. Record any download or execution block on the affected device.

## Analyses and workflows

Entries **1–4** start individual DNPcall, SNPcall, Contamination and CPI runs. **W — Workflow automatici** offers these plans:

| Choice | Sequence | Specific inputs |
| --- | --- | --- |
| W → 1 | DNPcall → Contamination | One or more BAMs, FASTA and DNP panel. The Contamination panel can be the same or separate. |
| W → 2 | DNPcall → CPI | Maternal cfDNA and paternal BAM pairs with known roles, population frequencies and CPI site selection. |
| W → 3 | DNPcall → Contamination and CPI | Both downstream analyses receive the same DNPcall tables and their respective inputs. |
| W → 4 | Multi-sample SNPcall | BAMs with FASTA or compatible pileups, and a shared SNP panel. |

An explicit SNP panel enables optional, independent SNPcall on the same BAMs in plans 1–3. Its results do not feed Contamination or CPI. Contamination preserves DNPcall counts and does not automatically filter CPI samples. One confirmation starts the plan in the scientific container. Steps run sequentially. Failure or cancellation prevents subsequent steps from starting. Each step retains its prepared inputs, results, logs and status. Shared pair members are processed once, preserving roles and associations. Interrupted runs cannot resume automatically.

## Interaction and traceability

The menu separates single analyses, automatic workflows and tools. Arrow-key navigation adapts to window resizing and explains when it falls back to text input. Numeric and letter shortcuts, including **W**, remain available.

- Select the reference FASTA sequence file. Selecting `.fai` or `.gzi` as the reference prompts an explicit correction and preserves user choice.
- A DNP panel lists target positions and alleles. `DNP_list.txt` is an example filename.
- Relative paths resolve against the working directory displayed before the field. The configured **Dati** directory does not redefine that base. Bamlist entries remain relative to the list's directory.
- A pair ID such as `Coppia01` is a user-chosen label for two samples of known roles. It need not match a BAM name and is not a scientific parameter.

Use `:annulla` and Enter in text fields or Ctrl+C, including during computation, to return to the main menu. NIPAT attempts to stop the container and reports unconfirmed stops. Partial logs and outputs remain accessible from **Ultima esecuzione** (Last run). Unsaved preference edits are discarded. **0 — Esci** exits the session.

The [scientific catalog](SCIENTIFIC_CATALOG.md), accessible from Help or `nipat parameters`, distinguishes public R options, internal rules and input preparation in Italian and English. The [roadmap](ROADMAP.md) covered full interface and guide translation.

## Evidence and scope

Publication binds exact installers to a source commit, Actions build, checksums, acceptance record and automatic evidence under the [research distribution protocol](INSTALLER_ACCEPTANCE.md). Checks cover Windows and Linux clients, real R and samtools numerical regressions, composed and separate analyses, sample identity, parameter propagation, cancellation and preservation of results. Builds exercise the staged Windows client with portable Python and the installed Ubuntu package. [CI/CD](CI_CD.md) details the coverage.

The historical Windows observation used 0.7.0a1, commit `1b601081a4aff9efe1806c921fd7ac963feea7b7`, with WSL2 and a real BAM. DNPcall → Contamination reproduced the standalone counts and genotypes for 11 DNP sites. Contamination retained 10 sites with mean and standard deviation both zero. This is evidence for the observed case. It cannot establish biological absence of contamination or general validity.

For 0.7.1 the publication checks compare scientific and runtime sources and require explicit review of client and package preparation changes. The previous observation is not a manual test of this EXE. Acceptance includes further target-device, multi-sample and representative CPI evaluation.
