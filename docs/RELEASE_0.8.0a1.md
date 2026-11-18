# NIPAT Experimental08 0.8.0a1

This portability experiment targeted Windows 10 and macOS alongside the stable NIPAT Desktop 0.7.2 distribution. Successful installation and analysis on Windows 10, Intel Mac or Apple Silicon must be established from the reports for each build and device.

## Scientific workflows

The text menu and CLI provide DNPcall, SNPcall, Contamination and CPI. Workflow composition, parameters, input validation, the scientific catalog and run records follow the existing contracts. The Linux image includes R, samtools, dependencies and workflow orchestration. This release predates the GUI.

## Experimental packages

| Experimental platform | Package |
| --- | --- |
| Windows 10 22H2 x64 build 19045 and Windows 11 x64 | `NIPAT-Setup.exe` |
| macOS 14 or later, Apple Silicon | `NIPAT-Experimental-0.8.0a1-macos-arm64.pkg` |
| macOS 14 or later, Intel | `NIPAT-Experimental-0.8.0a1-macos-x86_64.pkg` |

Windows uses a dedicated WSL2 distribution with prerequisite detection. Preparation may require an Internet connection, administrative approval and a restart. Windows 10 Pro 22H2 build `19045.6466` meets the version requirement. Other cumulative update revisions of build 19045 also qualify. Installation and WSL operation still required a physical-device test. Windows Server, ARM and 32-bit Windows were outside the supported targets.

The macOS packages include Lima, Python and native tools. Initial guest preparation requires Internet access. Both architectures use the same Linux AMD64 scientific image. Apple Silicon uses Rosetta inside an ARM64 VM. Evidence on this runtime is needed to assess performance and results. Ubuntu retained the stable 0.7.2 DEB, and Linux continued to host engine development and regression tests.

## Distribution and validation

The `experimental08` profile has its own **NIPAT Experimental08** name, directories and runtime. It leaves the stable installation in place and disables update checks. The desktop update channel continued to serve the stable release. Builds from `experiment/0.8-portability` produced dedicated artifacts or an experimental prerelease while preserving `main`, `Latest` and the 0.7.2 assets.

Build reports identify the commit, checksums and completed checks. CI covers the Mac clients, Windows detection, profile isolation, transport contracts, packaging and known scientific cases on Linux. Real Lima jobs are optional. Device tests cover first installation without WSL, restart, file permissions, Lima start and stop, Rosetta, reinstall and data preservation. Those scenarios and scientific validation on representative samples have separate evidence.

Packages lacked a system-recognized NIPAT signature and the Mac application lacked notarization. An operating system may block these packages.

## Further reading

- [User guide](GUIDA_UTILIZZO.md)
- [Distribution and requirements](DISTRIBUZIONE.md)
- [Windows installer](INSTALLATORE_WINDOWS.md)
- [macOS installer](INSTALLATORE_MACOS.md)
- [CI/CD and verification](CI_CD.md)
- [Validation record](VALIDAZIONE.md)
