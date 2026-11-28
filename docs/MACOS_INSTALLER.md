# Install NewPat on macOS

NewPat supports **macOS 14 or later** on Intel and Apple Silicon. Choose the package for the Mac's processor from the [stable release](https://github.com/GregorioDalia/NewPat-Desktop/releases/latest). In **Apple menu → About This Mac**, an Apple M-series chip means Apple Silicon.

| Processor | Release asset (match the version to the release tag) | Scientific runtime |
| --- | --- | --- |
| Apple Silicon | `NewPat-<version>-macos-arm64.pkg` | ARM64 Lima guest and Linux ARM64 scientific image (0.9.99 candidate) |
| Intel | `NewPat-<version>-macos-x86_64.pkg` | AMD64 Lima guest running the Linux AMD64 image |

The package includes native Python and Lima, the graphical application, CLI and scientific image. The first launch needs virtualization, internet access for guest preparation and sufficient storage for the application, VM disk, image, input files and results. Homebrew, Docker Desktop and separate R or samtools installations are unnecessary.

## Install and start

1. Download the PKG for your architecture and compare its checksum with the release checksum.
2. Double-click the PKG and follow Installer. NewPat packages have no Apple Developer ID signature or notarization. If macOS reports that it cannot verify the package, dismiss the dialog, open **System Settings → Privacy & Security**, find the blocked item and choose **Open Anyway** if your device policy allows it. The app may need its own approval on first launch. [Apple's instructions](https://support.apple.com/en-us/102445)
3. Open **NewPat** from Applications. Keep the preparation window open while the application creates its dedicated Lima environment, imports the verified image and checks engine contracts.
4. When the main window opens, create an experiment or open previous results. In 0.9.10, **Environment and help → Open demo** prepares a first experiment with the bundled inputs. Review the draft and start the analysis. [First experiment in Italian](QUICKSTART_IT.md)

Later launches reuse the prepared environment. Analyses run locally with networking disabled in each analysis container.

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

After an update under the same application path, a running VM can still see the previous bundle. If the installed manifest is valid on the Mac and missing or stale inside the VM, preparation requests exclusive access, checks for running containers, and restarts the idle VM once to refresh the share. If another NewPat session is using the runtime, finish its work, close it and reopen NewPat.

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

## Compare worker settings on an Apple Silicon Mac

The 0.9.99 candidate uses native Linux ARM64 R and samtools. The launcher disables Rosetta in the owned guest when upgrading from 0.9.10. It checks for active containers before stopping the VM and retains its disk, mounts and resource allocation. The starting Lima allocation is half the host RAM, capped at 8 GiB, and up to four CPUs, keeping one host CPU free when possible. An existing VM retains its own allocation. Check the actual values with the installed launcher:

```sh
"/Applications/NewPat.app/Contents/Resources/NewPat.command" resources inspect
```

On Apple Silicon with an effective Lima allocation of at most 4 GiB, DNP block processing automatically uses up to two R workers. The allocation includes the limits of the VM and of this run. Larger allocations use the regular CPU, task and memory estimates. In a three-repeat high-depth comparison on an 8 GiB M1 (0.9.5, four guest CPUs, 3,905 MiB effective), the median was 27.84 seconds at two workers, 36.09 at four and 29.87 in serial mode. The control and background profiles differed by less than 0.2 seconds across modes. These are synthetic DNP workloads. An explicit maximum in the experiment settings takes precedence, subject to the existing CPU and memory checks. Samtools determines its own concurrency before the R calculation.

When a single samtools process is admitted on this Mac configuration, its chromosome outputs go directly into the pending pileup in BAM dictionary order. This avoids writing and reading an extra complete copy on the VM's scratch disk. The new file is published after all chromosomes finish successfully.

Across these Apple Silicon allocations, a single BAM uses the established reader. For two or more BAMs, DNP decodes ordinary samtools tabular blocks directly and can share one read across up to four samples when their projected columns fit the worker budget. The original reader also handles unusual input or blocks above 32 MiB. When an indexed chromosome's target interval spans at most half its length and excludes at least 1 million bases, samtools can restrict its scan to that interval while retaining the complete BED mask. The archived nine-BAM panel was too dispersed for this latter optimization.

The Mac worker benchmark compares serial execution, automatic execution with a ceiling of two workers, and the default automatic policy. Add `--include-four` for an explicit four-worker ceiling. The report records how many workers actually overlapped in the R calculation and how many samtools processes overlapped during acquisition. Compare the R phase separately when the acquisition counts differ. Each run uses the same BAM list, reference, DNP panel and Lima allocation. The report records total command time, pileup, indexing, R processing and observed worker counts, and checks the individual scientific tables and genotype matrix against serial execution. [Mac worker benchmark](../scripts/benchmark_macos_dnp.py)

`initial_prepare_seconds` measures the explicit VM preparation before the timed runs. Each run's `wall_seconds` includes the launcher's own startup checks. When timestamps are available, `startup.launcher_to_first_command_seconds` measures time from invoking the launcher to the first scientific command recorded by the client. It includes preparation, input checks and runtime verification. Two components are reported separately within that interval: `runtime_ensure_seconds` for the Lima check (including lock wait) and `engine_describe_seconds` for the client's subsequent engine probe.

The benchmark enables performance diagnostics for every condition. It saves the serial table checksums and the kernel and sampled container memory peaks when available. With the updated engine it also records block reads, logical input bytes, total time spent by workers reading and parsing, and total time spent on calculation. Workers can overlap. Use the calculation phase's elapsed time for timing comparisons. A stopped run can retain `work/dnp-block-progress.json` with the most recent totals for completed groups. **Export diagnostics** includes this file for standalone runs and workflow steps.

Save the script in Downloads. Prepare a text file with one BAM path per line in a fixed sample order. Start with one representative indexed BAM, the matching indexed reference and the same panel as the slow run. Keep the Mac connected to power, use the same storage and close other analyses. From Terminal, replace the input paths below with your own. Choose a new output directory for each invocation.

```sh
"/Applications/NewPat.app/Contents/Resources/python/bin/python3.12" -I \
  "$HOME/Downloads/benchmark_macos_dnp.py" \
  --bamlist "$HOME/NewPat-data/bams.txt" --reference "$HOME/NewPat-data/genome.fa" \
  --panel "$HOME/NewPat-data/dnp-panel.txt" --output-dir "$HOME/NewPat-Mac-test"
```

One round runs each selected condition once. For repeated measurements of the same representative multi-BAM list, use `--rounds 3` in a fresh output directory. The order rotates to reduce the effect of warmed file caches. `benchmark.json` reports each run and the median total time per setting. Compare the spread, actual samtools concurrency, phase times and scientific table agreement before choosing the setting. If automatic mode already uses one worker, inspect the acquisition reason and measured CPU/RAM first. Preserve the per-run logs if a run fails. Reports and logs remain local and can contain paths or sample names.

A separate VM-allocation comparison can then change either the Lima CPU count or its memory while holding worker mode and inputs fixed. The DNP benchmark measures the engine in the installed package. The [Apple Silicon candidate trial](MACOS_CANDIDATE_TEST.md) compares the two callers with the existing 0.9.10 timings.

## Updates, resources and removal

Use **Check for updates**, then **Download and verify**. After verification the desktop shows the full path to the PKG. Choose **Show in Finder**, wait for running experiments to finish and quit all NewPat/NIPAT sessions. Open the selected PKG in Finder to start Installer. The app bundle and the account's data directory are separate.

**Installing over an earlier version.** Open the PKG and then launch NewPat from Applications. A download from GitHub and a verified download from the app use the same macOS Installer. NewPat normally reuses the existing VM.

The published 0.9.10 launcher can stop at a missing `owner.json` when an older Lima instance is still present. In builds with automatic recovery, the first launch checks the stopped instance against NewPat's original provisioning configuration. If it matches, NewPat moves that instance to a private `~/.nipat/recovered-nipat-…/nipat` directory, records the location in `.runtime/macos/setup.log` under the user directory, and prepares a fresh VM. Allow the usual first-launch setup to finish. Existing experiments remain in the user data directory. If the old VM is running, protected, or cannot be identified, preparation stops and the log records the reason.

**Moving from a candidate to a stable build with the same version number.** The updater only offers higher version numbers. Compare `source_commit` in `/Applications/NewPat.app/Contents/Resources/app/.distribution/macos-manifest.json` with the full commit of the published release tag. If they differ, download the published PKG for your architecture, verify its SHA-256 against the release checksums, close NewPat and run Installer. Recheck the installed manifest before recording stable-build test results.

The resource settings show host, Lima VM and container allocations. Preview any change to Lima RAM or CPUs and confirm it. NewPat backs up the previous configuration. A necessary restart has its own confirmation and active analyses block maintenance. Increasing the container limit alone cannot increase Lima's assigned RAM. [Resource guide](RESOURCES.md)

Removing the app bundle leaves its VM and user files in place. To remove the owned VM as well, close all analyses and run the following **before** removing the application:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime remove-runtime
```

A later preparation will recreate the runtime. Data and results stay in the user directory. Native PKG checks and mount-migration simulations cover packaging and recovery logic. Results for an actual Lima VM, Finder interactions, Gatekeeper or Rosetta belong to the tested device and architecture. See the [validation record](VALIDATION.md), [user guide](USER_GUIDE.md) and [release notes](https://github.com/GregorioDalia/NewPat-Desktop/releases).
