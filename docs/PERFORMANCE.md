# Performance diagnostics

NewPat can record wall time, CPU, memory, I/O and process activity for a single analysis. To measure normal elapsed time, run without monitoring. To locate a bottleneck or investigate a failure, repeat with diagnostics enabled and keep the inputs, settings and resource allocation fixed.

## Measure an analysis

1. Record the application version and check the environment. In the terminal menu, use **8**.
2. Choose the analysis and a new run name. For DNPcall, select a BAM, its matching indexed reference FASTA, and a DNP panel. A valid BAM index enables indexed acquisition when the inputs support it.
3. Confirm the input, output, settings and execution mode. Run the analysis normally.
4. Start a second run with a new name. Choose the launch option with performance diagnostics, or pass the global `--performance-diagnostics` option before the analysis command.
5. Open `run-report.html` in the second run. Inspect performance diagnostics and compare the scientific tables from both runs.

```sh
newpat --performance-diagnostics dnp-call \
  --bam "/data/sample.bam" --reference "/data/genome.fa" \
  --panel "/data/DNP_list.txt" --run-name dnp-profile-01
```

The same global option works for a workflow. `newpat --performance-diagnostics wizard` proposes a diagnostic run in the guided menu, where the launch summary also offers ordinary execution. The engine must advertise `performance-diagnostics-v1`. [Packaged launchers](USER_GUIDE.md)

## Comparing serial and automatic execution

| Mode | Global options |
| --- | --- |
| Serial | `--execution-mode serial` |
| Automatic | `--execution-mode auto` |
| Automatic with up to two workers | `--execution-mode auto --max-workers 2` |

The run records its initial capacity and worker ceiling at startup. In a desktop workflow sharing a runtime, the budget for a later step can change when an earlier step or independent SNP batch has finished. SNP summaries also check for a new budget before each eligible summary group. Each phase selects its pool from its current assignment, available tasks, CPU limits and workload estimate. A coordinator is accounted for separately. Nested work cannot multiply the worker limit. DNP first acquires a pileup, possibly processing independent target chromosomes concurrently, then builds a global index and computes blocks in R. Start with the same requested limits, normally **32 MiB of raw input** and **64 loci** per block. Record both requested and effective targets. Indivisible groups can exceed them. Raw pileup bytes and resident R memory measure different things. [Resource policy](RESOURCES.md)

In the terminal menu, change parallelism and block size in the run summary. Save reusable defaults in the resources, performance and provenance preferences. On Windows, set `$newpat` to the installed CLI launcher as shown in the [user guide](USER_GUIDE.md), then run the two commands from the folder containing the inputs.

```powershell
& $newpat --execution-mode serial dnp-call --bam ".\sample.bam" --reference ".\genome.fa" --panel ".\DNP_list.txt" --run-name dnp-serial-01
& $newpat --execution-mode auto dnp-call --bam ".\sample.bam" --reference ".\genome.fa" --panel ".\DNP_list.txt" --run-name dnp-auto-01
```

Check overlapping worker events in `work/parallel/*.jsonl` for actual concurrency. For DNP acquisition inspect the observed processes in `work/dnp-pileup.json`. For SNP BAM acquisition, inspect the strategy, fallback reason and observed process count in the sample’s `work/snp-acquisition.json`. For a multi-sample workflow, follow the work directory recorded for each step and inspect the outer sample events separately.

<a id="misure-e-significato"></a>

## Interpreting measurements

| Measure | Scope |
| --- | --- |
| Total wall time | The benchmark supervisor measures the complete command, including startup, environment setup, preparation, computation and finalization. |
| Run duration | Difference between `started_at` and `finished_at` in `run.json`. |
| Step duration | Preparation, computation and verification for one step in `workflow-state.json`. Concurrent steps can overlap. |
| Phase duration | Monotonic time between engine events. The R phase can include samtools, calculations and plotting. Nested phases overlap. |
| Docker memory | External Docker observer. On Linux the Docker CLI subtracts inactive cache when displaying memory. |
| Cgroup memory | Kernel accounting for the entire group, including applicable cache. A peak is available when the kernel exposes the counter and the observer reads it. |
| Process RSS | Resident memory for an R, samtools or supervising process. Summing RSS can double-count shared pages. |
| CPU and I/O | Counters visible inside the container. Host filesystems, caching and virtualization affect attribution. |

Use the same memory source across runs. Periodic samples can miss short peaks. A kernel peak reflects activity up to the last successful counter read. Leave missing measurements unavailable. For exit code 137, check the diagnosis in `run.json`. Docker can flag an out-of-memory termination of the container. When a child process is killed and the engine survives, an increase in the Linux cgroup `oom_kill` counter during the command confirms that the kernel killed a process in that group for lack of memory. Use the scientific step log and the per-process samples to identify the affected phase. Exit code 137 alone leaves the cause open.

<a id="consultazione-dei-risultati"></a>

## Files to inspect

| File or field | Contents |
| --- | --- |
| `run-report.html` | Human-readable overview and links to measurements. |
| `run.json` → `resource_budget` | Capacity, reserve, policy and startup worker ceiling. |
| `run.json` → `concurrent_execution` | Initial desktop CPU and memory assignment, number of participating experiments, and whether the calculation waited for resources. |
| `work/desktop-scheduling/grants.jsonl` | Host decisions at completed step boundaries, when a desktop budget changes. This path is relative to the top-level run directory. |
| `output/workflow/workflow-state.json` → `desktop_resource_grants` | Grants applied by the engine, with the next step or group, CPU, memory and worker ceiling. |
| `performance/summary.json` | External Docker observer summary. |
| `performance/container-samples.jsonl` | Container resource samples. |
| `performance/engine/summary.json` | Availability and summary of engine measurements. |
| `performance/engine/samples.jsonl` | Cgroup and process samples. |
| `performance/engine/phases.jsonl` | Phase start, end and duration. |
| `work/parallel/*.jsonl` | Worker budgets and task events. |
| `work/dnp-acquisition-budget.json` | DNP acquisition worker allowance. |
| `work/dnp-pileup.json` | Acquisition strategy, elapsed time and observed processes. |
| `work/dnp-blocks.json` | Acquisition, indexing and R block execution metrics. |

The scientific worker and DNP files in `work/` are relative to `output/workflow/steps/<id>/` for a plan. Compare the initial assignment with any grants applied before the step when interpreting different worker counts across runs. Sum task times to describe work performed. Use phase or wall duration to describe time experienced by the user. Short runs, interruptions and file-size caps can leave partial measurements. Inspect collector status alongside analysis state. Reports may include original sample names and paths.

<a id="protocollo-per-un-bam-grande"></a>
<a id="protocollo-per-input-reali"></a>

## Repeating a real-data benchmark

1. Keep file contents, indices, panels, frequencies, sample order, family roles, settings and checksum policy fixed. Record application and image identity.
2. Keep hardware, storage, power source, power profile, VM allocation and container limits fixed. Record competing load. Full hashing also reads every byte. Distinguish the first read from subsequent cached reads.
3. Alternate conditions, using a new run name each time. Where practical, repeat at least three times. Report median, spread, test conditions and any failures.
4. Verify sample identities and output agreement. Keep synthetic and real-data results separate. Fix the pairs/trios, panels, cutoffs and frequencies for CPI/postnatal CPI.
5. Change one factor at a time. Separate DNP acquisition, indexing and block computation. For composite workflows record both overall and per-step time.

The checkout includes a supervisor for DNPcall or DNPcall → Contamination. It accepts a list of distinct BAMs. This example uses a one-line list. Write each condition to a new directory. Omit `--performance-diagnostics` for a normal timed run.

```sh
python scripts/benchmark_workflows.py \
  --bamlist /data/one-sample.txt --reference /data/genome.fa \
  --panel /data/DNP_list.txt --output-dir /results/dnp-benchmark \
  --sample-counts 1 --repeats 3 --workflow dnp-call --performance-diagnostics
```

`benchmark.json` retains inputs, times, resources and available summaries. To compare one, two and N BAMs in one experiment, pass the desired counts to `--sample-counts` (for example, `1 2 4` for a four-file list). For each count the supervisor selects that many entries from the start of the same ordered list. To measure several desktop experiments competing for the runtime, launch the same workload as separate experiments, record their submission times and compare the elapsed time to finish the whole group with each run’s individual time and resource grants.

The [installed synthetic suite](WINDOWS_INSTALLATION_TEST.md) checks known workloads. For a physical Apple Silicon comparison, the [Mac worker benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac) uses the installed package and checks each condition against the serial output. The [0.9.10 audit](https://github.com/GregorioDalia/NewPat-Desktop/blob/v0.9.10/docs/AUDIT_0.9.10.md#portable-cpu-and-memory-policy) identifies which measurements came from earlier Mac runs and which exercised the policy on Linux. Measure representative local inputs to estimate elapsed time on a particular machine. [Run records](RUNS.md) · [Docker statistics](https://docs.docker.com/reference/cli/docker/container/stats/) · [Linux cgroup v2 counters](https://docs.kernel.org/admin-guide/cgroup-v2.html)

<a id="collaudo-dei-cinque-moduli-nella-0850"></a>
<a id="collaudo-del-parallelismo-0812"></a>
<a id="collaudo-del-pileup-parallelo-0813"></a>
<a id="collaudo-delle-ottimizzazioni-0814"></a>

Earlier experiments and their test conditions are indexed in the [historical performance studies](https://github.com/GregorioDalia/NewPat-Desktop/blob/c2b936b6d581137746b372b9bbade2318bae716c/docs/archive/README.md#audits-tests-and-decisions).
