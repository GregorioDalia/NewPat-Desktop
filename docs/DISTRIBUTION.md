# Distribution and system requirements

For a published version, open **Assets** on the [latest stable release](https://github.com/GregorioDalia/nipat-desktop/releases/latest). Match the version in the filename to the release tag and choose your operating system and processor. GitHub's **Source code** downloads are for developers. The table uses the 0.9.10 naming convention.

| System | Package | Scientific environment |
| --- | --- | --- |
| Windows 10 22H2 x64 (build 19045) or Windows 11 x64 | `NewPat-Setup.exe` | NewPat-managed WSL2 distribution with Docker Engine |
| Same Windows systems, local folder installation | `NewPat-<version>-Windows-complete.zip` | Same WSL2 runtime; complete archives included |
| macOS 14 or later, Apple Silicon | `NewPat-<version>-macos-arm64.pkg` | ARM64 Lima VM, Linux AMD64 image with Rosetta |
| macOS 14 or later, Intel | `NewPat-<version>-macos-x86_64.pkg` | AMD64 Lima VM and Docker Engine |
| Ubuntu 24.04 LTS, x86_64 | `newpat-desktop_<version>_amd64.deb` | Local system Docker Engine and Compose v2 |

All packages use the same scientific Linux AMD64 image with R, samtools, the analysis scripts and their dependencies. Each analysis container runs offline, reads selected inputs through read-only mounts and writes to its own run directory.

## Install

- **Windows.** Run the setup from your regular account. It includes bootstrap Python, downloads a verified payload and prepares missing WSL prerequisites. Those steps may require internet access, an administrator and a reboot. When **NewPat: ready** appears, launch the Start menu or desktop shortcut. For the complete ZIP, extract to a permanent local directory, run `1_INSTALL.cmd` and keep the resulting `NIPAT` directory. The older 0.9.9 archive ends in `-Windows-completo.zip` and uses `1_INSTALLA.cmd`. Its `NewPat.lnk` opens the app. The ZIP installation has its own update method and machine-specific WSL registration. [Windows guide](WINDOWS_INSTALLER.md)
- **macOS.** Open the matching PKG, run Installer and open **NewPat** from Applications. First launch configures the dedicated Lima VM and requires internet access. Native Python and Lima are bundled. macOS may require explicit approval for unsigned, unnotarized software. User data lives in `~/Library/Application Support/NIPAT-Desktop`. [macOS guide](MACOS_INSTALLER.md)
- **Ubuntu.** Install the downloaded DEB with APT using its exact filename. APT resolves eligible missing dependencies. The administrator must authorize the user's access to the local Docker socket. Start **NewPat** from the applications menu. [Ubuntu guide](LINUX_INSTALLER.md)

## Development installation on Ubuntu

From a fresh source checkout, with Python 3.12, venv, system Docker Engine and Compose v2:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
newpat build-runtime
newpat doctor --runtime
newpat self-test
newpat wizard
```

The build needs internet access. Keep development files separate from the packaged application. Supply `--data-dir` and `--runs-dir` before the subcommand to override output locations.

## Operation and updates

The application reports physical, VM and container resources separately. The [resource guide](RESOURCES.md) identifies which changes need a restart. Each analysis retains its sample mapping and [run report](RUNS.md). Scientific outputs retain identifiers required by downstream stages; presentation exports include original sample names.

New profiles use the **Stable** update channel. Users may select **Testing** or enable an optional startup notification. Existing preferences are preserved. **Check for updates** offers newer approved releases compatible with the installed system and installation method. The client verifies the package before installation. Finish active analyses before updating. Data and results remain in their configured directories.

The package manifest, commit, version and SHA-256 identify exact bytes. Windows and Apple trust decisions use separate mechanisms. Release notes describe the checks performed for a particular build. For candidate verification and evidence, see [installer acceptance](INSTALLER_ACCEPTANCE.md), [CI/CD](CI_CD.md) and [domain validation](VALIDATION.md). See also the [license](../LICENSE) and [third-party notices](../THIRD_PARTY_NOTICES.md).
