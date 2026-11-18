# Scientific workflow plan contract

A plan identifies samples, analysis steps and their input and output relationships. The Linux image contains the `nipat_scientific` engine, which implements `schema_version: 1` independently of the host OS or interface language.

`validate-plan --plan FILE` checks the structure and dependencies and returns JSON. It works without the sample files and starts no R or samtools process. File content, reference compatibility and output checks belong to execution.

`execute-plan --plan FILE --run-dir DIR` runs plans containing DNPcall, SNPcall, Contamination, prenatal CPI and postnatal CPIN. Both callers produce typed count tables accepted by all three downstream modules. Each SNPcall step processes one BAM or pileup. Multiple steps can share a panel. Use `execute` to run a single module.

The desktop command `workflow analyze` and menu **W → 5** build DNP branches, SNP branches, or both, starting from alignments or existing tables. Each branch can select its own subset of Contamination, CPI and CPIN. The client generates the JSON from the confirmed menu selections or CLI arguments.

Before each R invocation, the engine performs the [input content checks](INPUT_VALIDATION.md) used by single-module analyses. Each step keeps its normalized panels and `work/input-validation.json`. The engine verifies outputs before passing them to dependent steps. Numerical warnings appear in `artifacts.quality_warnings`. They preserve the original R tables and flag results that need scientific interpretation.

## Request structure

A request contains `schema_version`, `samples` and `steps`. It may also include `presentation`. Unknown fields and missing required fields cause validation errors. The caller must supply required orchestration options. Omitted scientific options take their defaults from the engine registry. The engine records the effective settings for each step.

Each entry in `samples` has three fields.

| Field | Meaning |
| --- | --- |
| `id` | Sample identity within the plan, independent of the filename. |
| `kind` | `bam`, `dnp-table`, `snp-table` or `snp-pileup`. |
| `path` | Absolute POSIX path inside the container. |

Sample, step, pair and trio identifiers contain 1–64 ASCII characters. The first character must be a letter. Subsequent characters may be letters, digits, `_` or `-`. Identifiers must be unique even when compared without regard to case. Each reference must match the declared spelling exactly. Two samples cannot register the same path string. The validator compares path strings without resolving symlinks, hard links or other names for the same physical file.

Use the container paths assigned by the client when it mounts inputs, such as `/workspace/inputs/sample_a.bam`. A Windows host path such as `D:\dati\sample.bam` is invalid here. Paths cannot contain `.` or `..` components, repeated slashes, backslashes or control characters. Values are literal. The contract accepts no shell commands or arbitrary programs and performs no variable, command, template or glob expansion.

Every entry in `steps` contains exactly `id`, `workflow`, `inputs` and `parameters`. The value of `workflow` selects the module.

| Workflow | Required fields in `inputs` | Orchestration parameters |
| --- | --- | --- |
| `dnp-call` | `samples` (list of BAM IDs), `reference` (FASTA), `panel` (DNP panel) | `parallel` (Boolean) |
| `snp-call` | `sample` (BAM or pileup ID), `reference` (FASTA or `null`), `panel` (SNP panel) | `mode` (`bam` or `pileup`) |
| `contamination` | `samples` (list of table references), `panel` (coordinate panel) | No module-specific required field |
| `cpi` | `pairs` (explicit pairs), `popfreq` (population frequencies), `cutoffs` (selected panels) | `cutoff_mode` (`all`, `panel` or `named`), optional finite `err_const` in `(0, 1]` |
| `cpin` | `trios` (explicit trios), `popfreq` (population frequencies), `markers` (panel with REF/ALT alleles or `null`) | No module-specific required field |

All steps accept a `scientific_settings` object in `parameters` for module-specific overrides. Downstream steps also accept `marker_type: "SNP"` or `"DNP"`. The validator infers the type if omitted and checks it if supplied. Each downstream analysis uses one table type. Frequencies and panels must use the corresponding coordinates. The engine checks their contents during execution.

`nipat settings` lists defaults, types, bounds, cross-parameter constraints and model constants. `nipat settings --export FILE` writes reusable JSON for `--scientific-config FILE`. Command-line overrides such as `--set module.parameter=value` take precedence over that file. Validation rejects unknown keys, nonfinite values, incorrect types and invalid threshold combinations. Python and R use the same registry. The client records the settings in the steps and run metadata. The registry documents formulas and other fixed model properties separately from the editable settings.

In `bam` mode, SNPcall requires a sample of kind `bam` and a FASTA reference. In `pileup` mode it requires a sample of kind `snp-pileup` and `reference: null`. An external pileup retains the acquisition settings of its producer. NewPat cannot infer those settings from the imported file.

## Typed references and family roles

Contamination, CPI and CPIN accept the following table references.

- `{"sample": "table_a"}` selects a registered `dnp-table` or `snp-table` sample.
- `{"step": "dnp", "output": "dnp-tables", "sample": "sample_a"}` selects the individual table produced by that DNPcall step for the sample.
- `{"step": "snp_a", "output": "snp-tables", "sample": "sample_a"}` selects the table produced by that SNPcall step for the sample.

A reference to a producing step creates a dependency. SNPcall produces `snp-tables` and DNPcall produces `dnp-tables`. A Contamination summary, a CPI/CPIN result or a guessed path to a future output cannot serve as a count-table reference.

Each CPI pair contains `id`, `mother` and `father`. The `mother` reference identifies the **maternal cfDNA table** and `father` the **paternal sample table**. The plan declares these roles explicitly. One sample cannot occupy both roles in a CPI step, even if two different caller steps process it. Multiple pairs may share a sample in the same role. Duplicate pairs are invalid. The validator checks the declared relationships. The person preparing the plan verifies which biological material each sample contains.

Each CPIN trio contains an `id` and three table references of the same marker type, `mother`, `father` and `child`. Their sample IDs must be distinct. Multiple trios may share a sample in the same role. Duplicate trios and contradictory roles are invalid. The maternal role in postnatal CPIN identifies the mother's sample. Prenatal CPI specifically expects maternal cfDNA.

Single-module native requests combine local IDs with filename prefixes. For example, `A:A:A` is valid for CPIN with prefixes `Mother`, `Father` and `Child` when it selects three distinct files and samples. Plans use global references and require no such naming convention.

| `cutoff_mode` | Required `cutoffs` value |
| --- | --- |
| `all` | Empty list `[]`, for all sites without a cutoff panel |
| `panel` | One object with `label: ""` and the panel `path` |
| `named` | One or more objects, each with a nonempty `label` and a `path` |

Cutoff labels must be unique. Commas, `=`, control characters and leading or trailing whitespace are invalid. Optional `err_const` overrides the error constant for the selected marker type and must be in `(0, 1]`. The configurable defaults are `err_const_snp = 0.001` and `err_const_dnp = 0.0000892303778101497`. Both exclude zero.

## Example: DNPcall, Contamination and CPI

This plan calls two BAMs once and passes the resulting counts to both downstream analyses. Contamination estimation leaves the CPI input intact. `validate-plan` accepts the example without any data files. Execution requires the inputs mounted at the listed paths, the FASTA indexes and a new destination directory.

```json
{
  "schema_version": 1,
  "samples": [
    {
      "id": "cfDNA_a",
      "kind": "bam",
      "path": "/workspace/inputs/bams/sample_0001.bam"
    },
    {
      "id": "paternal_a",
      "kind": "bam",
      "path": "/workspace/inputs/bams/sample_0002.bam"
    }
  ],
  "steps": [
    {
      "id": "dnp",
      "workflow": "dnp-call",
      "inputs": {
        "samples": ["cfDNA_a", "paternal_a"],
        "reference": "/workspace/inputs/reference.fa",
        "panel": "/workspace/inputs/dnp.tsv"
      },
      "parameters": {"parallel": false}
    },
    {
      "id": "contamination",
      "workflow": "contamination",
      "inputs": {
        "samples": [
          {"step": "dnp", "output": "dnp-tables", "sample": "cfDNA_a"},
          {"step": "dnp", "output": "dnp-tables", "sample": "paternal_a"}
        ],
        "panel": "/workspace/inputs/dnp.tsv"
      },
      "parameters": {}
    },
    {
      "id": "cpi",
      "workflow": "cpi",
      "inputs": {
        "pairs": [
          {
            "id": "pair_a",
            "mother": {"step": "dnp", "output": "dnp-tables", "sample": "cfDNA_a"},
            "father": {"step": "dnp", "output": "dnp-tables", "sample": "paternal_a"}
          }
        ],
        "popfreq": "/workspace/inputs/popfreq.tsv",
        "cutoffs": []
      },
      "parameters": {"err_const": 0.0000892303778101497, "cutoff_mode": "all"}
    }
  ]
}
```

## Validation result

The Python API `nipat_scientific.plan.validate_plan(document)` returns a new object and leaves its input intact.

- `schema_version: 1` identifies the report format.
- `plan` contains the canonical request.
- `execution_order` lists step IDs in dependency order.

The canonical sample registry is sorted by ID. Among steps whose dependencies are satisfied, the validator chooses the lexicographically smallest ID first. For the example, the order is `dnp`, `contamination`, `cpi`. The order of samples within a step, pairs and panels is preserved. The executor can group independent SNP steps within the shared budget, including in mixed plans.

Validating `report["plan"]` again produces the same report. The entire report cannot serve as a request because `execution_order` is derived from the references. The validator rejects cycles and references to missing steps, samples or output types.

The execution owns the `work` and `output` directories. The plan identifies samples by ID. For CPI and CPIN, the executor translates explicit pairs and trios into native filenames and records how the declared families, role-specific inputs and native outputs correspond. Users can keep the original filenames.

## Plan execution

```sh
python3 /opt/nipat/engine/main.py execute-plan \
  --plan /workspace/run/work/engine-plan.json \
  --run-dir /workspace/run/output/workflow
```

`execute-plan` uses the same request structure as `validate-plan` and adds runtime checks. Its default output includes a summary and the state file path. With `--json`, it writes the full report to stdout and progress messages to stderr. Both forms use the same exit codes. The engine descriptor reports `plan_execution.interface: workflow-plan-execution-v2`, workflows `dnp-call`, `snp-call`, `contamination`, `cpi` and `cpin`, scheduling `dependency-order-with-bounded-independent-snp` and `resume: false`.

The parent directory must exist and the destination itself must be new, even if an existing directory is empty. Before creating it, the engine checks the whole plan, the executable workflows and the inputs already available, including required references, panels, indexes and aliases. It verifies a step's output tables when they become available and before a dependent step uses them.

DNPcall expects `sample_0001.bam`, `sample_0002.bam` and subsequent aliases in `inputs.samples` order. The internal paths must work with the R interface and its samtools calls. The client creates read-only mounts without copying the BAMs. A plan with several DNPcall steps must respect this mapping in every step. An incompatible alias order is rejected. Plan ID `cfDNA_a`, for example, can map to alias `sample_0001`. The results record that mapping.

Downstream steps wait for their tables. The scheduler groups ready independent SNPcall steps under one process budget, including in mixed plans. Work with unknown memory requirements initially admits one sample. Child sample workers use serial inner R pools. Explicit `serial` mode limits computation to one process. The shared execution policy determines actual DNP parallelism, including when the DNP `parallel` parameter is set.

Contamination receives individual SNP or DNP tables and records both the sample and the producing step. It stages tables as `table_0001.txt`, `table_0002.txt` and so on in the consumer's declared order. The state records the original sample identity separately.

### SNPcall preparation and sample identity

Each SNPcall step selects one ID from `samples`, a SNP panel and either `bam` or `pileup` mode. DNPcall and SNPcall can read the same registered BAM independently. Different SNPcall steps have separate outputs. Their tables require references of type `snp-tables`.

The preflight checks all panels and external inputs before creating the destination. BAM input requires the FASTA and its indexes. Pileup input requires the QNAME column. Execution uses the same adapter as single-module SNPcall. BAM mode writes `work/snp_regions.bed`, runs samtools to generate `work/pileup.txt` and verifies its format before starting R. If samtools fails or receives an interrupt, R does not start. Pileup mode reads the supplied file directly.

The normalized panel columns are `chr`, `pos`, `ref` and `alt`. The three-column form with `pos=chr:position`, `ref` and `alt` is also supported. As in SNPcall 2.0, the samtools default here is `-d 0`. Users can configure `max_depth` and the other acquisition parameters. R uses reference bases and quality values from the pileup and groups observations by SNP and QNAME. Changing acquisition settings leaves an imported pileup unchanged.

Each step writes the scientific table to `output/SNPcall_output.txt`. On completion, `artifacts.snp-tables` associates the sample ID with its relative output path and SHA-256 digest. `artifacts.preparation` lists generated files by type (`regions-bed` or `pileup`), path and SHA-256. For an imported pileup this list is empty.

The SNPcall 2.0 table includes `N_REF`, `N_ALT` and `N_Other` counts, genotype log-likelihoods `GL0`, `GL1` and `GL2`, the `GT` genotype and indel statistics. CPI, Contamination and CPIN consume the SNP coordinates and model directly.

For distinct samples that share the same panel, reference and mode, finalization creates `snp_summary/group_0001` and subsequent groups. They contain merged genotypes, per-sample resources, labels and plots of missing genotypes and sample intersections. Repeated analysis of one sample does not create an additional individual. The individual tables and checksums remain available. The UpSet plot counts a genotype as assigned when it differs from `NA`.

### CPI preparation and pair identity

CPI accepts registered `dnp-table` or `snp-table` samples and explicit DNPcall or SNPcall results. Each step uses one marker type and its matching population frequencies. The plan declares `mother` and `father` for each pair. Both roles cannot refer to the same sample.

The first occurrence of a table, in pair order and then maternal/paternal role order, receives ID `s0001`, `s0002` and so on. The engine prepares a reference shared within one role once. It calls the CPI adapter with internal file prefixes `Mother` and `Father`. The declared biological roles remain in the plan.

R keeps its native pair IDs in the CSV and PDFs. The step state maps each declared pair to its native name, such as `Mothers0001-Fathers0002_DNPs`, its summary rows and its PDF.

| Mode | Summary rows |
| --- | --- |
| `all` | One row per pair, without a `Cutoff` column |
| `panel` | One row per pair, with the normalized panel path in `Cutoff` |
| `named` | One row per pair and label using the label declared in the plan |

The script writes `Summary_FetalFraction_CPI.csv`, one PDF per pair and `All_CPIplots.pdf` in `plots`, and curves for each pair and panel in `curves`. The curves use intervals of equivalent thresholds. There is no per-site CPI table. The executor checks the summary columns, expected pair and cutoff combinations, and presence and PDF headers of required plots. An incomplete CSV, duplicate rows or missing plots prevent completion. These structural checks do not determine the biological plausibility of a value.

### CPIN preparation and trio identity

CPIN accepts SNP or DNP tables, matching population frequencies and explicit trios. `inputs.markers` is `null` for all sites or points to a panel with coordinates **and REF/ALT alleles**. A coordinate list alone lacks the alleles required for this input.

`scientific_settings.site_selection` accepts `other_allele`, `all` or `both`. Other settings include minimum child read counts, error constants and genotype thresholds. The engine prepares shared tables once. `trio_mapping` links the plan ID, the three roles and the native trio identifier.

Outputs include `Summary_Postnatal_CPI.txt`, site details in `sites`, interval curves in `curves`, individual trio/analysis PDFs in `plots` and `All_CPIplots.pdf` at the root of the output directory. The engine checks the summary, expected trio/analysis combinations, tables and PDFs. Successful mappings appear in `artifacts.cpin-trios`.

### Evidence and states

| Path relative to `--run-dir` | Contents |
| --- | --- |
| `plan.json` | Canonical plan for the run |
| `workflow-state.json` | Overall state, step states and commands, and output-to-sample mapping |
| `steps/<id>/request.json` | Concrete request for the step adapter |
| `steps/<id>/command.log` | R process stdout and stderr |
| `steps/<id>/preparation.log` | samtools messages for SNPcall steps that start from BAM |
| `steps/<id>/work` | Panels, lists and tables prepared for R |
| `steps/<id>/work/effective-scientific-settings.json` | Effective parameters and model constants |
| `steps/<id>/output` | Scientific results for the step |

The engine replaces the state file atomically. Overall states are `running`, `succeeded`, `failed` and `cancelled`. Steps can also be `pending` or `blocked`. The result collections `dnp-tables`, `snp-tables` and `contamination-tables` record the sample, internal name, path relative to the run directory and SHA-256 digest. Contamination also records each source table and a separate summary path and checksum.

For DNPcall, `artifacts.dnp-summary.genotypes` identifies the verified aggregate genotype table by path and SHA-256. The engine checks its alleles and genotypes against the individual tables for every locus and sample. Older runs may lack this field.

For SNPcall from BAM, `preparation_command`, `preparation_log` and `preparation_exit_code` record the last samtools command, its log and its exit code. Preparation reads the BAM header before producing the pileup. After verification, `preparation_artifacts` records the BED and pileup before R starts. These records remain available even if R fails.

CPI records `pair_mapping` before preparing files or starting R. This map contains the `pair` ID, the `mother` and `father` references and `native_pair`. It can identify partial outputs after failure or cancellation. After output verification, the engine adds the following fields to `artifacts`.

| Field | Contents |
| --- | --- |
| `summary` | Summary CSV path and SHA-256 |
| `cpi-pairs` | Pairs with `pair`, `mother`, `father`, `native_pair`, `plot` and `summary_rows` |
| `combined-plot` | Path and SHA-256 of `All_CPIplots.pdf` |

`pair` keeps the plan ID and `mother` and `father` keep their input references. `plot` records the pair PDF path and checksum. Each entry in `summary_rows` contains `row`, numbered from 1 excluding the CSV header, and `cutoff`, which is `null` in all-sites mode, the internal path for a single panel or the declared label for a named panel. The mapping preserves the native scientific output files.

An error or interruption stops the plan and marks every unstarted step `blocked`, including independent steps. Earlier results remain available. An R process that exits zero but omits required outputs cannot complete a step. These states describe technical execution. Scientific interpretation of the sample and model is a separate task.

Cancellation reaches the scientific process group, including its children. The client allows a shutdown interval before forcibly removing the container. A shutdown or forced stop can prevent the final update. A stale `running` state establishes neither success nor a currently active process. A retry requires a new run directory.

The exit code is `0` only if every step completes. Validation errors return `2`. A scientific failure propagates the process exit code. An interruption returns `128 + signal number`. The plan state records the steps that ran. The client's `run.json` adds host inputs, image identity and application identity.

## Validation errors and limits

The Python API raises `PlanValidationError`, a subclass of `ValidationError`, with a stable `code` attribute. Interfaces can render the diagnostic message in the selected language while preserving the code.

| Code | Meaning |
| --- | --- |
| `plan.schema` | Unsupported contract version |
| `plan.fields` | Missing or unknown fields, or incorrect object structure |
| `plan.identifier` | Invalid identifier |
| `plan.path` | Invalid container path |
| `plan.list` | Missing, empty or incorrectly typed required list |
| `plan.duplicate` | Duplicate identity, sample path, reference or pair |
| `plan.sample_missing` | Sample absent from registry |
| `plan.sample_kind` | Unknown or incompatible sample type |
| `plan.workflow` | Unsupported analysis |
| `plan.step_missing` | Producer absent from the plan |
| `plan.output_kind` | Incompatible output type or producer |
| `plan.output_sample` | Specified step does not produce the requested sample |
| `plan.cycle` | Cyclic dependency, including a step referring to itself |
| `plan.parameter` | Invalid parameter or value inconsistent with the mode |
| `plan.roles` | Inconsistent CPI or CPIN role assignment |
| `plan.marker_type` | Inconsistent declared marker type or mixed table types in one consumer |
| `plan.cutoff_mode` | Inconsistent cutoff mode or number of panels |
| `plan.cutoff_label` | Invalid cutoff label |

A structurally valid plan can still refer to missing files, malformed tables, an inappropriate genome reference or unsuitable samples. File preparation and output validation check the data the engine can inspect. Numerical regression tests and domain assessment address separate questions.

## Sample presentation

`presentation` contains exactly `samples` and `pairs`. The first maps every sample ID to its original name without path components. The second maps zero or more CPI pair IDs or CPIN trio IDs in the plan to readable labels. Validation rejects empty names, control characters, unknown IDs and incomplete sample mappings.

Each step writes its exports to `output/presentation`. The workflow-wide index is in `presentation` under the run root. Canonical outputs, dependencies and checksums remain distinct from presentation copies. See the [engine presentation contract](../engine/README.md#readable-labels).
