# Code guide

Start with one experiment. A researcher selects samples in a desktop window. NewPat prepares a list of jobs, runs the scientific programs on the same computer, then saves their results so the researcher can reopen them. These three activities explain most of the directory tree.

## Follow an experiment in PyCharm

| Step | Open | What happens here |
| --- | --- | --- |
| 1. Choose samples and analyses | [desktop/web/app.js](../src/newpat/desktop/web/app.js) and [desktop/service.py](../src/newpat/desktop/service.py) | The window collects the selections. Its local Python service handles requests from the screen. The terminal reaches the application through [cli.py](../src/newpat/cli.py). |
| 2. Start the work | [desktop/plan.py](../src/newpat/desktop/plan.py), [experiments/analysis_plan.py](../src/newpat/experiments/analysis_plan.py) and [experiments/runner.py](../src/newpat/experiments/runner.py) | The desktop translates selections and family roles into workflow inputs. The plan builder connects the callers and downstream steps. The runner records the experiment and starts its local Linux container. The container supplies the same scientific tools across operating systems. |
| 3. Run each selected analysis | [engine/main.py](../engine/main.py) and [newpat_scientific/executor.py](../src/newpat_scientific/executor.py) | The engine verifies its programs, prepares their inputs and follows dependencies. For example, a contamination analysis can use the counts produced by DNPcall. |
| 4. Find the calculation | `scientific/vendor/` | Open the R program for the selected analysis. Shared code for preparing inputs, distributing work and collecting outputs lives in `src/newpat_scientific/`. |
| 5. Read or export the result | [desktop/results.py](../src/newpat/desktop/results.py) and [desktop/analysis_report.py](../src/newpat/desktop/analysis_report.py) | The desktop reads the saved results. For PDF export it prepares the report content and [reports.js](../src/newpat/desktop/web/reports.js) lays it out. |

## Where do I look for the science?

The two folders under `scientific/vendor/` record where the programs came from. **DNPcall** came from the DNPcall project. **SNPcall, Contamination, Prenatal CPI, Postnatal CPI and Fetal sex** came from Letizia's NEWPAT project. All six use the same NewPat engine. The files here are the operational copies adapted for NewPat. The [scientific guide](../scientific/README.md) links directly to each R file and identifies its reference implementation.

For a question about a value, start with the [settings registry](../src/newpat_scientific/settings_data.json) for its default and allowed range. For a question about a formula, use the [scientific catalog](SCIENTIFIC_CATALOG.md) to locate the calculation. For a question about speed, start with [the resource guide](RESOURCES.md), which distinguishes sharing resources between experiments from splitting work inside one analysis.

## What the other folders contain

| Folder | Why it is here |
| --- | --- |
| `src/newpat/` | The application on the user's computer. `desktop/` contains the screens, local services and the desktop interface. In it, `web/` holds screen layouts, charts and PDF rendering, `web/vendor/` holds bundled third-party libraries, and `native/windows/` holds Windows webview dependencies. `experiments/` launches and tracks work. `adapters/` handles panel formats. `validation/` verifies checksums, exposes shared file validators and runs the installed self-tests. |
| `src/newpat_scientific/` | Code shared by the client and the scientific environment. It describes what a valid analysis needs, prepares inputs and helps run each step. `catalog_data/` connects parameters and formulas to source files. |
| `engine/`, `scientific/` | The engine's entry point and the R programs it runs. The checksum list in `scientific/` identifies the operational scripts. |
| `config/`, `docker/scientific-runtime/` | A pointer to the scientific defaults, and the recipe for building the environment containing R, samtools and the analysis code. |
| `installer/` | `windows/`, `macos/` and `linux/` contain the platform-specific installation or launch code. Package builders also live in `scripts/`. `runtime/` builds the dedicated Linux environment used by Windows through WSL2. |
| `assets/branding/` | Source artwork and the tool that turns it into icons and wordmarks. |
| `examples/synthetic-trio/` | The demo. It includes alignments, reference sequence, panels, count tables, frequencies and timing inputs. The ZIP in `examples/` is the copy users can take away. |
| `tests/` | Automated checks. `fixtures/` holds small inputs and expected answers. `reference_r/` holds frozen comparison scripts. `r_optimization/` checks the scientific behavior of optimized paths. |
| `scripts/` | Tools for building packages and verifying the project. `acceptance/` exercises an installed copy. `windows/` contains Windows setup and launch helpers. |
| `.github/` | `workflows/` defines which jobs GitHub runs. `scripts/` implements their checks. `release-acceptance/` records evidence for particular releases. |
| `docs/` | User and developer guides. `archive/` points to earlier documentation and `validation/` stores recorded measurements. Start at the [documentation index](README.md). |

At the root, [pyproject.toml](../pyproject.toml) defines the Python package and launch commands, [compose.yaml](../compose.yaml) defines the scientific container service, and [distribution-files.txt](../distribution-files.txt) lists files eligible for packaging.

## Installed workspaces and source packages

Open `src/newpat` for the desktop client and `src/newpat_scientific` for input contracts and the local engine. From a development environment with the project installed, `python -m newpat` invokes the same client as the `newpat` command.

NewPat 0.9.99 initializes a separate workspace for its preferences, runtime and experiments. The [installation guide](DISTRIBUTION.md) links to the default paths for each platform. The uppercase `NEWPAT` under `scientific/vendor/` identifies the upstream R project.
