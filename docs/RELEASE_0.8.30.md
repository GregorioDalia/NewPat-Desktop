# NIPAT Desktop 0.8.30

This release integrated SNPcall 2.0 and revised result presentation. Publication followed qualification of the source, packages and associated test evidence.

## SNPcall 2.0

The scientific reference is [NEWPAT commit ce59f4be](https://github.com/lpistacchia/NEWPAT/tree/ce59f4beeeec710b1b42d425cb87d7aad729f71d/SNPcall). The [original R source](../tests/reference_r/2.0/SNPcall.R) is frozen unchanged.

- The caller reads `chr, pos, ref, alt` panels and legacy `pos, ref, alt` panels containing `chr:pos`.
- Input can be a BAM or a pileup with read names and qualities. Pileup generation uses `samtools -d 0` to remove the earlier default depth cap. Reads are grouped by SNP and QNAME, including overlapping windows.
- The 17-column table contains REF, ALT and Other counts, REF ratio, GL0/GL1/GL2, genotype, indel statistics and per-base counts. Outputs include per-sample plots, aggregate genotypes, missing-genotype counts, multi-sample UpSet plots, elapsed time and resident memory.
- `ratio` is REF/(REF+ALT). Genotype likelihoods use natural logarithms. When Other accounts for at least 10%, the genotype is missing and the counts and likelihoods remain available. Indel statistics examine the central base. Read exclusion examines the whole window. Zero coverage and missing estimates have distinct representations.

Optimizations select necessary columns, aggregate observations and keep worker counts within the CPU and memory budget. Serial operation remains available. Different SNP results from earlier releases may reflect the replacement of the scientific model. SNPcall 2.0 is the reference for this release.

## Presentation

DNP/SNP histogram bins begin at `0`, followed by `1–5`, `6–10` and subsequent intervals. Long panels and CPI plots span readable pages with bounded PDF dimensions. Summaries clarify units, missing genotypes and the interpretation of Contamination and CPI statistics. The presentation changes preserve DNPcall, Contamination and CPI formulas and tables.

## Verification

Acceptance compares SNP with original 2.0 and the other three modules with frozen 0.8.5. It checks exact tables and unrounded R values, varying qualities, overlapping windows, missing coverage, histogram bins and serial/parallel determinism. Updated PDFs must render, have the intended content and dimensions, and agree across modes. The 0.8.30-specific checks supplement earlier release requirements.

Local checks used R 4.5.0. Distribution qualification used R 4.4.2 with the image's pinned dependencies. The real 0.8.20 BAMs are outside the repository, so their recorded times belong to that version.

## Installation

Choose a package from the [0.8.30 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.30).

| System | Package |
| --- | --- |
| Windows 10 22H2 x64 / Windows 11 x64 | [NIPAT-Setup.exe](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.30/NIPAT-Setup.exe) |
| macOS 14 or later, Apple Silicon | [NIPAT-0.8.30-macos-arm64.pkg](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.30/NIPAT-0.8.30-macos-arm64.pkg) |
| macOS 14 or later, Intel | [NIPAT-0.8.30-macos-x86_64.pkg](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.30/NIPAT-0.8.30-macos-x86_64.pkg) |
| Ubuntu 24.04 LTS x86_64 | [nipat-desktop_0.8.30_amd64.deb](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.8.30/nipat-desktop_0.8.30_amd64.deb) |

Compatible clients, including 0.8.20, can use **Check for updates**. Finish active runs first. Recognized installations retain paths, preferences, data and results. New SNP runs use the 2.0 model. The Windows setup lacked a NIPAT Authenticode signature and Smart App Control qualification. Mac packages lacked notarization and required separate end-device Lima testing. See the [Windows](INSTALLATORE_WINDOWS.md), [macOS](INSTALLATORE_MACOS.md) and [Ubuntu](INSTALLATORE_LINUX.md) guides.
