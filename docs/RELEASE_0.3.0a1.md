# NIPAT CLI 0.3.0a1 — domain testing on Windows

These historical notes cover Windows 11 x64 with **working WSL2**. For the current version, see the [README](../README.md) and [user guide](USER_GUIDE.md). The prerelease included CLI workflows for DNPcall, SNPcall, Contamination and CPI. A GUI was outside its scope.

## Startup

1. Download **NIPAT-Setup.exe** from this release's GitHub assets.
2. Double-click it from your normal account without using **Run as administrator**.
3. Wait for download, configuration and self-tests to report **`NIPAT: ready`**.
4. Open **NIPAT** from Start and select the analysis, inputs and results directory.

Setup provides portable Python and a dedicated WSL environment containing Docker Engine, R, samtools and the required packages. It requires internet access the first time. Subsequent analyses run on the computer. Docker Desktop, Python and R do not require separate installation. See the [versioned user guide](https://github.com/GregorioDalia/nipat-desktop/blob/v0.3.0a1/docs/GUIDA_UTILIZZO.md) for workflows and inputs, [project overview](../OVERVIEW.md) for integration and [validation sheet](VALIDATION.md) for recording outcomes.

## Checks and limitations

Automated checks covered Python and PowerShell, the SNPcall example, synthetic CPI and Contamination cases, external input modes, and image load, execution and reload in the distributed engine. On the development PC an earlier, locally corrected candidate completed setup and self-tests, restarted its engine and reproduced results at 11 sites across 11 compared columns of a real BAM. The [Windows installer record](https://github.com/GregorioDalia/nipat-desktop/blob/v0.3.0a1/docs/INSTALLATORE_WINDOWS.md) identifies that candidate and the exact scope.

First installation of this EXE on a second PC and independent scientific cases remained open. Initial WSL activation and resumption after Windows reboot were untested. Inputs had to reside on fixed local disks. The WSL backend did not support UNC shares or network drives. Windows could display an unknown-publisher warning for the unsigned EXE. An experimental NIPAT environment with a different rootfs required separate migration. On failure, retain `setup.log` and `state.json` as described in the guide and preserve existing distributions and results.

The release tag, source commit and assets must match the manifest inside the EXE. Check downloads against `SHA256SUMS`. Earlier tags `v0.2.0a1` and `v0.2.0a2` remain unchanged.
