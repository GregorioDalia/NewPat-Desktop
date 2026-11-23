# NIPAT Desktop 0.8.9

Release 0.8.9 reduced repeated calculations and allocations in all four R programs. Scientific parameters, formulas, filters, output formats and the application architecture retained their previous contracts. Optional performance diagnostics default to off.

## Changes

- **DNPcall** prepares pileup observations directly, uses a lookup table for qualities and reuses repeated extractions and locus indices. It avoids duplicate grouping and counting. Acquisition still scans the BAM sequentially with `samtools mpileup -l`. DNPcall parallelism operates across samples.
- **SNPcall** reads the necessary columns and aggregates read features while preserving global QNAME groups and compatibility for nonstandard observations.
- **CPI** reuses shared samples between consecutive pairs and results across thresholds that select identical loci. It reconstructs every row in the original product order.
- **Contamination** collects rows and assembles each final summary in one pass.
- **Resource configuration** distinguishes saved, effective, suggested and newly entered values. Enter keeps the current setting, including automatic selection. The literal command `:suggerito` applies the suggestion.

The [equivalence specification](OPTIMIZATION_0.8.9.md) defines comparisons with 0.8.5.

## Installation and updates

Choose a package from the [0.8.9 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.9).

| System | Download |
| --- | --- |
| Windows 10 22H2 x64 / Windows 11 x64 | [NIPAT-Setup.exe](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.9/NIPAT-Setup.exe) |
| macOS 14 or later, Apple Silicon | [NIPAT-0.8.9-macos-arm64.pkg](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.9/NIPAT-0.8.9-macos-arm64.pkg) |
| macOS 14 or later, Intel | [NIPAT-0.8.9-macos-x86_64.pkg](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.9/NIPAT-0.8.9-macos-x86_64.pkg) |
| Ubuntu 24.04 LTS x86_64 | [nipat-desktop_0.8.9_amd64.deb](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.9/nipat-desktop_0.8.9_amd64.deb) |

Users of 0.8.5 can choose **9 — Check for updates** or download the package. Finish active analyses before updating. Previous results and their metadata remain available. Windows uses WSL2 with managed Docker Engine, macOS uses Lima with Rosetta on Apple Silicon, and Ubuntu uses local Docker Engine. Docker Desktop is optional. Packages lacked a recognized NIPAT signature and Mac notarization. See the [Windows](WINDOWS_INSTALLER.md), [macOS](MACOS_INSTALLER.md) and [Ubuntu](LINUX_INSTALLER.md) guides for installation and removal.

## Qualification and versioning

Differential tests run the frozen 0.8.5 R reference and candidate in the same runtime. They compare table bytes, unrounded intermediate values and rendered PDFs for the covered cases. Targeted tests check DNPcall and SNPcall transformations and CPI calculations. Separate domain validation is needed to assess other inputs.

CI and installer builds verify the client, workflow contracts, scientific regressions, image integrity and packaged contents. The 0.8.9 acceptance record identifies the revised R sources, commit, image, build, installers and test evidence. Hosted Mac tests cover clients and packages. Dedicated Lima/Rosetta tests on the two architectures remained outstanding.

Microbenchmarks isolate operations on synthetic data and omit some workflow costs. End-to-end time on real BAMs and peak container memory need direct measurement. The [performance guide](PERFORMANCE.md) distinguishes wall time, R time, container memory and partial R-process observations.

Commit, build and checksums identify candidates before publication. Published packages are immutable and subsequent official packages require a higher version. The updater compares version numbers, so a second build labeled 0.8.9 is invisible to clients already on 0.8.9. The planned 0.8.10 integrated prototype belonged to development testing outside the stable channel.
