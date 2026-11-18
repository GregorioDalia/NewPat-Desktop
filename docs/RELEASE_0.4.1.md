# NIPAT CLI 0.4.1 — simpler installation and startup

This Windows 11 x64 prerelease simplified Docker Desktop installation and launch. One installer and one icon handle preparation, startup and retry. Scientific algorithms were unchanged and domain validation remained open. Current instructions are in the [README](../README.md) and [user guide](GUIDA_UTILIZZO.md).

| Package | Procedure |
| --- | --- |
| [NIPAT-Setup.exe](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.4.1/NIPAT-Setup.exe) | Double-click to install the dedicated WSL environment. Wait for `NIPAT: ready`, then start **NIPAT**. This path assumes working WSL2. |
| [NIPAT-DockerDesktop-Setup.exe](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.4.1/NIPAT-DockerDesktop-Setup.exe) | Start Docker Desktop with Linux containers, double-click to install and open **NIPAT (Docker Desktop)**. Preparation and self-tests run before the menu opens. |

Both installers contain their complete payloads. The second requires Docker Desktop. After preparation fails, open its icon again to retry. Subsequent launches reuse completed preparation. Both installations can coexist in distinct default directories. The WSL installer embeds its own Linux environment. Initial WSL activation may require internet access, permission and a reboot and remained a separate test.

## Verification

The [versioned user guide](https://github.com/GregorioDalia/nipat-desktop/blob/v0.4.1/docs/GUIDA_UTILIZZO.md) describes the menu and four workflows. The [first Docker Desktop test](https://github.com/GregorioDalia/nipat-desktop/blob/v0.4.1/docs/VALIDAZIONE.md#prima-prova-con-docker-desktop) covers preparation and a real DNPcall → Contamination sequence, with logs and expected and observed results. Record the tested package explicitly. These notes make no claim of a new manual Windows test.

The launcher still uses PowerShell internally. Code signing, antivirus acceptance and SmartScreen acceptance were outside this revision. The [0.4.0 notes](RELEASE_0.4.0.md) document the earlier ZIP and separate setup route. Original NIPAT code remains GPL-3.0-or-later and the packages include component licenses.
