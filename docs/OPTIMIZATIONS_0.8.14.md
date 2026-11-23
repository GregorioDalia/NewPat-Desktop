# DNP and CPI performance evidence for 0.8.14

## Multi-BAM work queue and diagnostics

The final 0.8.14 implementation shares a queue of sample/block tasks across all BAMs. With two samples and a budget of five processes, independent blocks can occupy up to five slots in total. When there are more samples than slots, the same queue schedules the work across the available processes. The coordinator restores sample and locus order before writing tables and plots.

CPU, memory, the configured maximum and serial mode bound the worker pool. Complete windows and compatibility groups stay together. Pileup preparation precedes the R calculation and uses the same overall ceiling. The two phases have separate pools and do not overlap.

The external collector distinguishes an empty Docker response during shutdown from an error on a running container. It confirms termination against the same container ID and verified ownership. Other errors retain fixed diagnostic codes. A short run with no samples has a missing memory measurement. The internal diagnostics are recorded separately.

In the DNP JSON report, global `processing_seconds` measures elapsed time for the shared queue. Each sample's interval extends from its first block to its last, and sample intervals may overlap. The individual sample log starts at preparation and includes time waiting for the queue and producing plots. Adding the individual durations would double-count concurrent work.

The [release notes](RELEASE_0.8.14.md) document distribution and scope. The [42 Windows/WSL observations](validation/0.8.14-observed-benchmarks.json) concern candidate `e04ff883fc6417748174d2a7c3b49cadad989308`, before the final multi-BAM changes. They informed the shared-queue revision. Installer performance requires measurements of the installer build itself.

## Reference implementations

The following records describe the first 0.8.14 candidate, based on 0.8.13. Each qualification report identifies the sources it tested. The scientific regression reference is **NIPAT 0.8.5**, commit `eafadf7002a9c7d7c1b9af9ccafc47d698a059e5`.

| Capability | Origin | Change tested in 0.8.14 |
| --- | --- | --- |
| Automatic or serial mode, maximum workers, configurable blocks | 0.8.12 | Additional readr thread limits and coverage of the native engine entry point. |
| Parallelism across the four R programs | 0.8.12 | Targeted optimization of the CPI summary. |
| DNP pileup preparation by chromosome | 0.8.13 | Retained the existing overall budget. |
| DNP block reads from the global index | 0.8.10, subsequently extended for parallel execution | Combined reads for byte-contiguous rows. |

The [R scheduling reference](PARALLELISM_0.8.12.md) and [pileup acquisition reference](PILEUP_0.8.13.md) describe the applicable execution paths. Contamination works by sample and, where appropriate, by row block. SNPcall keeps QNAME groups intact. CPI can distribute work across pairs, panels/cutoffs or threshold intervals. These levels are alternatives and do not create nested pools.

## Serial mode and the overall process limit

`--execution-mode serial` runs one compute task at a time. A single samtools process prepares the pileup, followed by serial R computation. Automatic mode selects concurrency based on effective resources and available tasks. `--max-workers N` sets an upper bound.

For example, a maximum of four can allow four concurrent chromosome tasks during acquisition and four concurrent R blocks afterwards. The client, Python, R coordinator and optional monitor may still be present. They are distinct from the scientific worker count. Serial mode applies to this analysis and leaves other applications alone.

The SNP panel reader calls `readr::read_tsv()` with `num_threads = 1L`, independent of the host readr option. The runtime sets `VROOM_THREADS=1` and applies thread limits to the native engine `run` entry point, desktop and JSON paths. Numerical library thread limits remain in force. These constraints also apply in automatic mode, where the application schedules parallel work using bounded processes.

## CPI summary

The CPI calculation produces the informative maternal rows for each pair and panel. The 0.8.14 summary reuses `out$madre_info` instead of filtering the original maternal table again, as 0.8.13 did. The calculation uses the same fetal-read and fetal-fraction formulae, checks for missing and positive values, and minimum of two reads.

Maternal keys already belong to the chosen panel. Joining them with the original paternal table selects the same paternal rows without a second panel filter. The arguments to `run_CPI_iteration()`, formulae, order of CPI products and duplicate handling remain the same. The expected saving depends on the number of pairs, panels, cutoffs and rows.

## DNP reading and indexing

The previous block reader called `seek()` and `readChar()` for each requested row. The alternative combines rows only when they are contiguous in file bytes and adjacent in request order. Each temporary read range targets up to 8 MiB, except for a single larger indivisible row. The configurable computation block has a separate default of **32 MiB / 64 loci**.

Requests may contain gaps, repeated rows or reverse order. The reader preserves the request without sorting or deduplicating row indices. If no two requested rows are adjacent it uses the individual-read path directly. The same `read.csv()` parser consumes the bytes using column types inferred from the entire pileup. A warning or truncated combined read triggers individual-row reads to preserve the original handling of unusual bytes.

The global index still precedes block processing and performs QNAME and coordinate checks and type inference. Parsing, checking and type inference contribute separately to the cost of building the index. This test changed block reading and retained the existing index implementation.

## Helper microbenchmarks

The [local helper measurements](validation/0.8.14-microbenchmarks.json) isolate the operation being changed. They use synthetic data and exclude installer and full Windows/WSL workflow timing.

For CPI, each of two sessions included five repetitions of summary construction using the same previously computed CPI result. The second session also exercised the final reproducible harness. Timing excludes file reads, core calculation, plots and package loading. With 50,000 loci the median times were:

| Session | CPI selection | 0.8.13 | 0.8.14 |
| --- | --- | ---: | ---: |
| First session | Full panel | 36 ms | 21 ms |
| First session | Panel with 10% of loci | 16 ms | 10 ms |
| First session | ALL, no panel selection | 20 ms | 20 ms |
| Repeat with final harness | Full panel | 41 ms | 36 ms |
| Repeat with final harness | Panel with 10% of loci | 18 ms | 10 ms |
| Repeat with final harness | ALL, no panel selection | 22 ms | 22 ms |

The absolute improvement in the summary was small and varied across sessions. In the 5,000-locus ALL replay the median increased from 8 to 10 ms. The benchmark found identical R objects with `identical()` against 0.8.5 and 0.8.13. The exported tables and plot data/labels also matched byte for byte. Whole-program comparisons were qualified separately.

For DNP, the benchmark compared reading and parsing the same block over five alternating repetitions. Results matched. The table gives median timings.

| Synthetic block | Size | 0.8.13 | 0.8.14 |
| --- | ---: | ---: | ---: |
| 512 contiguous rows, depth 6,000 | 38.096 MiB | 1.292 s | 1.303 s |
| 20,000 contiguous rows, depth 4 | 1.335 MiB | 0.204 s | 0.039 s |
| 10,000 short rows with gaps | 0.668 MiB | 0.090 s | 0.085 s |

With deep rows, fewer reads had little effect on combined reading and parsing time. Many short contiguous rows showed the largest improvement. Rows with gaps used the direct path and showed only a small difference. These measurements do not establish the elapsed time of a real run or its index construction.

Three fresh R processes per method measured memory in the deep case. Median maximum RSS rose from **188.586 to 200.145 MiB**, an increase of about **11.56 MiB**. This is the peak of the R process reading the block after the index had already been constructed. The cumulative allocations measured about 114.9 MiB. They sum allocation activity rather than simultaneous resident memory.

An exploratory profile of index construction on the same deep fixture took 0.817 s. Of the 0.79 s sampled, `readLines()` and `strsplit()` accounted for 46.84% and 37.97% of self time, respectively. This single short run gives limited information about indexing real data.

## Qualification results

The [local 0.8.14 qualification](validation/0.8.14-rootless.json) identifies the tested sources by hash. It covered **20 cases, 64 scientific executions and 44 comparisons with 0.8.5**. Checks found byte-identical tables in 145 comparisons, identical unrounded scientific R objects, and identical rendered content on 137 PDF pages at 36 DPI, excluding PDF metadata. Ten focused R checks, 25 pileup acquisition cases and the R cancellation check also passed. Checksums confirmed that all 154 monitored source files and all 55 inputs were unchanged during the test.

Variants included serial, automatic, a maximum of two, a maximum of four and a repeat of the four-worker maximum. In cases exercising the R pool, the host selected one serial worker with no child PID, up to two workers at a maximum of two, and up to three in automatic mode or with a maximum of four. A CPI pair with two cutoffs used two workers because it provided only two tasks. Acquisition tests directly observed maxima of one, two and four samtools processes. Output ordering and repeatability were covered.

Tests used R 4.4.2 and samtools 1.21 on Linux with a relocated runtime and verified checkout sources. The environment did not run Docker or Windows/WSL and did not enforce container quotas. These results apply to the recorded cases and sources. Other checks completed included:

- A Python suite of 1,081 tests with four skipped, 224 CI script tests and the Ruff check. The CI script tests ran locally.
- Loading all four catalogs with full dependency verification, 17 catalog tests and checksum verification for all four R sources.
- Link checks on 55 Markdown files and the helper microbenchmarks reported above.

Build CI and installer qualification refer to the associated GitHub Actions build and commit. Real-data Windows/WSL trials measure phase times and whole-container memory separately. The [0.8.13 qualification](validation/0.8.13-rootless.json) is a separate historical reference.

<a id="collaudo-sugli-input-reali"></a>

## Real-input comparison protocol

1. Verify the installed version, commit and build. Keep the 0.8.13 candidate and earlier runs. A results directory name alone does not identify a build.
2. Keep inputs, scientific parameters, WSL/container resources, checksum policy and diagnostics fixed. Start with **32 MiB / 64 loci**.
3. In the analysis summary, choose **4 — Parallelism and blocks**, then run serial and automatic conditions under new names, for example `test0814-serial32-01` and `test0814-auto32-01`. The summary choice applies to this run.
4. Compare table contents and order with the scientific reference, 0.8.5. For timings use verified and comparable 0.8.13 runs. Where practical, alternate the conditions and repeat three times. Include failures and interruptions.
5. For DNP, distinguish acquisition, index construction and block computation. For CPI, record effective pairs, panels and cutoffs. The block reader is downstream of samtools and index construction.

Retain `run.json`, `execution.log`, `run-report.html`, the results, `work/` and, when available, `performance/`. The [performance guide](PERFORMANCE.md) explains which measures are comparable. Raw block MiB describe input size. R structures, process count and caching also affect resident memory.

Logs and results allow an initial comparison without transferring whole BAM and FASTA files. Original input may be needed to reproduce an unexplained failure or profile a particular workload. Keep sample files outside the source repository and distributed packages.
