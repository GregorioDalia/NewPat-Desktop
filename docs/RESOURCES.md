# Resources and memory

NewPat runs the scientific engine in a Linux container. The physical computer, the environment that hosts the container, and the individual run each have their own limits.

| Level | What to check |
| --- | --- |
| Computer | Physical memory and CPU capacity of the host |
| Runtime environment | Memory and CPUs available to WSL2 on Windows, Lima on macOS, or the local Docker Engine on Ubuntu |
| Run | CPU, memory and process limits applied to this analysis container |

A container cannot use more memory than its environment can supply. For example, setting an 8 GiB container limit inside a 4 GiB VM still leaves the VM as the effective constraint. An unavailable measurement means that NewPat could not determine a value.

## Inspect the allocation

Open **Environment and help** in the desktop or run `newpat resources inspect --json`. Inspect the effective values as well as the saved settings. Some VM changes require a restart before they take effect. Suggestions based on host capacity leave room for the operating system; the memory a particular analysis needs also depends on the sample, coverage and panel.

When changing VM settings in the text wizard, Enter keeps the current value, including an automatic setting. The token `:suggerito` adopts the suggested value. To configure explicit VM limits, specify both memory and CPUs. The tool previews the proposed changes before applying them.

<a id="budget-fisso-della-095"></a>
<a id="budget-del-run-e-numero-di-processi"></a>

## Run budget and workers

NewPat records the startup CPU, memory and worker ceilings in `run.json` under `resource_budget`. These ceilings reflect the measured runtime, the configured limits and the user’s request. On Linux, the engine also checks CPU quotas, memory limits and process limits in the process's own cgroup and its visible ancestors.

Desktop sessions of one user coordinate CPU and memory assignments on the same runtime. Jobs preparing together can share capacity from the start. A late arrival waits for a usable share of both resources. On a compatible engine, a desktop workflow can offer some of its allocation after a completed analysis step or group of independent SNP samples. The host revises its accounting only after the engine confirms that the previous workers have finished. The workflow can recover previously yielded capacity at a later boundary, up to its original ceilings. An engine without this capability retains its startup allocation. If capacity cannot be measured, one desktop experiment calculates at a time. [Desktop activity](GUI.md#set-up-an-experiment)

Each phase reserves 20% of its assigned memory and accounts separately for the coordinator's resident memory. The general worker estimate considers twice the coordinator's resident memory and any module-specific estimate. A phase with an unknown workload may run serially. A changed allocation guides scheduling of subsequent work. The operating system continues to enforce the container limits set at launch.

DNPcall makes two separate decisions:

1. **Acquisition.** Indexed BAMs with compatible settings and a bounded depth can share the work across target chromosomes. Each process reads the same set of BAMs, in sample order. The planner estimates memory from the sample count and reference. A single BAM uses up to 25% of the remaining working memory, with up to 40% available for the first two workers under the calibrated single-BAM conditions. A joint pileup can use up to half of the remaining working memory and charges the per-BAM estimate for each sample in each process. The chromosome count, CPU allocation and worker setting cap both pools at a maximum of five. Serial mode uses a single process. Inputs requiring a scan retain that path.
2. **R calculation.** The planner considers the number and size of available blocks, sample count and estimated memory per worker. It can keep larger blocks on a sufficiently provisioned run or divide substantial work more finely on a smaller allocation. It keeps complete windows and accounts for the largest actual block, including an indivisible group. In automatic mode, an allocation close to the base memory estimate reduces the target to the smallest complete group. On Apple Silicon running the AMD64 image under Lima, an effective run allocation of at most 4 GiB also limits the automatic R pool to two. With compatible joint pileups on that backend and native x86-64 Linux, a worker can share one read across samples. Single-sample runs keep the established reader.

Inspect `work/dnp-acquisition-budget.json`, `work/dnp-pileup.json` and `work/dnp-blocks.json` for a specific run. A BAM's compressed size alone predicts neither peak memory nor execution time. Compare like-for-like inputs, sample order and scientific settings. [Performance measurements](PERFORMANCE.md)

### SNPcall and downstream modules

For a single SNP sample, a coordinate-sorted BAM with a current index and multiple eligible target chromosomes can use several samtools processes. The acquisition planner considers the target reference lengths and run budget. It also monitors the pool's resident memory. If the pool exceeds its allowance, NewPat retries acquisition with one process. An existing pileup goes directly to the R analysis. The R caller can distribute complete read groups and, in a later phase, genotype likelihoods across groups of independent loci. The likelihood phase considers extra workers at 2,048 informative loci or 1,048,576 informative reads distributed across at least two loci. The run budget can still select one worker.

For a batch, NewPat first tries to admit independent samples. It estimates working memory from pileup bytes, bounded BAM depth or coverage measured in the target windows. For large BAMs with unbounded depth, it can check up to 2,048 SNP sites using a current index and a five-second measurement window shared by the batch. Overlapping windows are included in the estimate. The planner budgets each sample separately. Independent samples whose combined estimates fit can overlap, using one computational worker per sample. A sample with unknown cost runs on its own. A sample processed individually can still use the ordinary parallelism of its eligible phases. Contamination can distribute independent input tables, prenatal CPI can distribute pairs, and postnatal CPI can distribute trios.

## Limit a single run

Global options go **before** the scientific command.

| Option | Effect |
| --- | --- |
| `--cpus N` | Container CPU quota |
| `--memory-mb N` | Container memory limit in MiB |
| `--pids-limit N` | Limit on processes in the container, including coordinators |
| `--execution-mode serial` | One computational worker at a time |
| `--execution-mode auto` | Plan with the resources and work available |
| `--max-workers N` | Upper bound on simultaneous computational workers |

For a serial or capped comparison, use the same sample and panel for each run. This Ubuntu example requests at most two workers:

```sh
newpat --execution-mode auto --max-workers 2 --performance-diagnostics dnp-call \
  --bam sample.bam --reference genome.fa --panel dnp-panel.txt
```

## Configure WSL2, Lima or Docker

- **Windows.** Memory and CPU entries in `.wslconfig` apply to every WSL2 distribution for the current account. NewPat previews the existing and proposed values, keeps unrelated settings and writes a backup. You can save changes and restart WSL later. Applying the change immediately requires separate confirmation of the shared WSL restart. Close other WSL work first. [Microsoft WSL configuration reference](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
- **macOS.** The Lima VM belongs to NewPat. If it is running, changing its allocation requires confirmation of the stop and restart. NewPat checks ownership and preserves the existing VM data.
- **Ubuntu.** NewPat uses the local Docker Engine. Configure container limits for your runs. Docker permissions, service limits and host capacity also affect the actual allocation.

NewPat checks for active analyses before reconfiguring the environment. If the configuration changes concurrently, refresh the preview. Example commands for installations with the `newpat` launcher:

```sh
newpat resources inspect
newpat resources configure --memory-mib 8192 --vm-cpus 4
```

The second command previews the change. `--apply --yes` authorizes saving; `--restart` separately requests the runtime restart. When a saved change still needs a restart, the report can show `saved-restart-required`. With an immediate restart, success corresponds to `applied` after verification. Exit code 2 reports an incomplete restart or an allocation that still needs checking. The JSON backup records the path, hash and former content or absence of the system configuration file.

<a id="errori-di-memoria-e-codice-137"></a>

## Investigate exit code 137

Exit code 137 is consistent with a process receiving `SIGKILL`. To determine whether memory exhaustion caused it, open `run-report.html` and `execution.log`, and look for the recorded container status, `OOMKilled` and the limits in force. Missing runtime evidence leaves the cause undetermined.

Record the platform, physical RAM, effective runtime and container allocation, number of samples, and execution mode. After choosing an appropriate change, run a new experiment. The failed run keeps its logs and settings for comparison.
