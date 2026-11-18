# NIPAT Desktop 0.8.10 — integrated prototype

This development candidate combined DNPcall optimizations with progress indicators. [0.8.9](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.9) remained official. The updater did not offer the 0.8.10 candidate on the stable channel.

## Identifying a candidate

Select a successful [Installers (review build)](https://github.com/GregorioDalia/nipat-desktop/actions/workflows/windows-installer.yml) from `release/0.8.10-test` and match its commit to the candidate under test. The `installer-required` summary links the verified platform packages.

| Platform | Package |
| --- | --- |
| Windows x64 | `NIPAT-Setup.exe` |
| Ubuntu 24.04 x86_64 | `nipat-desktop_0.8.10_amd64.deb` |
| macOS Apple Silicon | `NIPAT-0.8.10-macos-arm64.pkg` |
| macOS Intel | `NIPAT-0.8.10-macos-x86_64.pkg` |

Actions artifacts are temporary. Retain the installer, commit, build and checksum. Multiple candidates can share the number `0.8.10`. A successful build does not exercise each target workstation. Installing manually upgrades a recognized **NIPAT Desktop** installation in place. Close active analyses and preserve reference runs. Platform requirements are in the [Windows](INSTALLATORE_WINDOWS.md), [Ubuntu](INSTALLATORE_LINUX.md) and [macOS](INSTALLATORE_MACOS.md) guides. Windows uses dedicated WSL2 and NIPAT-managed Docker Engine, macOS uses Lima, and Ubuntu uses local Docker Engine. R remains the scientific core.

## Changes

| Area | Behavior |
| --- | --- |
| DNPcall preparation | When a BAM index is available, select reads for the requested regions before producing the pileup. Preserve BED, `mpileup` options, maximum depth, BAQ and scientific filters. A missing index allows sequential scanning. A present but unusable index raises an error. |
| R processing | Index pileup rows and read groups of complete DNP windows, releasing consumed data. Preserve global type inference, locus identity and calculation/output order. If existing rules couple windows, use one block for the sample. |
| Intermediate storage | Use a temporary anonymous volume on the runtime's Linux filesystem. The BAM remains on a read-only mount. Large intermediates stay off the RAM disk. |
| Progress | Show phase, sample and elapsed time even without diagnostics. Report counts when the phase has a measurable total. |

Ordinary blocks target **64 loci and 8 MiB of raw pileup rows**. Complete windows and groups with the same effective position are indivisible, including when they exceed either target. Overlapping windows can share observations. Each block includes all data needed for its loci. The 8 MiB target describes raw input, leaves reads intact and is independent of R's actual memory use.

Preflight detects two cases where existing grouping rules can link windows: pileup coordinates that cannot be matched under those rules, and repeated QNAMEs within one pileup row. Both select one whole-sample block and record the reason in `work/dnp-blocks.json`. This preserves semantics but can require full-sample memory. Reusing a QNAME across different loci is insufficient to trigger fallback. Blocks of one sample execute serially. Existing cross-sample parallelism is bounded by the sample count.

For a single indexed BAM, selection and pileup use a pipeline. With multiple BAMs, indexed selections are staged on Linux disk in sample order. Overlapping phase durations must not be added. Total elapsed time includes intermediate preparation.

Results and logs persist in the run directory. Processing removes temporary intermediates at completion. The client collects container diagnostics before removing the owned container and anonymous volume. Interrupted-run recovery verifies ownership before cleanup.

Resource settings distinguish saved, effective, suggested and new values. **Enter keeps the current value.** Additional CPUs can affect a single-BAM run only through its actual workload. Compare total time including I/O, preparation and plotting.

Progress events identify preparation, BAM reading, DNP calculation, plotting and output verification/export. Elapsed time advances even while R writes no log lines. The prototype provides no remaining-time estimate. Structured events and snapshots are available for a future GUI.

| Path | Recorded information |
| --- | --- |
| `work/dnp-pileup.json` | Access strategy, selection and pileup times, intermediate and pileup sizes. Unmeasured counts are absent or null. |
| `work/dnp-blocks.json` | Index reading, block limits, any compatibility fallback, processed loci/rows/bytes, timings per sample and block. |
| `progress/` in the run directory | Per-process progress events, including when performance diagnostics are disabled. |

In automatic workflows the DNP step contains both reports. Progress events are separate from CPU and memory monitoring.

## Comparing a first run with archived results

1. Verify `NIPAT 0.8.10`, record the package commit and build, then run **8 — Verifica ambiente**.
2. Choose a previously analyzed BAM and reuse the exact FASTA, panel, parameters, input verification and resource limits. Choose a fresh run directory.
3. Match the reference's diagnostic setting. An additional short run with ordinary **Avvia analisi** checks progress indicators with diagnostics disabled.
4. Compare individual tables, summaries, display tables and PDFs first. Distinguish PDF content and rendering from creation metadata. Development checks also compare unrounded R quantities and, for indexed access, pileup bytes.
5. Compare end-to-end and phase durations including all intermediate reading, writing and copying. Distinguish the whole-container peak from R's partial **Peak RAM** readings. Retain the entire run even after failure or cancellation.

A suitable archived reference with results and metadata can avoid rerunning an old release. Account for cache, load and resource differences before attributing timing changes to code. See the [performance guide](PERFORMANCE.md). Test cancellation on a new run using **Ctrl+C**. Verify return to the menu, interrupted status and preservation of partial outputs. Keep previously successful runs intact.

## Evidence and versioning

The build links the commit, scientific image, installers and reports. Read the actual job outcomes and artifacts. Skipped checks remain distinct from passes. Synthetic equivalence applies to executed cases. End-user system tests and real data are separate. In particular, checking a Mac package does not exercise a complete Lima/Rosetta VM. Measure performance on the target system. Keep private BAMs, real-sample outputs and run archives off GitHub. Logs and metadata can reveal sample names and local paths.

Multiple builds could use 0.8.10 before release. Testing a different same-version candidate requires a manual download because the updater compares versions. Published releases are immutable. A later official package requires a higher version. SNP 2.0 and the fifth R module were deferred until the scientific scripts became available.
