# NIPAT CLI 0.4.0 — prerelease for domain testing

This release was prepared for researchers to compare results against expectations for their own data. Its status indicated readiness for testing. Domain validation remained open. For the current release see the [README](../README.md) and [user guide](GUIDA_UTILIZZO.md).

## Download and startup

| Package | Procedure |
| --- | --- |
| [NIPAT-Setup.exe](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.4.0/NIPAT-Setup.exe) | Double-click the EXE, wait for `NIPAT: ready`, then open the **NIPAT** icon. |
| [NIPAT-DockerDesktop-0.4.0-windows-x64.zip](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.4.0/NIPAT-DockerDesktop-0.4.0-windows-x64.zip) | With Docker Desktop running Linux containers, extract the entire ZIP, run `1_SETUP.cmd` once, then open `NIPAT.exe`. |

The setup EXE includes an internal Linux environment and scientific runtime. It needs no separate archives or Docker Desktop. Initial scope was **Windows 11 x64 with working WSL2**. First-time WSL activation may require internet access, administrative permission and restart, and required separate testing.

## Included features

The guided interface provides contextual instructions, checks inputs, accepts corrections and presents an editable summary before confirmation. Both packages use `NIPAT.exe`, with menu actions to open results and logs. **Avvia analisi** runs the actual DNPcall, SNPcall, Contamination or CPI scripts using their supported input modes. Internal environment preparation is resumable and verifies readiness before switching. Data, results and the previous environment are preserved. Original NIPAT code is GPL-3.0-or-later. Bundled components retain their licenses.

## Test scope

With WSL2 already working, record installation and analysis separately for each package in the [0.4.0 validation sheet](https://github.com/GregorioDalia/nipat-desktop/blob/v0.4.0/docs/VALIDAZIONE.md), including the [first Docker Desktop test](https://github.com/GregorioDalia/nipat-desktop/blob/v0.4.0/docs/VALIDAZIONE.md#prima-prova-con-docker-desktop). See the [versioned user guide](https://github.com/GregorioDalia/nipat-desktop/blob/v0.4.0/docs/GUIDA_UTILIZZO.md). Historical technical checks cover their own cases. Validating new scientific cases requires independent evidence. WSL supports fixed local disks and excludes network drives and UNC shares. Automatic workflow chaining, persistent history, language selection and a GUI were outside this release.
