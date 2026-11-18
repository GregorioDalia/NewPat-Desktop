# NIPAT 0.5.0a1 — validation preview

This prerelease ran DNPcall, SNPcall, Contamination and CPI through a guided text menu and reproducible commands. It supported technical and domain evaluation. It included no graphical interface or general scientific validation claim. For current instructions see the [README](../README.md) and [user guide](GUIDA_UTILIZZO.md).

## Installers

- **Windows 11 x64.** `NIPAT-Setup.exe` supplies portable Python, dedicated WSL2, a NIPAT-managed Docker Engine and the scientific image. Double-click to install or launch. WSL2 activation requires virtualization and may require internet access, administrative permission and a restart.
- **Ubuntu 24.04 LTS x86_64.** `nipat-05-preview_0.5.0~a1_amd64.deb` includes the app and the same scientific image as Windows. APT installs missing Python 3.12, Docker Engine and Compose v2 dependencies. Granting access to Docker requires separate authorization. Users run NIPAT without root privileges.

Both packages use the **NIPAT 0.5 Preview** identity and dedicated paths. The scientific image contains R scripts, samtools, dependencies and input preparation. Local analyses use the verified image and do not download replacements.

## Operation and limitations

The menu collects inputs and parameters, previews the run and waits for confirmation. Runtime diagnostics and self-tests cover bundled examples. Each analysis writes results, intermediates, metadata and logs to a new directory. Input files remain unchanged. Users can chain analyses by selecting compatible outputs as inputs to the next workflow.

The Windows WSL backend requires fixed local disks and excludes network drives, UNC shares and removable drives. Docker Desktop is unnecessary. Ubuntu supports the local system Docker daemon, without rootless operation or UID remapping. Uninstallation preserves the package's designated data, results and runtime. Reinstalling an identical build is a different test from upgrading between versions. The included self-tests cover their fixtures. Evaluating application-specific datasets and parameters remains the responsibility of domain researchers.

See the [versioned user guide](https://github.com/GregorioDalia/nipat-desktop/blob/f4f6930c08c1d6f23554f38224a47ae243d676f1/docs/GUIDA_UTILIZZO.md), [distribution requirements](https://github.com/GregorioDalia/nipat-desktop/blob/f4f6930c08c1d6f23554f38224a47ae243d676f1/docs/DISTRIBUZIONE.md), [validation sheet](https://github.com/GregorioDalia/nipat-desktop/blob/f4f6930c08c1d6f23554f38224a47ae243d676f1/docs/VALIDAZIONE.md), [GPL-3.0-or-later license](https://github.com/GregorioDalia/nipat-desktop/blob/f4f6930c08c1d6f23554f38224a47ae243d676f1/LICENSE) and [third-party notices](https://github.com/GregorioDalia/nipat-desktop/blob/f4f6930c08c1d6f23554f38224a47ae243d676f1/THIRD_PARTY_NOTICES.md).
