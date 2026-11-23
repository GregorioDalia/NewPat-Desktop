# NIPAT Desktop 0.6.0

This pre-1.0 research release provided four local analyses, a guided text menu, persistent configuration and in-app updates. The [release list](https://github.com/GregorioDalia/nipat-desktop/releases) identifies the packages actually published. The distribution supports research and makes no general scientific validation claim.

## Installation

| Platform | Package | Startup |
| --- | --- | --- |
| Windows 11 x64 | `NIPAT-Setup.exe` with portable Python, dedicated WSL2 and the scientific image | Double-click setup, then open **NIPAT Desktop**. |
| Ubuntu 24.04 LTS x86_64 | `nipat-desktop_0.6.0_amd64.deb` with the app and the same image | Install with APT, then use **NIPAT Desktop** or `nipat`. |

NIPAT Desktop has its own installation identity and paths. Windows setup lets users choose locations for the application, WSL environment, cache, data and results. Upgrade and repair preserve those destinations and files outside the installed components. WSL2 requires virtualization. Initial activation may require internet access, administrative permission and a restart. Windows needs no separate Docker Desktop, R, samtools or Python installation. This package has no NIPAT Authenticode signature. Acceptance by local device protections needs testing on the target workstation.

Ubuntu APT resolves missing Python 3.12, Docker Engine and Compose v2 dependencies. Permission to access the Docker socket is a separate administrative decision. Run NIPAT as a non-root user.

## Menu and preferences

DNPcall, SNPcall, Contamination and CPI are available from the text menu. Field instructions guide entry. At the summary, Enter alone cancels. **1 — Avvia analisi** explicitly starts computation. There is no graphical interface.

**Configura** persists data and result directories, modes, references and workflow parameter defaults. Users can override proposed values for the current analysis and must select samples, CPI pairs and a run name each time. **Guida e informazioni** and **Verifica ambiente** are separate menu entries. Menu preferences do not affect direct CLI commands.

Preferences live in `%LOCALAPPDATA%\NIPAT-Desktop\preferences.json` on Windows and `${XDG_CONFIG_HOME:-~/.config}/nipat-desktop/preferences.json` on Linux. Moving the application, WSL or cache requires setup.

## Updates

**9 — Verifica aggiornamenti** checks approved published GitHub releases and verifies the complete downloaded installer. Download and installation require separate confirmations. Users can cancel or defer either. Setup preserves paths, preferences, data and results. Installing the Ubuntu `.deb` requires APT administrator permission.

**Configura → Aggiornamenti** offers `testing` (the default, including approved prereleases and stable releases) and `stable` (approved stable releases only). Startup checks are optional and disabled initially. They display a notification without downloading or installing software. Prepared installations and analyses work offline. The updater cannot publish a review build or grant package acceptance. Every run records the application version and actual engine identity.

## Engine and records

The self-contained image includes the R scripts, samtools, dependencies and workflow preparation. Version 0.6 retains the R algorithms. Inputs are mounted read-only and each local analysis creates a separate directory. Results go in `output`, available intermediates in `work`, parameters and status in `run.json`, and messages in `execution.log`. To chain analyses, select compatible outputs for the next workflow. Existing results are preserved.

Self-tests cover the supplied cases. Publication combines automated checks with documented manual installation and operation evidence, identifying desktop scenarios still pending. Reusing observations from a previous build requires comparing operative source files and cannot establish that the new EXE was manually tested. The release retains evidence and limitations. Domain evaluation with appropriate inputs and reference results was planned for 0.7.

[User guide](USER_GUIDE.md) · [Distribution requirements](DISTRIBUTION.md) · [Results and logs](RUNS.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md) · [Technical and domain validation](VALIDATION.md) · [GPL-3.0-or-later](../LICENSE) · [Third-party notices](../THIRD_PARTY_NOTICES.md)
