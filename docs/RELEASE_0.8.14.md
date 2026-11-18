# NIPAT Desktop 0.8.14

This release introduced serial and automatic execution, a configurable process limit, and chromosome-parallel DNP pileup. One global queue serves sample/block tasks across any number of BAMs, including batches with more samples than available processes.

## Execution

Available workers can take the next block without waiting for an entire sample to finish. Reassembly preserves sample, locus and result order. Serial mode, process ceilings and memory limits apply to the whole queue. Blocks requiring global compatibility stay intact. Pileup preserves canonical chromosome order and provides a serial fallback. Acquisition completes before R processing begins.

SNPcall, Contamination and CPI use bounded parallelism. CPI reuses informative rows in its summary. Readers and numerical libraries respect the global budget, including in serial mode. Scientific formulas and filters are unchanged. Docker monitoring distinguishes a normal container exit from parsing failures and labels a run too short for external samples as unobserved.

Global CLI options precede the analysis command.

```powershell
.\nipat.cmd --execution-mode serial dnp-call --bam sample.bam --reference genome.fa --panel DNP_list.txt
.\nipat.cmd --execution-mode auto --max-workers 4 dnp-call --bam sample-a.bam --bam sample-b.bam --bam sample-c.bam --reference genome.fa --panel DNP_list.txt
```

Repeat `--bam` or provide a file list with `--bamlist`. The menu summary exposes the same controls. The maximum process count is a ceiling. The initial block targets are 32 MiB of raw input and 64 loci. R memory use also includes the data structures built from that input.

## Benchmarks and verification

The [earlier 0.8.14 candidate measurements](https://github.com/GregorioDalia/nipat-desktop/blob/main/docs/validation/0.8.14-observed-benchmarks.json) at `e04ff883fc6417748174d2a7c3b49cadad989308` cover 42 Windows/WSL runs. DNP and Contamination used real inputs. SNP and CPI used small examples. Serial and automatic DNP, SNP and Contamination tables matched. The informative CPI check also verified expected numerical results.

| Earlier candidate workload | Serial median (s) | Automatic median (s) |
| --- | ---: | ---: |
| First BAM alone | 377.649 | 122.849 |
| Second BAM alone | 191.161 | 68.071 |
| Both BAMs together | 623.327 | 291.771 |

The combined R phase used two workers, compared with five for one sample. This motivated the new shared queue. Its speedup still needed measurement. The real inputs are outside the repository, and the earlier manual installer test applies to that build only.

Differential checks use frozen 0.8.5 tables, unrounded R quantities and PDFs, supplemented by resource-budget, multi-sample and monitoring-shutdown tests. Build evidence identifies the shipped commit and image. Large SNP/CPI inputs and the global DNP indexing phase require separate profiling.

## Installation

Choose a package from the [0.8.14 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.14).

| System | Package |
| --- | --- |
| Windows 10 22H2 x64 / Windows 11 x64 | `NIPAT-Setup.exe` |
| macOS 14 or later, Apple Silicon | `NIPAT-0.8.14-macos-arm64.pkg` |
| macOS 14 or later, Intel | `NIPAT-0.8.14-macos-x86_64.pkg` |
| Ubuntu 24.04 LTS x86_64 | `nipat-desktop_0.8.14_amd64.deb` |

Earlier stable versions offer **Check for updates**. Users of a candidate already labeled 0.8.14 must download the official installer manually because the updater compares version numbers. Finish active runs before upgrading. Data, preferences and results are preserved.

Windows uses managed Docker Engine under WSL2, macOS uses Lima with Rosetta on Apple Silicon, and Ubuntu uses local Docker Engine. Docker Desktop is optional. Packages lacked a recognized NIPAT signature and Mac notarization. End-device VM testing and scientific domain validation remain separate from package checks.
