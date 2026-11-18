# Install NewPat on macOS

NewPat supports **macOS 14 or later** on Intel and Apple Silicon. Choose the package for the Mac's processor from the [stable release](https://github.com/GregorioDalia/nipat-desktop/releases/latest). In **Apple menu → About This Mac**, an Apple M-series chip means Apple Silicon.

| Processor | NewPat 0.9.7 package | Scientific runtime |
| --- | --- | --- |
| Apple Silicon | `NewPat-0.9.7-macos-arm64.pkg` | ARM64 Lima guest running the Linux AMD64 image with Rosetta |
| Intel | `NewPat-0.9.7-macos-x86_64.pkg` | AMD64 Lima guest running the Linux AMD64 image |

The package includes native Python and Lima, the graphical application, CLI and scientific image. The first launch needs virtualization, internet access for guest preparation and sufficient storage for the application, VM disk, image, input files and results. Homebrew, Docker Desktop and separate R or samtools installations are unnecessary.

## Install and start

1. Download the PKG for your architecture and compare its checksum with the release checksum.
2. Double-click the PKG and follow Installer. NewPat packages have no Apple Developer ID signature or notarization. If macOS reports that it cannot verify the package, dismiss the dialog, open **System Settings → Privacy & Security**, find the blocked item and choose **Open Anyway** if your device policy allows it. The app may need its own approval on first launch. [Apple's instructions](https://support.apple.com/en-us/102445)
3. Open **NewPat** from Applications. Keep the preparation window open while the application creates its dedicated Lima environment, imports the verified image and checks engine contracts.
4. When the main window opens, create an experiment or open previous results. Later launches reuse the prepared environment. Analyses run locally with networking disabled in each analysis container.

An error during preparation leaves the environment unready. Record the message and package identity. On a managed Mac, involve the administrator if policy blocks installation.

## Application, data and mounts

| Item | Default location |
| --- | --- |
| Application | `/Applications/NewPat.app` |
| Command-line launcher | `/Applications/NewPat.app/Contents/Resources/NewPat.command` |
| User files | `~/Library/Application Support/NIPAT-Desktop` |
| Data, runs and preferences | `data/`, `runs/` and `preferences.json` under the user directory |
| Runtime information and setup log | `.runtime/macos/runtime.json` and `.runtime/macos/setup.log` under the user directory |
| Lima home and instance | `~/.nipat/lima`, instance `nipat` |

In Finder, press **Shift–Command–G**, paste the user directory and press Return. Technical NIPAT names and the older `NIPAT.command` alias preserve access for existing installations. The dedicated VM has an ownership record and is separate from other Lima or Docker Desktop environments.

The VM shares the user's home, `/Volumes`, `/private/tmp` and the account's temporary directory with read/write access. The app directory is mounted read-only when outside the home directory. Each analysis container gets only its selected inputs, read-only, and its run directory with write access. macOS permissions still apply to protected folders and external volumes.

Use `--data-dir` or `--runs-dir` before an analysis command to select destinations. To add a shared location, close other NewPat sessions, finish active analyses and run:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime prepare --mount "/path/to/data"
```

The launcher also checks mounts when the application moves. It verifies VM ownership, preserves custom mounts and existing resource allocations, and can stop and restart the idle VM. A `mount-backup-*.json` file in `.runtime/macos` records the previous configuration and ownership information for recovery. Preparation verifies the current app manifest through the VM before marking it ready.

<a id="cli-e-diagnostica"></a>

## Command line and diagnostics

```bash
newpat_cli="/Applications/NewPat.app/Contents/Resources/NewPat.command"
"$newpat_cli" --runtime status
"$newpat_cli" --runtime ensure
"$newpat_cli" doctor --runtime
"$newpat_cli" self-test
"$newpat_cli" wizard
```

Initial preparation checks the archive and engine contracts. Run `self-test` explicitly for the numerical examples. `--runtime status` can report `repair_required` for a mount mismatch. After fixing the cause, reopen the app or use `--runtime prepare`. Keep the full error, setup log, macOS version, architecture and package identity when reporting a problem. After analyses finish, `--runtime stop` stops the dedicated VM.

## Updates, resources and removal

Use **Check for updates** or download a newer PKG for the same architecture. Close existing NewPat/NIPAT sessions before running Installer. The app bundle and account's data directory are separate.

The resource settings show host, Lima VM and container allocations. Preview any change to Lima RAM or CPUs and confirm it. NewPat backs up the previous configuration. A necessary restart has its own confirmation and active analyses block maintenance. Increasing the container limit alone cannot increase Lima's assigned RAM. [Resource guide](RISORSE.md)

Removing the app bundle leaves its VM and user files in place. To remove the owned VM as well, close all analyses and run the following **before** removing the application:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime remove-runtime
```

A later preparation will recreate the runtime. Data and results stay in the user directory. Native PKG checks and mount-migration simulations cover packaging and recovery logic. Results for an actual Lima VM, Finder interactions, Gatekeeper or Rosetta belong to the tested device and architecture. See the [validation record](VALIDAZIONE.md), [user guide](GUIDA_UTILIZZO.md) and [release notes](https://github.com/GregorioDalia/nipat-desktop/releases).
