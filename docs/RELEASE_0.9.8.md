# NewPat 0.9.8

## Using the desktop

Choose **Start experiment** after reviewing the inputs and settings. NewPat checks the configuration and runtime before starting the analysis. The Activity view shows the current phase, sample when available, and elapsed time. Expand **Technical log** to inspect detailed messages.

Use the flags to select English or Italian. The information button beside the IGV viewer title opens the official IGV website in the system browser. References, alignments and results are displayed locally in NewPat. [Desktop guide](GUI.md)

## DNP execution

For a single indexed BAM with bounded depth, NewPat can assign two samtools processes to different chromosomes when the CPU limit and the estimated memory cost permit. The acquisition decision uses the resources assigned to the run. The subsequent R calculation chooses its own worker pool. [Resource settings](RISORSE.md)

In a Windows/WSL benchmark on the installed 0.9.7 engine, the test harness assigned one or two samtools processes to a 3.43 GiB BAM with 22 target chromosomes. Each run had four CPUs, 3,905 MiB of memory and the same 106 blocks for four R workers. The following times apply to that machine and sample.

| Processes in execution order | Pileup | Complete DNP analysis¹ |
| ---: | ---: | ---: |
| 1 | 186.5 s | 297.3 s |
| 2 | 100.7 s | 215.2 s |
| 2 | 100.2 s | 212.2 s |
| 1 | 403.0 s | 519.1 s |

¹ Elapsed time excludes the harness's final pileup checksum. The first pair saved 82.2 seconds overall. The final single-process run took longer during pileup for reasons the measurements could not establish. The maximum sampled container memory while processing target chromosomes was 703 MiB with one process and 803 MiB with two. The two DNP tables and the raw pileup had identical SHA-256 digests across all four runs. These measurements guided the scheduling change. They describe the instrumented Windows benchmark.

## Downloads

Choose the guided setup or complete ZIP for Windows x64, the Apple Silicon or Intel package for macOS 14 or later, or the Debian package for Ubuntu 24.04 LTS x86_64. Published assets include checksums. [Downloads](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.8) · [Installation guides](DISTRIBUZIONE.md)
