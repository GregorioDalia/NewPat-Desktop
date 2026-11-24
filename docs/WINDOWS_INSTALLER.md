# Install NewPat on Windows

Download **NewPat-Setup.exe** from the [stable release](https://github.com/GregorioDalia/nipat-desktop/releases/latest). Run it from your regular Windows account. It installs the latest compatible stable release, preserves the paths of a recognized installation and adds a Start menu shortcut. A separate [complete ZIP](#complete-zip-installation) installs under the directory where you extract it.

## Requirements

Use Windows 11 x64 or Windows 10 22H2 x64, build 19045, on a computer with hardware virtualization and WSL2. Windows Server, Windows on ARM, 32-bit Windows and earlier Windows 10 builds are outside the supported configuration. The installer checks edition, architecture, build and WSL readiness. Missing Windows features, kernel updates or device policy can require internet access, elevation or a restart. Docker Desktop, Python, R and samtools do not need to be installed separately.

Allow space for the application, downloaded archives, imported WSL filesystem, scientific image, inputs and results. A runtime upgrade may keep a previous filesystem alongside the new one. Choose writable local fixed disks for installed directories and inputs. The WSL transport does not support UNC paths, network drives or removable disks.

## Guided setup

1. Double-click `NewPat-Setup.exe` from your regular account. The setup requests elevation for missing Windows prerequisites when needed.
2. Select the application, WSL environment, cache, data and results directories. An empty application directory starts a new installation. A recognized installation offers update and repair. If Windows needs a reboot, restart and sign back in with the same account. The guided installer normally registers a one-time resume command there. If setup does not resume automatically, open **NewPat - Resume Setup** in the Start menu. Releases through 0.9.9 label that shortcut **NewPat - completa preparazione**.
3. Wait for archive verification, runtime preparation, diagnostics and self-tests. The completion message is **NewPat: ready**.
4. Launch NewPat from setup, the Start menu or the optional desktop shortcut. The Start menu also has a shortcut that opens the application folder. To check the prepared system, run the [installed application test](WINDOWS_INSTALLATION_TEST.md).

The setup includes its own Python bootstrap and downloads a verified application payload from GitHub. Future compatible payloads can reuse the saved installer. A newer bootstrap may be required if the installer contract changes. For a new network installation use the installer supplied on the release page.

The **NewPat** shortcut opens the stable installation. If a separate testing installation is present, its **NewPat Testing** shortcut opens that copy.

<a id="controlli-di-sicurezza-di-windows-e-del-browser"></a>

## Windows security and browser messages

The NewPat installer has no NewPat Authenticode signature. SHA-256 checks the identity of a download against the published file. Windows reputation and device policy are separate checks. Smart App Control may block the installer, its temporary Inno file (for example `NewPat-Setup.tmp`), an executable or a script. Distinguish this from browser download warnings, SmartScreen and antivirus detections.

If a file is blocked, keep the full message, filename, download source, version and time. Open **Event Viewer → Applications and Services Logs → Microsoft → Windows → CodeIntegrity → Operational** and look for nearby events, particularly 3077 (block) or 3076 (audit). The build's `windows-trust-check.json` records component hashes and observed signature states. Keep security controls enabled while gathering evidence. Managed devices may need administrator assistance.

For example, immediately after a failed launch, run this read-only query in PowerShell and look for the filename and timestamp that match your attempt:

```powershell
Get-WinEvent -FilterHashtable @{
    LogName = 'Microsoft-Windows-CodeIntegrity/Operational'
    Id = 3076, 3077
    StartTime = (Get-Date).AddHours(-2)
} | Select-Object TimeCreated, Id, Message | Format-List
```

If the event names a temporary setup executable, include both that filename and the name of the downloaded EXE when reporting the problem. If no matching event appears, retain the original warning so the reviewer can identify which Windows or browser component issued it. The ZIP has a separate installation procedure below; its scripts and embedded executables are also subject to device policy.

<a id="zip-completo-aggiuntivo"></a>

## Complete ZIP installation

1. From the published release, download `NewPat-<version>-Windows-complete.zip` (through 0.9.9 the suffix is `-Windows-completo.zip`) and compare its SHA-256 with `SHA256SUMS`. In PowerShell, use `Get-FileHash -Algorithm SHA256 -LiteralPath` followed by the actual download path.
2. Extract the entire archive into its final location on a local fixed disk. Close the compressed-folder view and open the extracted files.
3. Run `1_INSTALL.cmd` (`1_INSTALLA.cmd` in 0.9.9) as your regular user. Wait for **NewPat: ready**, including any required restart.
4. If Windows asks for a reboot, restart, sign back in and open `NIPAT\NewPat.lnk` **inside the extracted folder** to resume ZIP preparation. Once ready, the same shortcut opens the application. A normal first installation from the ZIP also opens NewPat when preparation succeeds.

Keep the extracted `NIPAT` directory. After preparation it contains `current.json`, which identifies the active version and full source commit, plus the data and results. For the installed test use [these ZIP-specific instructions](WINDOWS_INSTALLATION_TEST.md#complete-zip). The ZIP installs no Start menu shortcut. Python and scientific archives are included, but missing Windows prerequisites may still require a connection. Copying the folder to a different PC does not transfer its registered WSL environment.

| Item | Location under the extracted `NIPAT` directory |
| --- | --- |
| Version directories | `versions\<version>-<commit>` |
| WSL environment and archive cache | `wsl` and `cache` |
| Data, results and menu preferences | `data`, `runs`, `preferences.json` |
| Launcher and preparation log | `NewPat.lnk`, `versions\<version>-<commit>\.runtime\installer\setup.log` |

If Windows blocks the downloaded command file, first verify the original release ZIP checksum. For a verified archive, Windows may offer **Properties → Unblock → Apply** on the ZIP. Extract it into a fresh directory after applying the change. The bundled `README.txt` describes the checksum and extraction procedure for that package. Removing the internet-origin mark does not sign the files or override Code Integrity policy.

**Testing a candidate from Actions.** Extract the GitHub artifact first. The full Windows build artifact (`nipat-windows-setup`) also contains an EXE, a payload ZIP and build reports. Open the inner `NIPAT-<version>-Windows-complete.zip`, extract it into its own permanent directory and follow steps 2–4 above. The Windows ZIP-only artifact (`newpat-windows-review-zip`) supplies the same type of inner archive. Its `windows-zip-build.json` records the exact ZIP filename, SHA-256, version and source commit for comparison. [Review builds](CI_CD.md)

**If you already installed a candidate with the stable version number.** Compare `source_commit` in the active `NIPAT\current.json` with the full commit of the published release tag. Automatic updates look for higher version numbers. When the commits differ, the ZIP installer also rejects installation over that candidate in the same root. To use the published ZIP, close NewPat, extract it into a separate permanent directory and follow steps 2–4. Keep the candidate directory and its data and runs. The new installation has its own folders. To view an existing experiment, use **Open folder** in the results archive and select its existing run directory.

**Moving from 0.9.9.** The published 0.9.9 ZIP uses `1_INSTALLA.cmd`, `2_AVVIA.cmd` and `LEGGIMI.txt`. Its updater expects those exact archive members. The first move to the English layout requires the new ZIP. Close NewPat, extract that ZIP into a fresh temporary directory and open PowerShell there. Set the existing installation path to the directory that contains your `installation.json`, `data` and `runs`, then run:

```powershell
$existingRoot = (Read-Host 'Full path to your existing NIPAT installation folder').Trim('"')
if (-not (Test-Path -LiteralPath (Join-Path $existingRoot 'installation.json') -PathType Leaf)) {
    throw 'Select the existing ZIP installation folder that contains installation.json.'
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\app\installer\windows\install-zip.ps1 -BundleDirectory . -InstallRoot "$existingRoot" -OpenWhenReady
```

The installer checks ownership, uses the same data and runs directories and activates the new version after preparation succeeds. Launch subsequent sessions with `NewPat.lnk`. The command launchers are `2_LAUNCH.cmd` and `1_RESUME_SETUP.cmd`. For a guided EXE installation from 0.9.9, run the new `NewPat-Setup.exe` once. Choose the recognized installation when prompted.

ZIP updates retain the selected root, verify the download and activate the new version after successful preparation. Existing data from another root or installation channel remain where they were. Before removing a ZIP installation, preserve its data/results and identify its WSL distribution from the active backend. The ZIP has no Inno uninstaller.

### Verify an installed 0.9.9 upgrade

1. Before the upgrade, open a completed experiment in 0.9.9. Record its run directory, the SHA-256 of its `run.json` and the SHA-256 of one scientific result table. For each file, run `Get-FileHash -Algorithm SHA256 -LiteralPath '<full path>'` in PowerShell.
2. After upgrading, launch `NewPat.lnk` from the same installation root. Open the historical experiment, verify that the two paths and hashes match, and check the NewPat icon in the taskbar.
3. Use **Save example data** and open the extracted README at **Run the timing experiment**. Start two experiments with that workload and different names. Stop one while both are active. Record its run directory. Once it shows as interrupted, remove its card and let the other experiment finish.
4. Reopen NewPat. The interrupted card should stay hidden. Its run directory and any files already written should still exist. Open the completed experiment and check the reported genotypes against the timing workload's expected counts.

## Locations and ownership

| Resource | Default for the guided desktop installation |
| --- | --- |
| Application | `%LOCALAPPDATA%\Programs\NIPAT-Desktop` |
| WSL environment and cache | `%LOCALAPPDATA%\NIPAT-Desktop\wsl`, `%LOCALAPPDATA%\NIPAT-Desktop\cache` |
| Data and results | `%LOCALAPPDATA%\NIPAT-Desktop\data`, `%LOCALAPPDATA%\NIPAT-Desktop\runs` |
| Installation records | `%LOCALAPPDATA%\NIPAT-Desktop\installations` |
| Wizard preferences | `%LOCALAPPDATA%\NIPAT-Desktop\preferences.json` |
| WSL registration | Name beginning with `NIPAT-Desktop-`, tied to the verified filesystem and location |
| Setup resume on sign-in | `NIPAT-Desktop-ResumeSetup` RunOnce value |

The [installation profile](../installer/windows/install-profile.json) defines the channel (`desktop`), application identity and ownership checks. The five roots for the application, WSL, cache, data and results must be absolute, distinct, writable and non-nested on local fixed disks. Setup rejects reparse points, unsuitable system locations and conflicts with another installation. Use an empty or recognized application directory. For another nonempty directory, setup can offer an empty `NIPAT-Desktop` child after confirmation. Existing data and results may remain in the data directories.

Shortcuts invoke `2_LAUNCH.cmd`; `newpat.cmd` and the compatibility alias `nipat.cmd` invoke the terminal client. `scripts/windows/run.ps1` checks the ready state, installed manifest and selected runtime. The installed launcher uses its own backend settings. Preferences supply defaults to interactive use. For direct commands use `--data-dir` and `--runs-dir` before the subcommand.

## Updates, repair and diagnostics

**Check for updates** selects the download for the installed channel and method. The guided installation uses its saved verified setup and the release payload. The ZIP installation uses a full ZIP. Close active sessions when prompted. To complete an update after a reboot, use the resume action for your installation method described above.

The setup verifies hashes of both the scientific image archive and WSL filesystem. Inside the owned WSL distribution, `nipat-engine ensure` starts the included Docker Engine. Loading the archive resolves a local immutable Linux AMD64 image ID. The recorded build ID, archive digest and local image ID have distinct roles. Analyses use the verified local image with pulling disabled.

A matching owned WSL distribution and location can be reused. Changing the filesystem or location creates a separate distribution and retains the earlier environment. The roots selected for data/results become defaults and existing files stay in place. When an owned registration was removed manually, setup can reimport only if the prior destination is empty. It refuses an unrelated registration with the same name.

Setup verifies the candidate with `doctor --runtime` and `self-test`, activates the backend and writes `ready` last. For the guided installation use **NewPat - Resume Setup** after correcting a setup failure. For the complete ZIP, use its local `NIPAT\NewPat.lnk`. Retain these files for diagnosis:

| Evidence | Location |
| --- | --- |
| Phase, error and detailed setup log | `.runtime\installer\state.json` and `.runtime\installer\setup.log` under the application |
| Active backend | `.runtime\backend.json` |
| Diagnostics and self-tests | `doctor.stdout.log`, `doctor.stderr.log`, `self-test.stdout.log`, `self-test.stderr.log` and corresponding `*.exit-code.txt` files under `.runtime\installer` |
| Update handoff | `updates\handoff-*\handoff.log` and any `error.txt` under the configured cache |
| Previous state/backend | `.runtime\installer\recovery` |

A stderr message alone does not establish failure. Check the recorded exit code. Editing the state file does not repair the runtime. Inno copies application files before preparing the runtime, so an incomplete upgrade may block launch while a previous distribution still exists.

The managed-file inventory distinguishes distributed components from user files. Before replacing changed components, setup saves affected files, inventory and configuration in `%LOCALAPPDATA%\NIPAT-Desktop\installations\backups\<UTC-guid>`. It may use a validated legacy manifest if the previous inventory is absent. It removes obsolete managed files only after verifying the previous hash. An invalid new inventory stops preparation. Backups are selective and do not contain the complete Linux filesystem or user datasets.

## Maintenance and removal

**Environment and help → Installation and storage** displays owned resources and their sizes. Active resources and the most recent prior environment are protected. For the guided setup, the following PowerShell commands locate the installed launcher and display the inventory:

```powershell
$appDir = (Get-ItemProperty -LiteralPath 'HKCU:\Software\NIPAT\desktop' -Name app_dir).app_dir
$newpat = Join-Path $appDir 'newpat.cmd'
& $newpat installation inspect --json
```

To remove an item, enter an ID with `removable: true` from that inventory. NewPat checks ownership and asks for confirmation:

```powershell
$targetId = Read-Host 'Removable item ID from the inventory'
& $newpat installation cleanup --target $targetId
```

To repair the current installation when the inventory marks it recoverable, use:

```powershell
& $newpat installation recover --target current-installation
```

Repair validates the installed payload and resumes preparation, diagnostics and self-tests. Cleanup and repair require confirmation (or an explicit `--yes` for automation). The client hands off with exit code 85. Check the final outcome in `.runtime/maintenance/<id>/result.json` and the installer logs.

The uninstaller removes managed application files, shortcuts and automatic setup resumption. It retains data and results. A separate prompt offers removal of verified owned WSL and cache components, with **No** selected by default. **Cancel** stops before cleanup. A verification or removal error stops uninstallation and records the outcome in `%LOCALAPPDATA%\NIPAT-Desktop\installations\logs\uninstall-*.log`. Other distributions, Docker Desktop, unrelated files and the Windows WSL feature are outside this cleanup. User preferences, ownership records and some generated runtime files may remain for reinstallation.

## Resources

Resource settings distinguish physical memory, WSL's allocation and the container limit. Changes to the account's `.wslconfig` can affect all its WSL2 distributions. NewPat shows the proposed change, keeps a backup and requests confirmation. Restarting WSL is a separate action. Increasing the container limit alone cannot increase WSL memory. [Resource guide](RESOURCES.md)

## Development and verification

To run a source checkout with an already prepared, compatible installation, open PowerShell in the checkout root:

```powershell
$nipatApp = Read-Host "NewPat application directory"
$nipatBackend = Get-Content -Raw -LiteralPath (Join-Path $nipatApp '.runtime\backend.json') | ConvertFrom-Json
$env:NIPAT_BACKEND = 'wsl'
$env:NIPAT_WSL_DISTRO = $nipatBackend.wsl_distro
$env:NIPAT_RUNTIME_IMAGE = $nipatBackend.runtime_image
& '.\1_SETUP.cmd'
if ($LASTEXITCODE -ne 0) { throw 'Client preparation failed.' }
& '.\2_LAUNCH.cmd'
```

The source setup prepares the client with an explicit distribution and immutable `sha256:` image ID. It does not build the image or create a WSL filesystem. For independent development use a dedicated WSL distribution with `nipat-engine`, Docker Engine, Compose and the matching verified archive.

The [installer build](../.github/workflows/windows-installer.yml) packages the allowlisted source and binds the bootstrap, payloads and hashes in `installer-build.json`. Internal artifact names can retain the NIPAT identifier. The [acceptance protocol](INSTALLER_ACCEPTANCE.md), [CI guide](CI_CD.md) and [validation record](VALIDATION.md) describe what was tested. The bootstrap version and launcher version are recorded separately. Running the guided setup refreshes recognized shortcuts.

<a id="riparazione-dellautotest-cpin-della-0850"></a>

For an installation still on NIPAT 0.8.50, see the [historical CPIN self-test repair on GitHub](https://github.com/GregorioDalia/nipat-desktop/blob/main/docs/WINDOWS_INSTALLATION_TEST_0.8.50.md#correzione-locale-dellautotest-cpin).
