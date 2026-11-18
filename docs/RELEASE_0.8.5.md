# NIPAT Desktop 0.8.5

This stable release added optional performance diagnostics for local analyses on Windows, macOS and Ubuntu. Diagnostics are off by default. The R scripts, parameters and algorithms retain their previous behavior.

## Measurements

Enable diagnostics from the menu summary or with `--performance-diagnostics`. The choice applies to one analysis. An external container observer and an internal engine monitor collect available CPU, memory, I/O and process measurements. Phase events use a monotonic clock for preparation, R execution, output verification and presentation.

The run's `performance` directory contains JSON summaries and JSONL samples. A dedicated section of `run-report.html` presents the results. Samples are written incrementally and missing or partial data are identified. Scientific outcome and monitoring outcome are recorded separately. The benchmark supervisor can collect diagnostics and records resources, inputs and repetitions.

## Installation

Choose the package for the operating system from the [0.8.5 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.5).

| System | Download |
| --- | --- |
| Windows 10 22H2 x64 / Windows 11 x64 | [NIPAT-Setup.exe](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.5/NIPAT-Setup.exe) |
| macOS 14 or later, Apple Silicon | [NIPAT-0.8.5-macos-arm64.pkg](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.5/NIPAT-0.8.5-macos-arm64.pkg) |
| macOS 14 or later, Intel | [NIPAT-0.8.5-macos-x86_64.pkg](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.5/NIPAT-0.8.5-macos-x86_64.pkg) |
| Ubuntu 24.04 LTS x86_64 | [nipat-desktop_0.8.5_amd64.deb](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.5/nipat-desktop_0.8.5_amd64.deb) |

The installer updates an existing **NIPAT Desktop** installation. See the [Windows](INSTALLATORE_WINDOWS.md), [macOS](INSTALLATORE_MACOS.md) or [Ubuntu](INSTALLATORE_LINUX.md) guide for installation, updates and removal. Packages lacked a recognized NIPAT signature and the Mac application lacked notarization.

## First measurement

1. Prepare the BAM and its index, the indexed FASTA for the same assembly and the DNP panel.
2. Open NIPAT, check for version `0.8.5` and choose **1 — DNPcall**.
3. Run the same inputs, parameters and resource limits once normally and once with performance diagnostics enabled.
4. Keep both result directories and open the diagnostics run's `run-report.html`. The [performance guide](PERFORMANCE.md) explains the measures and comparison protocol.

## Verification and interpretation

CI exercises collection in the scientific engine, compares DNP outputs with and without diagnostics against known synthetic results, and checks that observations survive an out-of-memory exit. Build evidence identifies the commit, package hashes and installer checks.

Use ordinary runs to estimate normal execution time because monitoring adds overhead. Periodic samples can miss peaks. Kernel counters, Docker statistics and process memory describe different quantities. Phase events cover only some operations inside R. Counter availability depends on the kernel, runtime and filesystem. CI applies no speed threshold on shared runners. Large BAM performance and full Lima/Rosetta operation on a Mac with virtualization require separate tests.
