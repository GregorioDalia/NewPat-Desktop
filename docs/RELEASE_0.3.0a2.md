# NIPAT CLI 0.3.0a2 — guided input and Windows launch

This development record applies to candidate `0.3.0a2`. Current instructions are in the [README](../README.md) and [user guide](USER_GUIDE.md).

## Changes

- Double-click `NIPAT-Setup.exe` to install the internal Linux environment and bundled scientific runtime, then start **NIPAT**. No separate directory or archive preparation is needed.
- Both the WSL installation and Docker Desktop package provide `NIPAT.exe`. Double-clicking opens the CLI. Direct commands remain available.
- The alternative `NIPAT-DockerDesktop-0.3.0a2-windows-x64.zip` supplies portable Python and the same verified scientific archive. It requires a working Docker Desktop installation with Linux containers. Its setup resolves the local image identity after loading the verified archive. The export engine's identifier need not match.
- A rootfs change prepares a separate internal Linux environment. Setup checks tools and runs self-tests before switching, preserves the previous distribution and data/results directories, and supports resumption after failure.
- Original NIPAT code uses GPL-3.0-or-later. Included components have their own license records and attributions.
- The versioned NIPAT banner and vertical menu support arrow keys and Enter in compatible terminals, and numeric selections in plain text.
- Input validation occurs while filling the form. `:indietro` returns to the previous field and preserves values during correction. Each of the four workflows displays contextual help, examples and available commands after mode selection and inside the fields. In lists, Enter repeats instructions before the first file and ends the list after at least one file has been entered. Use `:annulla` to cancel a field. Numeric `0` has no such function.
- Users can edit inputs, parameters and destination in the summary before choosing **Avvia analisi** (Start analysis). The final screen opens results, the run directory and logs, displays execution metadata and recalls the last run of the session.
- **7 — Guida all'uso** contains **1 — Come usare NIPAT** and **2 — Verifica strumenti di analisi**. Tool verification requires a separate request and is skipped during `--dry-run`.

All four workflows and their input modes retain their R algorithms and scientific defaults. The changes add no external Python dependencies. The selected results directory and last-run recall last for the session. Persistent history and automatic workflow chaining were outside this version.

## Candidate checks

Before the WSL migration update, local verification of the launcher and two-package revision passed 178 Python tests on Python 3.12.14, 17 publication tests (including a package from the actual generator) and 32 portable-runtime load assertions using PowerShell 7.6.7 on Linux. These covered archive verification, local identity, platform and error handling. Windows CI exercises the compiled EXE and PowerShell 5.1. Its result must be associated with the delivered build.

At commit `5be5094`, using Python 3.12.14, all 173 automated tests passed. New cases covered Enter on required fields and lists, retained items, cancellation, path corrections and on-demand tool checks. In a POSIX console, repeated Enter before the first DNPcall BAM left the field open, displayed instructions and allowed cancellation. An SNPcall `--dry-run` through the real menu and services ended successfully with status `planned` and no scientific result.

On the earlier `cf16710` base, before contextual help and the Help menu revisions, 164 Python 3.12.14 tests passed. They covered the four workflows, field edits, confirmation and results. New modules imported in isolated Python without `site-packages`. Arrows, Enter and Esc worked in a real POSIX terminal, alongside the plain-text numeric menu. An SNPcall `--dry-run` through real services recorded `planned` without reporting scientific completion. Package, manifest and installer display all used `0.3.0a2`, with a test for divergence. PowerShell accepted the Python-generated manifest. All 64 installer assertions passed on PowerShell 7 for Linux.

The Windows acceptance plan still called for these checks on the final packages:

1. Start `NIPAT.exe` in both modes, finish setup and self-tests, and confirm a real analysis.
2. Exercise arrows, Enter, numeric selections and contextual help in every workflow mode.
3. Try Enter before and after the first file, correct a bad path, go back with `:indietro` and cancel with `:annulla`.
4. Distinguish Help from tool verification, including behavior in `--dry-run`.
5. Edit a field from the summary and verify that only confirmation starts the analysis.
6. Open the results directory and log after an analysis.

The automated upgrade logic still required physical Windows installation, upgrade, resumption and preservation checks. Failed preparation blocks the updated app. Setup does not automatically roll back application files already replaced. Language selection remained future work. Independent domain validation and observations from other versions are separate.

[User guide](USER_GUIDE.md) · [Project overview](../OVERVIEW.md) · [Validation sheet](VALIDATION.md)
