# Scientific engine interface

The NewPat image installs the engine in `/opt/nipat/engine`, the R scripts in `/opt/nipat/scientific` and the preparation library in `/opt/nipat/lib/nipat_scientific`. The engine runs independently of the working directory, client source tree and desktop installation directory. Its Python code uses the standard library. The image supplies R, samtools and their dependencies.

This document describes the engine interface inside the container. The [desktop CLI and guided menu](../docs/USER_GUIDE.md) prepare requests and mounts and record run metadata for ordinary use.

## Commands and identity

```sh
python3 /opt/nipat/engine/main.py describe --json
python3 /opt/nipat/engine/main.py verify
python3 /opt/nipat/engine/main.py catalog cpi --json
python3 /opt/nipat/engine/main.py validate-plan --plan /inputs/plan.json
python3 /opt/nipat/engine/main.py execute-plan --plan /inputs/plan.json --run-dir /run/workflow
python3 /opt/nipat/engine/main.py execute dnp-call --request /run/work/request.json
python3 /opt/nipat/engine/main.py execute snp-call --request /run/work/request.json
python3 /opt/nipat/engine/main.py execute contamination --request /run/work/request.json
python3 /opt/nipat/engine/main.py execute cpi --request /run/work/request.json
python3 /opt/nipat/engine/main.py execute cpin --request /run/work/request.json
python3 /opt/nipat/engine/main.py execute fetal-sex --request /run/work/request.json
```

`execute` validates the request, prepares the input files and starts the R program. Use `run` for a direct call with native R arguments.

```sh
python3 /opt/nipat/engine/main.py run snp-call -- \
  --pileup /inputs/pileup.txt --snplist /inputs/SNPlist.txt --out /outputs/output.txt
```

`run` passes the arguments following the workflow name directly to R and removes an optional leading `--`. It skips the input preparation performed by `execute`.

Before running any workflow, the engine checks all six R sources against the bundled scientific manifest. `describe --json` returns the following contract.

| Field | Value or meaning |
| --- | --- |
| `schema_version` | `1` |
| `interface` | `native-r-v1` |
| `workflow_interfaces` | `dnp-call-v1`, `snp-call-v2`, `contamination-v2`, `cpi-v3`, `cpin-v2` and `fetal-sex-v1` for their respective workflows |
| `preparation.interface` | `workflow-preparation-v1` |
| `plan_execution.interface` | `workflow-plan-execution-v2` |
| `plan_execution.workflows` | `dnp-call`, `snp-call`, `contamination`, `cpi`, `cpin`, `fetal-sex` |
| `scientific_settings.interface` | `scientific-settings-v1`, with a shared registry and effective values per step |
| `plan_execution.scheduling` | `dependency-order-with-bounded-independent-snp` |
| `plan_execution.resume` | `false` |
| Scientific identity | Manifest hash and path/hash of each of the six R scripts |
| `preparation.file_sha256` | Hashes of the engine entry point, shared preparation modules, R presentation adapter and JSON catalog records |

Verification rejects missing modules and paths outside the bundle. The preparation hashes identify bytes installed in the image. The engine also checks each R hash against the manifest. Build evidence and run metadata supply the release commit, distributed archive and image ID.

`execute` validates the inputs and results and handles signals during scientific execution. Verification and startup errors return exit code 2. For SNPcall from BAM, the engine also forwards signals to samtools and only starts R after successful preparation. The image supplies the dependencies before the engine runs.

`catalog` exposes the bilingual scientific catalog and checks its correspondence with the R sources in the image. `validate-plan` reads JSON and returns the canonical plan and dependency order without reading sample files, creating outputs or invoking R or samtools. See the [workflow plan contract](../docs/WORKFLOW_CONTRACT.md) and [scientific catalog](../docs/SCIENTIFIC_CATALOG.md).

`execute-plan` validates and executes a plan in a new destination. It prints the outcome and the path to `workflow-state.json`. With `--json`, it writes the full JSON report to stdout and progress messages to stderr. The exit code reflects the plan outcome in either mode.

Both callers produce typed count tables for contamination, prenatal CPI and postnatal CPI. Each of those steps uses either SNP or DNP tables. Prenatal CPI selects explicit pairs and postnatal CPI explicit trios. Fetal sex uses three role-specific tables for one maternal sample. Dependencies determine step order. Ready independent SNP steps share a bounded process budget, including in mixed plans. The policy admits one outer sample when memory demand is unknown. Nested sample workers use serial R pools. Users can request serial execution.

Each step keeps its request, prepared files, results and log. The engine maintains the overall state in `workflow-state.json`, coordinates the sequence, and forwards interruptions to the scientific process group. Errors and interruptions prevent later steps from starting. A retry uses a new destination.

DNPcall requires read-only BAM aliases `sample_0001.bam`, `sample_0002.bam` and so on, in the order specified by the step, on internal paths supported by the R interface. The client exposes these aliases without copying the BAMs. The engine resolves references to produced tables from the plan. The client does not need to predict intermediate filenames.

Each SNPcall step selects one sample and a SNP panel. BAM mode keeps the BED and pileup in `work` and records samtools messages in `preparation.log`. A preparation error or an invalid pileup prevents R from starting. Pileup mode reads the supplied file directly. Both write `output/SNPcall_output.txt`. The entry in `artifacts.snp-tables` associates it with the sample ID.

For CPI, the engine translates maternal/paternal references and pair IDs into internal names while preserving original input filenames. It prepares shared parents once. Outputs include the summary CSV, per-pair PDFs and a combined PDF. `artifacts.cpi-pairs` links the declared pair IDs to native names, CSV rows and plots. These mappings preserve the contents of the R results. See [plan execution](../docs/WORKFLOW_CONTRACT.md#plan-execution).

## Common request rules

Each request contains `schema_version: 1` and the workflow name. Paths describe files and destinations **inside the container**. Inputs must reside outside the distinct work and output directories. The output directory must be empty, and planned staging files must not already exist. Validation precedes preparation. The engine refuses to overwrite existing generated files.

The client mounts only the selected inputs read-only and the current run read-write. The runtime uses a read-only image filesystem, a dedicated temporary directory and disabled networking. Keep source and application directories outside `/opt/nipat`. The Dockerfile allows explicit probe and analysis commands without imposing an `ENTRYPOINT`.

After an I/O failure, partially prepared files remain in the run directory for diagnosis. Start the next analysis in a new directory.

## Contamination

```json
{
  "schema_version": 1,
  "workflow": "contamination",
  "panel": "/inputs/panel.txt",
  "samples": [
    {"path": "/inputs/sample_001.tsv", "name": "Original_sample.txt"}
  ],
  "work_dir": "/run/work",
  "out_dir": "/run/output"
}
```

The engine validates the panel and tables, copies the tables byte for byte into `work/inputs` and writes the R panel to `work/DNPpanel.txt`. Each staged table retains its original filename stem and uses the `.txt` extension. Unicode and spaces are permitted. Directory separators, control characters and duplicate names (including case-only collisions) are rejected before staging. The client can select individual files or recursively enumerate a directory. The engine request contains the final list of selected files.

## SNPcall

```json
{
  "schema_version": 1,
  "workflow": "snp-call",
  "mode": "bam",
  "panel": "/inputs/SNPlist.txt",
  "bam": "/inputs/sample.bam",
  "pileup": null,
  "reference": "/inputs/genome.fa",
  "work_dir": "/run/work",
  "out_dir": "/run/output"
}
```

With `mode: "pileup"`, both `bam` and `reference` must be `null`. The file specified by `pileup` must include QNAME in column seven. Additional columns are allowed. This mode runs without samtools and does not create BAM preparation files.

With `mode: "bam"`, `pileup` must be `null` and the FASTA reference requires an adjacent `.fai` index. BGZF-compressed references also require `.gzi`. A BAM index is optional because samtools uses the `-l` position list. The engine preserves the chromosome names from the panel, creates three-base BED windows in `work/snp_regions.bed` and runs samtools to generate `work/pileup.txt`. As in SNPcall 2.0, its default `-d 0` removes the depth limit.

Both modes produce the 17-column `output/SNPcall_output.txt`, four sample plots and a `summary` directory with genotypes and resources. The normalized panel columns are `chr`, `pos`, `ref` and `alt`. The earlier three-column form (`pos=chr:position`, `ref`, `alt`) is also supported. The position must be between 2 and 2147483646 inclusive in both modes. The `snp-call-v2` interface identifies the scientific table schema. Requests use `schema_version: 1`.

## DNPcall

```json
{
  "schema_version": 1,
  "workflow": "dnp-call",
  "panel": "/inputs/DNP_list.txt",
  "samples": [
    {"path": "/inputs/bams/sample_0001.bam", "sample_id": "sample_0001"}
  ],
  "reference": "/inputs/genome.fa",
  "parallel": false,
  "work_dir": "/run/work",
  "out_dir": "/run/output"
}
```

The client accepts one BAM, multiple BAMs or a list. Relative entries in the list resolve against its directory. The client assigns consecutive aliases beginning with `sample_0001.bam` and records the original paths in `run.json`. It mounts the BAMs and reference read-only. The reference requires `.fai` and, for BGZF, `.gzi`. BAM indexes are optional.

The engine checks the aliases and panel and writes `work/DNP_list.txt` and `work/bamlist.txt`. Work and output directories must be siblings named `work` and `output`. Execution starts in their parent directory with the relative arguments `--bamlist=work/bamlist.txt`, `--DNPs=work/DNP_list.txt` and `--out=output`. ASCII aliases provide paths compatible with the R interface even when the original names include spaces or Unicode. Boolean `parallel` controls the R `--parallel` option. Actual concurrency is subject to the shared resource policy.

Existing staging files, a nonempty output directory or existing `mpileup.txt` and `bedfile_for_mpileup.bed` in the run root prevent preparation. In ordinary execution the R script creates the latter two files and removes them when it finishes. The request, normalized panel and BAM list remain available.

DNPcall passes its effective process budget to the pileup acquisition helper. If the helper fails, R stops the analysis. `work/dnp-pileup.json` records the strategy and processes. The engine checks the required result tables before recording success. See the [DNPcall acquisition paths](../scientific/README.md#dnpcall).

<a id="cpi"></a>

## Prenatal CPI

```json
{
  "schema_version": 1,
  "workflow": "cpi",
  "samples": [
    {"path": "/inputs/sample_0001.txt", "name": "MotherA.txt"},
    {"path": "/inputs/sample_0002.txt", "name": "FatherB.txt"}
  ],
  "pairs": "A:B",
  "mother_prefix": "Mother",
  "father_prefix": "Father",
  "popfreq": "/inputs/population.tsv",
  "cutoff_mode": "named",
  "cutoffs": [{"label": "Full", "path": "/inputs/panel.tsv"}],
  "err_const": 0.0000892303778101497,
  "work_dir": "/run/work",
  "out_dir": "/run/output"
}
```

The `pairs` string contains comma-separated `mother:father` identifiers. The adapter trims surrounding whitespace. Prefixes are configurable and may be empty. Selected table names must match `<prefix><identifier>.txt`. A parent shared across pairs is staged once.

The client exposes the selected tables, frequencies and panels. The engine validates them again and copies tables byte for byte into `work/inputs`. R can access the selected inputs.

| `cutoff_mode` | Request and preparation |
| --- | --- |
| `all` | Empty `cutoffs` list, no native `--cutoff_map` argument and no output `Cutoff` column |
| `panel` | One panel with an empty label. The engine writes `work/DNPpanel.txt` and uses its internal path as the `Cutoff` value. |
| `named` | One or more unique, nonempty labels. The engine writes `work/cutoff_001.tsv` and subsequent files. |

The CLI accepts repeated `--cutoff` arguments and `--cutoff-map`. An unlabeled path in the map uses that path as its label. Panels can use three text columns with or without a header, or the five-column DNP format. The engine normalizes them to `chr`, `pos1` and `pos2`. XLSX panels are unsupported.

Labels cannot contain commas, equals signs or control characters. Internal cutoff paths cannot contain commas or equals signs because the R parser cannot encode them. The client uses aliases for host paths containing these characters. `err_const` must be finite and in `(0, 1]` for the selected marker type. Arguments are passed without a shell, preserving empty prefixes and values beginning with a hyphen.

Pair labels and PDFs use `Mother<id>-Father<id>_DNPs` or `Mother<id>-Father<id>_SNPs`, according to the marker type, regardless of the input prefixes. Ambiguous sample names and pair output collisions, including case-only collisions, cause an error before staging. The request, prepared tables and panels remain in `work`. The engine writes `Summary_FetalFraction_CPI.csv` in `output`, one PDF per pair and `All_CPIplots.pdf` in `output/plots`, and iteration tables for each pair and cutoff in `output/curves`.

<a id="cpin"></a>

## Postnatal CPI

An `execute cpin` request uses `schema_version: 1`, `workflow: "cpin"`, a `samples` list with `path` and `name`, the `trios` selection, the three role prefixes, `popfreq`, `work_dir` and `out_dir`. Optional `markers` selects a panel with coordinates and REF/ALT alleles.

`trios` is a comma-separated list of `mother:father:child` triples. Each role selects a distinct table through its prefix and identifier. Tables, the marker panel and population frequencies must use the same marker type, SNP or DNP. `scientific_settings` supplies validated overrides including `min_coverage`, the four `include_*` genotype-combination flags and the two marker-specific mismatch probabilities.

The engine exports a single combined index per trio in `Summary_Postnatal_CPI.txt` and an audit of included and excluded sites in each `<Trio>_sites.txt`. See [Postnatal CPI preparation and trio identity](../docs/WORKFLOW_CONTRACT.md#postnatal-cpi-preparation-and-trio-identity) for the workflow-plan equivalent.

## Fetal sex

An `execute fetal-sex` request uses `schema_version: 1`, `workflow: "fetal-sex"`, and absolute paths for `autosomes` (DNP), `x` (DNP), `y` (SNP), `work_dir` and `out_dir`. The three input tables belong to the same maternal cfDNA sample. The summary takes its sample label from the autosomal filename. The optional `scientific_settings` object overrides the source defaults. Each completed run exports `Fetal_sex_summary.txt`, `Autosomal_informative_sites.txt`, `X_informative_sites.txt` and `Y_sites.txt`. [Reference inputs and expected outputs](../tests/fixtures/fetal_sex/README.md)

## Readable labels

Both `execute` requests and plans can include an optional `presentation` object. Its `samples` map associates internal IDs with original sample names. Its `pairs` map associates pair IDs with readable labels. The sample map must be complete. The pair map may be partial. Labels are treated as data throughout.

The engine runs the scientific scripts identified by the manifest and creates readable copies in `output/presentation`. In plans, the combined index is in `workflow/presentation` for a workflow directory named `workflow`. The R adapter saves the native plots and renders copies with the original labels. Table exports change identifier fields only. Steps use canonical outputs for dependencies and numerical checks. Failure to create a requested export is reported as an error.

When names coincide, the engine adds a distinguishing identifier. Export filenames follow filesystem restrictions and may be shortened. The mapping retains the complete original name. CSV/TSV labels that spreadsheet software might interpret as formulas are protected as text. Scientific values are preserved.

The [user guide](../docs/USER_GUIDE.md) covers scientific configuration and desktop workflows. The engine validates overrides before staging and records effective parameters for every step.
