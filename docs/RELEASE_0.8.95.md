# NIPAT Desktop 0.8.95 — additional full Windows ZIP

This release kept the four 0.8.90 installers and added `NIPAT-0.8.95-Windows-completo.zip`. The Windows `NIPAT-Setup.exe` remained a self-contained installer. The five scientific modules and R formulas were unchanged.

## ZIP installation

Extract the entire archive and run `1_INSTALLA.cmd`. The package includes Python 3.12.10, the WSL filesystem and the same scientific archive used by the other installers. Enabling or updating Windows WSL components may require Internet access, administrator approval and a restart.

After verification and preparation, the installer creates the Start menu shortcuts **NIPAT Desktop ZIP** and **NIPAT Desktop ZIP - completa preparazione**. It installs to `%LOCALAPPDATA%\NIPAT-Desktop-Zip` with its own data, results, cache and preferences. The EXE installation keeps its own directory and registration.

Each version has its own directory. The active-version pointer changes only after successful preparation. Interruptions, errors or restart requests leave the previous version selected. Menu updates download a full ZIP and retain the installation method. Previous application directories are kept.

## Windows components and evidence

The native launcher's component version was `0.8.81`, independently of the application version returned by `nipat --version`. The build checks the launcher's and coordination DLL's SHA-256 digests against the 0.8.81 components.

The ZIP skips the Inno Setup executable. Windows still evaluates scripts, DLLs and WSL helpers according to device policy. No NIPAT publisher signature or Smart App Control qualification was claimed.

`windows-zip-check.json` records package verification. `desktop-acceptance.json` binds the ZIP digest to the accepted build. Release reports distinguish embedded-Python client checks and scientific regressions from physical Windows tests with WSL and Smart App Control enabled. Domain validation remains separate. The [Windows ZIP guide](INSTALLATORE_WINDOWS.md#complete-zip-installation) covers installation, recovery and paths. GitHub’s **Source code** ZIP is the source distribution.
