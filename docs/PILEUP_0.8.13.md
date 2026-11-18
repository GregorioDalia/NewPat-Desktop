# Parallel pileup acquisition in candidate 0.8.13

Version 0.8.13 extended parallel execution to **DNP pileup preparation**. NIPAT 0.8.5 remained the scientific reference under the [differential test contract](../tests/r_optimization/README.md). This record covers the candidate and its qualification protocol. Real-data speed and installer validation were separate tests.

## Why acquisition was investigated

A 0.8.12 DNP run with one BAM and 845 loci produced these timings:

| Stage | Duration |
| --- | ---: |
| Pileup acquisition | 148.155 s |
| Scanning and indexing | 16.292 s |
| Block computation with five R workers | 41.918 s |
| Other operations in the run | 9.709 s |
| Total | 216.074 s |

An earlier serial 0.8.10 run with 32 MiB blocks took 298.676 s. These single observations motivated work on acquisition. The four exported table files matched byte for byte across the two runs. Neither observation measured 0.8.13. The real-data comparison against 0.8.5 was still outstanding. Identifying data and run archives were kept outside the repository.

## Preparing one chromosome at a time per worker

With an index for every BAM and compatible reference dictionaries, the preparation stage creates a task per panel chromosome. Each task starts **one `samtools mpileup` process** for that chromosome and its requested positions. Sample order, scientific options, filters, BAQ and depth limit stay fixed. A DNP window stays in a single task.

Workers write partial results to Linux scratch. Assembly follows the BAM `@SQ` dictionary order regardless of task completion order. The complete file goes through the existing index and R calculation. Type inference and global QNAME and coordinate checks still precede block computation.

Chromosome selection has an I/O tradeoff. `mpileup -r` can read and decode more off-panel alignments than the 0.8.12 multi-interval `view -M -L` preselection. The BED filter still runs before BAQ. On a whole-genome BAM with a sparse panel, the extra reading and decoding can offset parallel gains. The effect needs measuring on the intended workload.

Missing or mixed indices, incompatible dictionaries or ambiguous names for regional selection use the serial `sequential-budgeted` path. Indexed BAMs are first preselected with `samtools view -M -L` into temporary Linux files. Unindexed BAMs are read at their original paths. One `mpileup` then processes the list in sample order. This path runs one samtools process at a time. Acquisition measurements include staging time and bytes.

The report records the fallback reason. Each existing index is used even if a different BAM lacks one. Preselection or indexed-processing errors stop the run. Cancellation stops and waits for processes started by the preparer. Failed and cancelled runs retain diagnostics and withhold incomplete pileup from completed results.

The regional path uses [samtools 1.21](https://www.htslib.org/doc/1.21/samtools-mpileup.html). Qualification must establish pileup identity against the reference path.

## Budget and settings

The [0.8.12 options](PARALLELISMO_0.8.12.md) continue to apply.

| Setting | Initial value | Effect in 0.8.13 |
| --- | --- | --- |
| `--execution-mode` | `auto` | Select capacity automatically. `serial` allows one compute process per stage. |
| `--max-workers` | No manual cap | Cap DNP preparation processes and R workers. |
| `--dnp-block-mib` | `32` | Target raw input size per R block, in MiB. |
| `--dnp-block-loci` | `64` | Target number of complete loci per R block. |

The shared policy considers available CPUs, container quotas, memory, PIDs and the manual cap. R calculates the budget before acquisition. Preparation caps it again at the number of independent tasks. Each preparation task uses one samtools process. The same configured maximum applies to R workers in the subsequent stage. Stages execute sequentially without nested pools.

Actual worker counts can differ by stage and can fall below the requested maximum. The policy retains one process even if its memory estimate exceeds available RAM. Coordinators, clients and monitors are outside the worker pool. The separate `--pids-limit` setting covers all container PIDs.

Original inputs remain read-only. Scratch already used the Linux filesystem. Version 0.8.13 did not automatically copy entire BAMs and FASTAs. Any input-locality experiment must include copying time.

## Records to retain

| Run-relative file | Contents |
| --- | --- |
| `run.json` | Version, commit, inputs, requested options, resources and status. |
| `work/dnp-acquisition-budget.json` | Budget passed to preparation. |
| `work/dnp-pileup.json` | Strategy, fallback reason if any, acquisition times and process activity. |
| `work/dnp-blocks.json` | R blocks, acquisition/index/computation timings and actual workers. |
| `work/parallel/*.jsonl` | R scheduling decisions and task intervals. |
| `performance/engine/summary.json` and `performance/engine/samples.jsonl` | Container memory, CPU and process counters when diagnostics are enabled. |
| `output/` | Scientific results for comparison. |

For compound workflows, the step owns its `work/` files under `output/workflow/steps/<id>/`. Distinguish requested settings from observed workers in the report. The legacy DNP setting `parallel=false` can coexist with automatic execution.

**Maximum observed R-process RSS (MiB)** is a per-process maximum. Use the cgroup peak, when available, to compare total memory. Summing process RSS can count shared pages more than once.

## Windows qualification protocol

1. Identify the exact 0.8.12 and 0.8.13 builds and the common BAMs, indices, FASTA and panel. Read the version from run metadata. An older results folder's name can refer to another version.
2. Hold WSL/container resources, checksum policy, **32 MiB / 64 loci** and diagnostics constant. Avoid concurrent analyses.
3. Compare all four conditions below. Reuse a prior run only if its inputs, version, settings and outputs are verifiable. Give each new run its own name.

| Version | Mode | Purpose |
| --- | --- | --- |
| 0.8.12 | Serial | Control for the earlier R implementation. |
| 0.8.12 | Automatic | Reference with parallel R only. |
| 0.8.13 | Serial | Exercise the new path with one task at a time. |
| 0.8.13 | Automatic | Measure parallel preparation and computation. |

Option **4 — Parallelism and blocks** in the final review applies to the current run. Enable diagnostics and keep failed or interrupted records. Alternate the order across repeats when feasible. A single run provides limited evidence on speed and cache effects.

4. Verify process counts and overlapping activity within each stage. A requested cap or a series of distinct PIDs alone cannot establish concurrency.
5. Compare qualification pileups and scientific results with **0.8.5**, including table order, unrounded quantities and plots. Repeat at least the parallel condition. The previous comparison with 0.8.10 addressed a different reference.
6. Evaluate total and stage times, cgroup RAM and correctness together before changing block sizes or process limits.

[Local 0.8.13 qualification](validation/0.8.13-rootless.json) used the source hashes in the report. It covered **20 cases, 64 scientific executions and 44 comparisons against 0.8.5**, all newly run. The 145 table comparisons matched byte for byte. Unrounded scientific R objects matched, as did 137 rendered PDF pages at 36 DPI, excluding PDF metadata. Nine focused R checks, 25 pileup acquisition cases and R cancellation passed.

Pileup cases covered high depth, overlapping paired reads, indels, repeated QNAMEs, overlapping or unsorted panels, nonlexicographic chromosome order, multiple inputs, missing/corrupt indices, ambiguous contig names and cancellation. Acquisition tests directly observed maxima of one, two and four samtools processes. The available memory budget selected two workers in all 24 parallel R comparisons, including those capped at four. All 24 showed overlapping activity.

These tests used R 4.4.2 and samtools 1.21 under Linux with a relocated R runtime and without Docker or WSL. They did not exercise scientific container quotas, installers or real-data performance. The [0.8.12 local evidence](validation/0.8.12-rootless.json) records the preceding release separately.
