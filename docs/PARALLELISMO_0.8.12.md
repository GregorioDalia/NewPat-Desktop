# R workers and DNP blocks in 0.8.12

The 0.8.12 development candidate introduced a shared scheduling policy for the four R programs. Real-data and installer qualification were still pending. The [equivalence criteria](#equivalence-and-qualification) use the 0.8.5 reference.

## Settings

| Setting | Initial value | Meaning |
| --- | --- | --- |
| R execution mode | Automatic (`auto`) | Choose the worker count from the available resources and independent work. This may select one process. |
| Maximum R workers | Automatic | An explicit maximum caps the automatic decision. |
| Target DNP block size | 32 MiB | Target size of the raw pileup allocated to a block. |
| Target maximum DNP loci per block | 64 | Target number of complete loci in a block. |

`serial` uses one R worker even if a larger maximum was saved. The two block settings apply to DNPcall. Mode and worker cap apply to all four modules, including automatic workflows.

Accepted integer ranges are 1–1024 workers, 1–4096 MiB and 1–1,000,000 loci. The upper bounds describe what the settings accept. Complete windows, shared QNAMEs and groups required for compatibility stay together. An indivisible block can therefore exceed either target. The initial 32 MiB and 64 loci were starting points for qualification.

## One compute budget

The cap counts **R processes performing parallel computation**. A waiting R coordinator can have an additional PID. samtools, the Python engine and the monitor also run processes. The container-wide PID limit (`--pids-limit`) has a separate setting.

With a cap of four, DNPcall can distribute four samples or the blocks of one sample. A child processing a sample handles that sample's blocks serially. The same rule prevents nested pools in the other modules. Numerical libraries use one thread per process. Steps in a compound workflow run sequentially.

| Module | Units available for parallel execution |
| --- | --- |
| DNPcall | Samples, or complete blocks of the current sample when the sample layer has no child processes. |
| SNPcall | Complete read groups for each QNAME, including reads spanning multiple loci. |
| Contamination | Samples, or contiguous row ranges for one large sample. |
| CPI | Pairs, or panels, cutoffs or threshold ranges when the higher level runs serially. |

Collection restores the required order before aggregation and writing. Formulas, scientific filters, thresholds and numerical reduction order must remain equivalent to the reference. Reading, preparation and plotting can still include serial stages.

## How the scheduler chooses a worker count

Automatic mode takes the minimum allowed by independent work, CPU affinity, container CPU quota, manual cap, remaining PID capacity and estimated memory. The runtime uses Linux under WSL2 on Windows and Lima on macOS. Increasing VM CPUs can raise the available ceiling. Fractional CPU quotas round down with a minimum of one worker.

The release used the remaining memory under effective container limits, kept 20% in reserve and budgeted at least **2 GiB per worker**. For DNPcall, the estimated cost in MiB was `max(2048, 512 + 48 × largest planned block in MiB)`, rounded up. An indivisible block larger than the requested target contributes its actual planned size. Unknown memory selects serial execution.

These planning estimates cannot guarantee a memory bound. Expanded observations, joins, copies and R objects can consume more. The scheduler retains one worker even if the dataset cannot fit. `--memory-mb` caps container memory and can stop the container if set too low. WSL and Lima memory allocations are configured separately. See [Resources and memory](RISORSE.md).

## Menu and preferences

To set defaults for future guided runs:

1. Choose **5 — Configure → 9 — Resources, performance and provenance → 6 — Parallelism and blocks**.
2. Choose **1** for R execution mode, **2** for maximum R workers, **3** for target DNP block size (MiB) or **4** for the target maximum loci per block.
3. Choose **9** to apply the values and return, then **9** again to save changes.

Enter retains the current value. For the worker cap, `:vuoto` restores automatic selection without a manual maximum. Choose **0** to discard unconfirmed changes in the current menu.

For a single analysis, select **4 — Parallelism and blocks** in the final review, apply the values and start. Saved defaults remain available for the next run. Older preferences receive initial values for missing fields.

Explicit options to `wizard` take precedence over saved preferences. The final review still allows a one-run override. Direct CLI commands use their own arguments or initial defaults. Performance diagnostics are optional and are enabled separately for each run.

## CLI

The four global options precede the subcommand: `--execution-mode auto|serial`, `--max-workers N`, `--dnp-block-mib N` and `--dnp-block-loci N`. The legacy DNPcall `--parallel` option is accepted. The shared policy governs execution, including when `--execution-mode serial` and `--parallel` are supplied together. Automatic mode works without `--parallel`.

Run these PowerShell examples from the candidate's application folder containing `nipat.cmd`. Check `.\nipat.cmd --version` first and substitute local input paths. Each command creates a new run.

```powershell
.\nipat.cmd --execution-mode auto --max-workers 4 --dnp-block-mib 32 --dnp-block-loci 64 dnp-call --bam "C:\Dati\campione.bam" --reference "C:\Dati\genome.fa" --panel "C:\Dati\DNP_list.txt" --run-name dnp-max4
.\nipat.cmd --execution-mode serial snp-call --pileup "C:\Dati\snp-pileup.txt" --panel "C:\Dati\SNP_list.txt" --run-name snp-seriale
.\nipat.cmd --execution-mode auto --max-workers 2 contamination --input "C:\Dati\campione-individual.txt" --panel "C:\Dati\DNP_list.txt" --run-name contamination-max2
.\nipat.cmd --execution-mode auto --max-workers 4 cpi --input-dir "C:\Dati\cpi" --pairs "A1:A1" --popfreq "C:\Dati\frequenze.tsv" --run-name cpi-max4
```

To open the menu with a temporary cap:

```powershell
.\nipat.cmd --execution-mode auto --max-workers 2 wizard
```

On Linux use `nipat` and POSIX paths. On macOS use `"/Applications/NIPAT Desktop.app/Contents/Resources/NIPAT.command"` with the same arguments. The global options may also precede `workflow`. See the [CLI guide](GUIDA_UTILIZZO.md#comandi-diretti).

## Inspecting actual worker activity

Every scientific invocation records decisions in `work/parallel/*.jsonl`. Compound workflow steps use `steps/<id>/work/parallel/`. These events are emitted even when performance diagnostics are off.

`plan`, `task-start` and `task-end` record mode, requested cap, selected `workers`, estimated capacity, rationale, PIDs, task indices and timings. Evidence of simultaneous work requires overlapping intervals on distinct PIDs. DNPcall also records the block plan and measurements in `work/dnp-blocks.json`. Use [performance diagnostics](PERFORMANCE.md) for overall elapsed time, container CPU and peak RAM.

<a id="equivalenza-e-collaudo"></a>

## Equivalence and qualification

The reference is **NIPAT v0.8.5**, commit `eafadf7002a9c7d7c1b9af9ccafc47d698a059e5`. The [frozen copies and checksums](../tests/reference_r/0.8.5/README.md) include compatibility changes already distributed in that release. The baseline stays fixed when qualifying a candidate.

The [R test contract](../tests/r_optimization/README.md) compares all four modules against that reference in serial and automatic modes, with caps of two and four and repeated parallel conditions. It requires identical table bytes and ordering, identical unrounded R values, equivalent rendered PDF pages and unchanged inputs. Parallel tests must show overlapping computation within the effective cap.

The [0.8.12 qualification protocol](PERFORMANCE.md#collaudo-del-parallelismo-0812) distinguishes equivalence, determinism and speed/memory measurements. Release qualification also requires agreement on a real dataset, repeated runs at fixed resources and final-platform tests. Raw data and identifiable results stay outside Git.

## Local qualification results

The [local qualification summary](validation/0.8.12-rootless.json) records commit `302fb5648563d80910cc9460d0bec5845106414b`, source and test hashes and the 0.8.5 reference. R 4.4.2 passed **20 synthetic cases and 44 comparisons**. These comprised 20 serial candidates and 24 parallel runs across six representative cases. All 145 tables were byte-identical. Unrounded R values passed `identical()`. All 137 PDF pages were pixel-identical at 36 DPI, excluding metadata.

All four modules showed overlapping child processes in automatic mode, with caps of two and four, and on repeats. The available budget selected two workers even with a cap of four. Two additional CPI cases covered cutoffs and intervals. They required distinct child PIDs and recorded observed overlap because very short tasks can finish before the next child starts. Eight focused R checks, the indexed pileup audit and cancellation during real R execution also passed.

The 64 scientific executions include 34 completed results reused after checking unchanged science and capture hashes. All comparisons ran again. The report records the revised overlap criterion for the two small CPI cases and the earlier evidence hashes. It contains no private inputs.

These tests used a relocated R runtime on a local Linux system. Docker image, Windows and macOS installer qualification and agreed real-data tests remained outstanding. The results establish neither a real-data speedup nor a guaranteed memory bound or equivalence across every possible input.
