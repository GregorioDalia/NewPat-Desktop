# Install NewPat on macOS

NewPat supports **macOS 14 or later** on Intel and Apple Silicon. Choose the package for the Mac's processor from the [stable release](https://github.com/GregorioDalia/nipat-desktop/releases/latest). In **Apple menu → About This Mac**, an Apple M-series chip means Apple Silicon.

| Processor | NewPat 0.9.9 package | Scientific runtime |
| --- | --- | --- |
| Apple Silicon | `NewPat-0.9.9-macos-arm64.pkg` | ARM64 Lima guest running the Linux AMD64 image with Rosetta |
| Intel | `NewPat-0.9.9-macos-x86_64.pkg` | AMD64 Lima guest running the Linux AMD64 image |

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

## Compare worker settings on an Apple Silicon Mac

The Apple Silicon installer uses a native ARM guest and runs the AMD64 scientific image through Rosetta. The starting Lima allocation is half the host RAM, capped at 8 GiB, and up to four CPUs, keeping one host CPU free when possible. An existing VM retains its own allocation. Check the actual values with the installed launcher:

```sh
"/Applications/NewPat.app/Contents/Resources/NewPat.command" resources inspect
```

When the AMD64 engine runs under Lima on Apple Silicon and the effective allocation is at most 4 GiB, DNP block processing automatically uses up to two R workers. The allocation includes the limits of the VM and of this run. Larger allocations use the regular CPU, task and memory estimates. In a three-repeat high-depth comparison on an 8 GiB M1 (0.9.5, four guest CPUs, 3,905 MiB effective), the median was 27.84 seconds at two workers, 36.09 at four and 29.87 in serial mode. The control and background profiles differed by less than 0.2 seconds across modes. These are synthetic DNP workloads. An explicit maximum in the experiment settings takes precedence, subject to the existing CPU and memory checks. Samtools determines its own concurrency before the R calculation.

When a single samtools process is admitted on this Mac configuration, its chromosome outputs go directly into the pending pileup in BAM dictionary order. This avoids writing and reading an extra complete copy on the VM's scratch disk. The new file is published after all chromosomes finish successfully.

Across these Apple Silicon allocations, a single BAM uses the established reader. For two or more BAMs, DNP decodes ordinary samtools tabular blocks directly and can share one read across up to four samples when their projected columns fit the worker budget. The original reader also handles unusual input or blocks above 32 MiB. When an indexed chromosome's target interval spans at most half its length and excludes at least 1 million bases, samtools can restrict its scan to that interval while retaining the complete BED mask. The archived nine-BAM panel was too dispersed for this latter optimization.

The Mac worker benchmark compares serial execution, automatic execution with a ceiling of two workers, and the default automatic policy. Add `--include-four` for an explicit four-worker ceiling. The report records how many workers actually overlapped in the R calculation and how many samtools processes overlapped during acquisition. Compare the R phase separately when the acquisition counts differ. [Mac worker benchmark](../scripts/benchmark_macos_dnp.py) Each run uses the same BAM list, reference, DNP panel and Lima allocation. The benchmark prepares the VM once before timing, records total command time, pileup, indexing, R processing and observed worker counts, and checks the individual scientific tables and the genotype matrix against serial execution.

The benchmark enables performance diagnostics for every condition. It saves the serial table checksums and the kernel and sampled container memory peaks when available. With the updated engine it also records block reads, logical input bytes, total time spent by workers reading and parsing, and total time spent on calculation. Workers can overlap. Use the calculation phase's elapsed time for timing comparisons. A stopped run can retain `work/dnp-block-progress.json` with the most recent totals for completed groups. **Export diagnostics** includes this file for standalone runs and workflow steps.

Save the script in Downloads. Prepare a text file with one BAM path per line in a fixed sample order. Start with one representative indexed BAM, the matching indexed reference and the same panel as the slow run. Keep the Mac connected to power, use the same storage and close other analyses. From Terminal, replace the input paths below with your own. Choose a new output directory for each invocation.

```sh
"/Applications/NewPat.app/Contents/Resources/python/bin/python3.12" -I \
  "$HOME/Downloads/benchmark_macos_dnp.py" \
  --bamlist "$HOME/NewPat-data/bams.txt" --reference "$HOME/NewPat-data/genome.fa" \
  --panel "$HOME/NewPat-data/dnp-panel.txt" --output-dir "$HOME/NewPat-Mac-test"
```

One round runs each selected condition once. For repeated measurements of the same representative multi-BAM list, use `--rounds 3` in a fresh output directory. The order rotates to reduce the effect of warmed file caches. `benchmark.json` reports each run and the median total time per setting. Compare the spread, actual samtools concurrency, phase times and scientific table agreement before choosing the setting. If automatic mode already uses one worker, inspect the acquisition reason and measured CPU/RAM first. Preserve the per-run logs if a run fails. Reports and logs remain local and can contain paths or sample names.

A separate VM-allocation comparison can then change either the Lima CPU count or its memory while holding worker mode and inputs fixed. For an Apple Silicon image built natively for ARM64, separate R/package and samtools builds plus scientific equivalence checks would be needed. The DNP benchmark above measures the installed AMD64 image.

## Updates, resources and removal

Use **Check for updates** or download a newer PKG for the same architecture. Close existing NewPat/NIPAT sessions before running Installer. The app bundle and account's data directory are separate.

The resource settings show host, Lima VM and container allocations. Preview any change to Lima RAM or CPUs and confirm it. NewPat backs up the previous configuration. A necessary restart has its own confirmation and active analyses block maintenance. Increasing the container limit alone cannot increase Lima's assigned RAM. [Resource guide](RESOURCES.md)

Removing the app bundle leaves its VM and user files in place. To remove the owned VM as well, close all analyses and run the following **before** removing the application:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime remove-runtime
```

A later preparation will recreate the runtime. Data and results stay in the user directory. Native PKG checks and mount-migration simulations cover packaging and recovery logic. Results for an actual Lima VM, Finder interactions, Gatekeeper or Rosetta belong to the tested device and architecture. See the [validation record](VALIDATION.md), [user guide](USER_GUIDE.md) and [release notes](https://github.com/GregorioDalia/nipat-desktop/releases).
