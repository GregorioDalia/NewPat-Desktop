# NewPat architecture

NewPat runs on the user's computer. The Python client owns the desktop interface, guided terminal menu, CLI, preferences and run records. The desktop interface uses a local webview and a loopback service for the interface and local genomic tracks. Scientific computation runs in a Linux container that includes R, samtools, the five scientific programs and their dependencies. It can run a single analysis or an entire workflow plan.

## Components

| Component | Responsibility |
| --- | --- |
| `src/nipat/gui/` | Desktop windows, local interface, experiments, results and IGV. |
| `src/nipat/cli.py`, `wizard.py` | Commands, menu, input selection and confirmation. |
| `src/nipat/execution/workflows.py` | Preliminary validation, workflow request and run creation. |
| `src/nipat/execution/analysis_plan.py`, `analysis_forms.py` | Plans for SNP and DNP branches, including explicit samples and family roles. |
| `src/nipat/execution/runner.py` | Engine identity, isolation, execution, cancellation and diagnostics. |
| `src/nipat/execution/transport.py` | Access to a local Linux Docker Engine or the engine inside WSL2 or Lima. |
| `src/nipat/execution/performance.py` | Optional client-side observation of container resources. |
| `src/nipat/storage.py` | Separation of data, results, program files and reserved destinations. |
| `engine/main.py` | Engine contract, verification of scientific source files and workflow dispatch. |
| `src/nipat_scientific/` | Shared validation, parameter catalog and input preparation. |
| `src/nipat_scientific/plan.py`, `executor.py` | Plan contract, dependencies and step execution inside the image. |
| `src/nipat_scientific/settings_data.json`, `settings.py`, `settings.R` | Parameter registry, Python/R validation, model constants and effective settings. |
| `src/nipat_scientific/dnp_pileup.py`, `dnp_blocks.R` | BAM acquisition, pileup indexing and scheduling across samples and blocks. |
| `src/nipat_scientific/performance.py` | Optional cgroup and process sampling and phase events inside the engine. |
| `scientific/vendor/` | Bundled R programs and upstream scientific resources. |

The client and engine each ship their own copy of the preparation library. Python adapters validate counts, frequencies, loci and alleles, prepare the file formats required by R and check the resulting artifacts. Normalizations write working copies. Cases that require scientific interpretation generate traceable warnings. The scientific equations reside in the R programs.

## Workflow execution

The client builds a request, confirms the inputs and starts one container. The engine determines step order, prepares the files and binds downstream inputs to specific upstream outputs. The container requires neither the GUI nor the host CLI. Its contract uses paths assigned by Linux mounts.

`execute` runs one module. `execute-plan` runs an explicit dependency graph. The client command `workflow analyze` supports DNPcall and SNPcall, independently selected downstream analyses, imported SNP pileups and imported count tables. DNP and SNP branches can share BAMs and each can feed Contamination, prenatal CPI and postnatal CPIN with marker-compatible panels and frequencies. A SNPcall batch creates one step per sample. In BAM mode samtools prepares the pileup before R.

Independent SNP calls can share one bounded pool in mixed plans. Serial mode runs one compute task at a time and nested pools remain serial. Other steps follow plan order and dependencies. Failure stops further scheduling and blocks pending steps. A new run is required to repeat the plan. Interaction, language, preferences, runtime launch, installation and updates belong to the client and platform packages. Protocol identifiers are language-independent. [Workflow contract](WORKFLOW_CONTRACT.md) · [Engine reference](../engine/README.md)

## Platform runtimes

| Host | Execution environment |
| --- | --- |
| Windows | User-account Python and launchers call `wsl.exe` for the configured, dedicated WSL2 distribution. `nipat-engine ensure` starts its Docker Engine as needed. Checks, execution and cancellation use that engine. |
| macOS | The host-native client uses the dedicated Lima VM and its Docker Engine. Python and Lima are bundled. Intel uses an AMD64 guest. Apple Silicon uses an ARM64 guest and Rosetta to run the same Linux AMD64 scientific image. Preflight checks engine identity and interfaces. |
| Linux | Ubuntu 24.04 LTS x86_64 uses the local Docker Engine and Compose with a `linux/amd64` container. The installed package uses `unix:///var/run/docker.sock`. It requires a system daemon without rootless mode or user namespace remapping. Results use the caller's UID/GID. |

The WSL transport runs with UID/GID 0 inside its dedicated environment. The Windows account that starts WSL determines access to Windows files.

## Client and engine contract

A single-analysis JSON request uses schema version 1 and one of `dnp-call-v1`, `snp-call-v2`, `contamination-v2`, `cpi-v2` and `cpin-v1`. The SNP interface identifies SNPcall 2.0 and its 17-column output. Plans use their own schema version 1 and `workflow-plan-execution-v2`. Requests describe container paths, scientific parameters and destinations. The runner resolves the image to an immutable ID and checks that its description supports the required interface and modules. The engine validates the input files again before invoking R. `doctor --runtime` checks all five module contracts and `scientific-settings-v1` against the image.

Environment probes mount no user data. During analysis, `work/engine-compose.json` gives the container read-only binds for selected input files, read/write access to this run, a read-only image filesystem, dedicated temporary storage and disabled networking. This avoids copying large BAM and FASTA files and limits exposure of sibling files and other runs. Optional CPU, memory and PID limits are recorded. Effective resources and the requested execution mode constrain workers. The container PID limit also covers coordinating processes and threads.

## File paths and sample identity

`--data-dir` and `--runs-dir` select independent roots. Relative CLI paths are resolved against the working directory. Paths inside BAM lists are relative to the list. On Windows, the WSL transport accepts local fixed disks. UNC paths, network drives and removable devices are unsupported. The client translates paths separately from scientific arguments and builds argument lists directly. CLI and menu prevent a results directory from overlapping managed runtime or cache destinations.

DNPcall receives ordered aliases such as `sample_0001.bam`. The run record in `run.json` maps them to original files. Standalone Contamination, CPI and CPIN preserve individual names in prepared copies and reject collisions, including case-only differences. In plans, Contamination uses aliases such as `table_0001`. CPI and CPIN use stable aliases for selected tables. State records link each table to its sample and producer step, and each native R result to its declared pair or trio. A branch calls each sample once and reuses the counts across families and downstream steps. Prenatal CPI takes maternal cfDNA and father. CPIN takes mother, father and child. The maternal samples used in the two analyses can differ.

## Preferences and provenance

The guided menu stores data/results roots, reference and workflow defaults, checksum policy, worker limits, DNP block settings, optional container limits and scientific overrides. The user selects run names, samples and families per experiment. **Configure** saves changes explicitly. A direct CLI command uses its arguments, environment and distributed defaults. Windows desktop preferences are in `%LOCALAPPDATA%\NIPAT-Desktop\preferences.json`. macOS uses `~/Library/Application Support/NIPAT-Desktop/preferences.json`. Installation configuration separately owns the program, cache and VM paths.

`newpat settings` lists defaults, types, bounds and constants. `--scientific-config PATH` and `--set module.parameter=value` apply validated overrides. Duplicate keys and inconsistent parameters are rejected. Each scientific step stores effective settings in `work/effective-scientific-settings.json`.

Each run has its own directory. `run.json` records parameters, inputs, path mappings, state, commands and image identity. `runtime.engine` identifies the verified R files and preparation code in the image separately from the client code. `execution.log` records client and engine messages. In plans, `output/workflow/workflow-state.json` records each step and its artifacts, with scientific messages in `steps/<id>/command.log`.

SNPcall from BAM retains BED and pileup. Both SNP input modes retain the normalized panel. DNPcall retains the panel, BAM list, acquisition and block metrics. Its temporary BED and pileup are removed after completion. Contamination, CPI and CPIN retain prepared tables, normalized panels and required frequencies. Display copies use original sample names and link back to canonical results. Scientific values and sample associations are preserved.

Cancelling requests termination of the active process and removal of its container. Partial results remain available for investigation. A dry run records the request, inputs and planned command. Image availability and scientific results require an actual execution. Full provenance hashes all inputs before and after the run. Automatic mode hashes small files and records metadata for large ones. Reconciliation compares an incomplete record to observed container identity. Explicit stop requires an identity match and produces a separate report. [Runs and results](ESECUZIONI.md)

## Installation, updates and maintenance

Release manifests associate version, commit and checksums. Windows and Ubuntu provide manifests compatible with existing clients. macOS uses a feed for its two host architectures. The updater verifies a download before installer handoff. New preferences default to the stable channel. Users can select testing and opt into startup checks.

The Windows desktop installer manages separate local roots for the program, WSL, cache, user data and results. Roots must be writable, fixed, independent and free of path links. Repair and update identify the existing package by inventory, then back up changed components, recovery metadata and generated Python before replacement. Unknown files remain in place. Obsolete files are removed only when they match the previous inventory. A modified obsolete component stays in place and is backed up. Account preferences, destination records, data and results survive uninstall.

WSL ownership depends on the registered distribution and destination. A missing owned distribution can be recreated in an empty destination while preserving the previous receipt. Changing its filesystem or location provisions a separate environment. Selecting new data or results roots leaves existing files where they are. WSL image provenance includes the Linux base, resolved package versions and engine. Builders may reuse an archive whose descriptor, content and checksum match the required component.

The launcher activates configuration after diagnostics and self-test succeed. Maintenance acquires an exclusive lock after the client exits and rechecks inventories, owned distributions, cache archives and backup records before changing anything. Selective backups support recovery of individual items. [Windows installer](INSTALLATORE_WINDOWS.md)

The macOS packages install `/Applications/NewPat.app` with host-native portable Python and Lima, plus the AMD64 scientific archive. The user workspace is `~/Library/Application Support/NIPAT-Desktop` and `LIMA_HOME` is `~/.nipat/lima`. First launch provisions the dedicated guest and verifies the bundled archive. Provisioning may use the network. Analysis runs offline in an isolated container. The bundle includes a separate terminal launcher for CLI use. [macOS installer](INSTALLATORE_MACOS.md)

The Ubuntu package includes the scientific archive and uses the host's Docker daemon directly. APT installs missing dependencies. Granting daemon access is an administrative decision. [Linux installer](INSTALLATORE_LINUX.md)

## Resource controls and diagnostics

Fixed run capacity, phase-specific estimates and execution settings determine compute concurrency. A reconfiguration lock coordinates resource changes with analyses. The preview and its configuration hash prevent applying a stale change. WSL changes require confirmation because settings may affect other distributions. Lima is dedicated to NewPat. Native Linux applies container limits.

DNPcall checks every samtools exit, keeps stderr and records the strategy and observed concurrency in `work/dnp-pileup.json`. A failed acquisition stops the call. Its memory estimates guide scheduling. Hard container limits and kernel measurements provide separate evidence. Optional diagnostics record client-side samples, cgroup/process measurements and scientific phases with size limits and explicit missing-data indicators. A monitoring error preserves the scientific outcome. Numerical comparisons on representative cases and expert review are needed to assess scientific suitability. [Performance diagnostics](PERFORMANCE.md)
