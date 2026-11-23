# NIPAT Desktop 0.8.99 — separate Windows ZIP and setup installations

Release 0.8.99 changed Windows installation, preparation and updates. DNPcall, SNPcall, Contamination, prenatal CPI and postnatal CPIN retained the 0.8.95 models.

## Local ZIP installation

`NIPAT-0.8.99-Windows-completo.zip` contains the application, Python and both runtime archives. Extract it to its permanent location and run `1_INSTALLA.cmd` to prepare the `NIPAT` subdirectory. Use `NIPAT\2_AVVIA.cmd` to launch and `NIPAT\1_COMPLETA_PREPARAZIONE.cmd` to resume preparation. Start menu shortcuts are optional to the workflow.

Data, results, cache, the WSL environment and preferences remain under that root. Keep the `NIPAT` directory. ZIP updates preserve the original destination and activate the new version after preparation. WSL is registered on the host, so moving the directory to another computer is insufficient to reproduce the installation.

`LEGGIMI.txt` documents PowerShell recovery, including checking the official hash, handling the selected archive's Internet mark, extracting a fresh copy and starting the same installer. Device policy still applies to individual components.

## Online setup

`NIPAT-Setup.exe` guides installation and downloads `NIPAT-<version>-Windows-payload.zip` from GitHub. The setup has its own bootstrap version. Compatible updates reuse the setup stored with the application and download the verified payload for the new release.

First installation resolves a compatible stable release. An update requests the exact version offered to the client and verifies its commit, size and SHA-256. The setup/payload and full ZIP have separate update feeds. Downloads require Internet access. Scientific analyses run locally. Bootstrap corrections or incompatible changes can require a new setup.

## Preparation and qualification

Preparation uses Windows primitives and Python for process coordination, without loading `NipatActivityNative.dll`. System tools configure WSL. Elevation applies only to operations that require it.

The ZIP and EXE installations have separate locations and update mechanisms. This release provided no automatic migration or general backward-compatibility contract for earlier installations. Unrelated data and results are preserved.

Published reports identify package hashes and completed CI checks. Scientific qualification, a physical Windows/WSL restart and Smart App Control tests on the target device are distinct from hosted installer checks. The setup lacked a NIPAT Authenticode signature. Consult the [Windows guide](WINDOWS_INSTALLER.md) for procedures, logs and checks.
