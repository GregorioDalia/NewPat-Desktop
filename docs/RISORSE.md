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

NewPat records the effective allocation in `run.json` under `resource_budget` when the run starts. CPU and memory limits come from the available hardware, runtime and container. The memory planner reserves 20% of the capacity and accounts for the coordinator's resident memory when sizing its worker pool. The global worker ceiling stays fixed for the run. Other applications can still affect elapsed time and memory pressure.

Each phase checks its expected workload against that run budget. The general estimate considers twice the loaded coordinator's resident memory and any module-specific estimate. Some phases stay serial when their workload cannot be estimated. The worker count is a planning decision; the operating system enforces the configured container limits.

DNPcall makes two separate decisions:

1. **Acquisition.** For one indexed BAM with compatible settings and reference information, NewPat estimates the cost of each samtools process. The pool normally uses up to 25% of the working memory left after accounting for the coordinator. For a bounded-depth workload with an estimated 576 MiB per process, the first two can use up to 40% of that memory. Any additional processes must fit the 25% allowance. The number of eligible chromosomes, the CPU and worker limits, and a ceiling of five also constrain concurrency. A single eligible chromosome, serial mode, or missing workload evidence leaves one acquisition process. Inputs that require scanning can still use the unpartitioned path.
2. **R calculation.** The planner considers the number and size of available blocks, sample count and estimated memory per worker. It can keep larger blocks on a sufficiently provisioned run or divide substantial work more finely on a smaller allocation. It keeps complete windows and accounts for the largest actual block, including an indivisible group.

Inspect `work/dnp-acquisition-budget.json`, `work/dnp-pileup.json` and `work/dnp-blocks.json` for a specific run. A BAM's compressed size alone predicts neither peak memory nor execution time. Compare like-for-like inputs, sample order and scientific settings. [Performance measurements](PERFORMANCE.md)

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
