# Scientific parameter catalog

The catalog documents public arguments, calculation rules and input preparation for the six R programs distributed with NewPat. It is available in English and Italian without starting the scientific runtime or opening samples. In the terminal menu, choose **7 → 6** (Help and information → Scientific catalog), then a module and section. **L — Language** changes the language of the catalog view.

```sh
newpat parameters cpi --lang en
newpat parameters dnp-call --section rules --lang en
newpat parameters snp-call --section preparation --lang en
newpat parameters --json
```

In a source checkout use `python -m newpat`. The packaged Windows wrapper and macOS command launcher accept the same arguments. JSON includes both languages. The `--lang` and `--section` options control text display. [Platform launchers](USER_GUIDE.md)

## Reading an entry

| Section | What it describes |
| --- | --- |
| Public R arguments | Required and optional arguments, native defaults and mappings to CLI and engine request fields. |
| Internal R rules | Formulae, filters, format assumptions and presentation rules. |
| Input preparation | Adapter transformations, their scope and relevant dependency defaults. |

A **direct** mapping passes the native meaning through. An **adapted** mapping prepares the representation required by R, such as a CPI sample directory. NewPat **manages** destinations when it assigns fixed names and paths within a run.

For an actual run, consult its `run.json` and `work/effective-scientific-settings.json`. The catalog distinguishes R defaults from client defaults. Imported pileups may have been produced with unknown acquisition settings. CPI panels called *cutoffs* select coordinates by membership. Their names do not impose numerical thresholds on samples.

`newpat settings` lists configurable parameters, ranges, model constants and cross-parameter constraints. Global options `--scientific-config PATH` and `--set module.parameter=value` apply validated overrides. [User guide](USER_GUIDE.md)

Global scheduling options precede the analysis command. `--execution-mode auto` lets the run's resource budget and work determine concurrency. `--execution-mode serial` runs one compute process at a time. `--max-workers` caps the automatic pool. Nested pools remain serial. DNP accepts `--parallel` for CLI compatibility. The global policy controls the actual number of workers.

DNP defaults are `--dnp-block-mib 32` and `--dnp-block-loci 64`. These targets describe raw input and loci per block. An indivisible group can exceed them. R memory depends on the expanded observations. Samples and blocks share a task queue. `work/dnp-blocks.json` records the resulting blocks and workers. The [input and output checks](INPUT_VALIDATION.md) describe preparatory validation separately from the scientific rules.

## Reading the desktop results

DNPcall and SNPcall count REF, ALT and other reads and assign a genotype at each locus. A genotype of `0/0` means two reference alleles. A genotype of `NA` means the caller could not assign a genotype there. The genotype alone gives no paternity classification.

| Desktop result | How to read it |
| --- | --- |
| Contamination | The results table stores the mean across informative sites as a proportion. The desktop displays it as a percentage (for example, `0.04` appears as `4%`). Read it together with the informative site count. With no informative sites the estimate is `NA`. An estimated zero with informative sites is a possible numerical result. |
| Prenatal CPI | For the selected pair and site panel, `CPI_medianFF` is the log₁₀ CPI at the threshold closest to the rounded median number of fetal reads. The median fetal fraction is reported separately. The desktop compares `CPI_medianFF` with the two plot guides saved for that step. The defaults are −4 and +4. When a reported value equals a guide, the display identifies the boundary because the R summary rounds to three decimal places. These guides describe the plot. |
| Postnatal CPI | One result per trio. Read the CPI together with its base-10 logarithm, contributing site count and selected mother–child genotype combinations. The site table records each PI and the reasons for exclusion. For a supported estimate, the reference band compares the recorded log₁₀(CPI) with the two saved numeric limits. A value exactly on a limit is marked as such. |

**Population allele frequencies** are supplied in a per-locus input table for each CPI marker type. `Ref_f.pop` and `Alt_f.pop` give the REF and ALT frequencies in the selected population. The catalog entry `(0, 1]` documents the allowed values. Each must be finite, greater than zero and at most one. At loci with an obligatory paternal allele, its frequency is the denominator of the site paternity index. For a heterozygous mother and heterozygous child in postnatal CPI, the denominator is the sum of the two frequencies. A zero frequency would make that division undefined. The frequencies in the demo were assigned for its simulated loci. For an analysis, record the population table and its source. [CPI input checks](INPUT_VALIDATION.md#file-requirements)

## Provenance

Every module entry identifies the R source path, SHA-256 and reviewed line ranges across the script. Preparation entries identify adapter sources and their hashes. CI checks both sets of references in the checkout, including the Dockerfile that pins samtools. The engine rechecks available embedded sources in the installed image. Client-only and build-only files are checked during CI.

The client ships a local catalog. To query the copy packaged with the engine, run the following inside the scientific image.

```sh
python3 /opt/newpat/engine/main.py catalog cpi --json
```

The engine identity includes catalog and plan-validator hashes. These identify the reviewed files. Numerical tests and domain validation address correctness. The [workflow contract](WORKFLOW_CONTRACT.md) explains typed links between analyses and the distinction between plan validation and execution.
