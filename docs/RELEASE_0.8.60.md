# NIPAT Desktop 0.8.60

Release 0.8.60 fixed Windows setup preparation and added a synthetic test suite for installed clients. The five modules, scientific parameters and formulas are described in the [0.8.50 release notes](RELEASE_0.8.50.md).

## Windows setup and local tests

The CPIN verifier now locates its local helper under the installer’s embedded Python. This corrects the incomplete setup seen with 0.8.50. The build runs the five bundled verifiers and tests the suite driver using the actual embedded interpreter. The 0.8.50 repair utility is unnecessary for 0.8.60.

Setup records the self-test's stdout, stderr and exit code. An unavailable prerequisite leaves a resumable state. Setup marks an installation ready only after verification.

The bundled `scripts/windows/test-installed.ps1` exercises the five modules and composed workflows with three samples, explicit family roles, BAMs, pileups, tables and invalid inputs. It uses independent analytical expectations and compares serial, automatic and two-worker results. The suite runs with the installed Python and WSL runtime, checks version, commit and image, and writes HTML, JSON, logs and a ZIP to a fresh directory. It verifies that inputs, installation and preferences remain intact. See [installed-client verification](WINDOWS_INSTALLATION_TEST.md).

A previous Windows installation passed 70 checks in 10 minutes 57 seconds on **0.8.50 with the CPIN repair**. That result belongs to the repaired build.

## CI and reliability

An installer build can reuse seven scientific records from a successful CI run when the Git tree and Docker image match exactly. Verification covers identity, completeness, reports and hashes. A mismatch triggers fresh tests. One workflow can prepare and publish the qualified installers without rebuilding.

The [0.8.60 audit](AUDIT_0.8.60.md) records scope, fixes and limitations. The Windows post-update restart test retains the process handle and uses explicit acknowledgement to obtain the true exit code even if the process exits immediately. On Mac and Linux, Ctrl+C returns to the menu even just after the input prompt appears. The Windows console path keeps its previous behavior.

## Installation

Close active runs, use **Check for updates** on `stable` or select a package from the [0.8.60 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.60). Supported packages cover Windows x64, Ubuntu 24.04 x86_64 and ARM64/Intel macOS. The Windows installation path and PowerShell launch procedure remain compatible with 0.8.50.

`.github/release-acceptance/v0.8.60.json` ties test evidence to the published bytes and lists deferred scenarios. Complete end-device WSL/Lima installation and domain validation on biological data require evidence beyond the automated package fixtures.
