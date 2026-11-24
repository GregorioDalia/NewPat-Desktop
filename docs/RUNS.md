# Run folders and records

Each experiment gets its own run folder. Open the experiment in NewPat and use its open-folder action to find the exact location. Use a new name for each execution or let NewPat generate one. You can change the results directory in Preferences or pass the global CLI option `--runs-dir`. [Default locations](USER_GUIDE.md#file-locations)

## Where to look first

| File or folder | What it contains |
| --- | --- |
| `run-report.html` | A report you can open in a browser, with status, inputs, samples, parameters, phases, resource information and warnings |
| `run.json` | The structured run record, including input metadata, settings, status and engine identity |
| `execution.log` | Commands, diagnostic messages and errors |
| `output/` | Scientific results and plots |
| `output/presentation/` | Labeled exports from individual analyses, when available |
| `sample-map.tsv` | The association between original sample files and internal IDs such as `sample_0001`, where applicable |
| `work/` | Engine request, input mapping, validation reports and retained intermediate files |

A workflow has a top-level run record and an `output/workflow/` folder. Its `plan.json` identifies the requested samples, roles, dependencies and steps. Read `workflow-state.json` for the status, artifacts and checksums of each step. Each `steps/<id>/` folder holds the request, `command.log`, `output/` and step-specific `work/`. Presentation exports are in `presentation/`. Compatible groups of SNP results have summaries in directories such as `snp_summary/group_0001/`.

## Interpret the status

| Status in the run record | Meaning |
| --- | --- |
| `preparing` | NewPat is checking inputs and preparing the environment. |
| `running` | The engine has started. A final status has yet to be recorded. |
| `planned` | A dry run prepared a request. |
| `succeeded` | Execution and the required technical output checks completed. |
| `failed` | Preparation, execution or verification encountered an error. |
| `interrupted` | The client recorded an interruption, such as Ctrl+C. |

Check the overall status as well as the step status. A failed or interrupted workflow can contain valid results from earlier steps. A pending step may become `blocked`; an interrupted step may be `cancelled`. When NewPat cannot verify the workflow state, the report identifies the uncertainty. Scientific interpretation requires suitable reference data and review of any quality warnings.

Find input validation in `work/input-validation.json`. Single analyses can record quality warnings in `work/scientific-validation.json`; workflows report them under the step's `artifacts.quality_warnings`. [Validation guide](INPUT_VALIDATION.md)

## Stop an experiment or remove its card

1. In **Activity**, select **Stop analysis** and confirm. A queued submission can be cancelled before the calculation starts. For a running experiment, wait for its final state and check the run folder for any files already produced.
2. Select **Remove from list** on the finished activity card or in **Experiments and results**. Removing a card hides the corresponding experiment from the desktop lists. Existing input files, outputs and logs stay on disk.
3. To list a saved experiment again, choose **Open existing results** and select the folder containing its `run.json`. A submission cancelled before run creation has only an activity card.

After an unexpected exit, the desktop checks the local runtime before offering to remove a run whose last recorded status was `running` or `preparing`. An unverified run can appear as **Needs verification**. See [Inspect an incomplete run](#inspect-an-incomplete-run).

## Outputs by analysis

The paths below are relative to an individual run or to a workflow's `steps/<id>/` folder.

| Module | Results |
| --- | --- |
| DNPcall | Per-sample tables in `output/individual_outputs/`, genotype summaries in `output/summary/` and additional figures in `output/plots/` |
| SNPcall | `output/SNPcall_output.txt`, per-sample plots and tables in `output/summary/` when available |
| Contamination | `output/contamination_summary.txt` and sample-level `contamination_<sample>.txt` tables |
| Prenatal CPI | `output/Summary_FetalFraction_CPI.csv`, curves in `output/curves/` and PDF figures in `output/plots/` |
| Postnatal CPI | `output/Summary_Postnatal_CPI.txt`, per-site tables in `output/sites/`, threshold curves in `output/curves/` and PDF figures |

Use the *individual count table* as the starting point for another module. Match the file against the sample map. In a workflow, use the plan and `workflow-state.json` to trace labels such as `table_0001` back to the sample. The artifact keys `snp-tables`, `cpi-pairs` and `cpin-trios` connect outputs to samples, pairs and trios. Numbering in `summary_rows` starts at the first data row and excludes the header.

SNP BAM processing keeps `work/snp_regions.bed`, `work/pileup.txt` and the preparation log. Imported pileups are recorded as original inputs. DNP processing uses a temporary pileup. Its acquisition records describe the resource allocation (`work/dnp-acquisition-budget.json`) and the strategy, tasks and observed concurrency (`work/dnp-pileup.json`).

## Reproduce a run

Keep the input and sample order, role assignments, panels, allele frequencies and effective scientific settings. By default `--input-hashes auto` calculates SHA-256 for files up to 16 MiB and stores metadata for larger files. Choose `--input-hashes full` when a byte-level identity check is needed for large BAMs or references. Allow for extra full-file reads.

The engine mounts selected inputs read-only. Keep the source files unchanged until the run finishes. `work/input-mounts.json` maps paths to the names seen by the engine. `work/engine-request.json` or `work/engine-plan.json` describes the request, and `work/engine-compose.json` describes its execution environment. The run record identifies the client (`source.nipat_version`) and engine (`runtime.engine`). The module's effective settings are recorded in `work/effective-scientific-settings.json` and `output/scientific-settings.json`.

Keep a complete run directory when moving an experiment. Workflow records refer to files using relative paths. Preserve the original inputs separately and record the source run for any count tables reused in a new analysis. Review identifying names and paths before sharing results or logs.

<a id="misure-delle-prestazioni"></a>

## Performance measurements

To record timing, CPU and memory observations, select **Record performance diagnostics** in the desktop or put `--performance-diagnostics` before the scientific command. Open `run-report.html` and the `performance/` directory. Container memory, R process RSS and elapsed time describe different aspects of a run. Use the same inputs, settings and resource limits when comparing executions. [Performance guide](PERFORMANCE.md) · [Resources and memory](RESOURCES.md)

<a id="esecuzioni-incomplete"></a>

## Inspect an incomplete run

An unexpected exit can leave `preparing` or `running` in the record. On Ubuntu, for example:

```sh
newpat runs inspect
newpat runs inspect --run "/path/to/run" --json
newpat runs stop --run "/path/to/run"
```

Use the installed launcher for your platform and substitute the actual run directory. `inspect` reads runtime state. `stop` asks for confirmation and acts only on a container associated with the run. For scripted use, `--yes` confirms the operation. The recovery attempt records its outcome in `recovery.json` when applicable.

A confirmed stop returns exit code 0 when the recorded containers have been removed or are absent. Code 2 indicates that cleanup or runtime identity needs attention. Cancelling the prompt takes no action and returns 0. Once the cause is resolved, start a fresh run and retain the existing records.
