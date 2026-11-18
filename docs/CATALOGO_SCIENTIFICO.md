# Scientific parameter catalog

The catalog documents public arguments, calculation rules and input preparation for the five R programs distributed with NewPat. It is available in English and Italian without starting the scientific runtime or opening samples. In the terminal menu, choose **7 → 6** (Help and information → Scientific catalog), then a module and section. **L — Language** changes the language of the catalog view.

```sh
newpat parameters cpi --lang en
newpat parameters dnp-call --section rules --lang en
newpat parameters snp-call --section preparation --lang en
newpat parameters --json
```

In a source checkout use `python -m nipat`. The packaged Windows wrapper and macOS command launcher accept the same arguments. JSON includes both languages. The `--lang` and `--section` options control text display. [Platform launchers](GUIDA_UTILIZZO.md)

## Reading an entry

| Section | What it describes |
| --- | --- |
| Public R arguments | Required and optional arguments, native defaults and mappings to CLI and engine request fields. |
| Internal R rules | Formulae, filters, format assumptions and presentation rules. |
| Input preparation | Adapter transformations, their scope and relevant dependency defaults. |

A **direct** mapping passes the native meaning through. An **adapted** mapping prepares the representation required by R, such as a CPI sample directory. NewPat **manages** destinations when it assigns fixed names and paths within a run.

For an actual run, consult its `run.json` and `work/effective-scientific-settings.json`. The catalog distinguishes R defaults from client defaults. Imported pileups may have been produced with unknown acquisition settings. CPI panels called *cutoffs* select coordinates by membership. Their names do not impose numerical thresholds on samples.

`newpat settings` lists configurable parameters, ranges, model constants and cross-parameter constraints. Global options `--scientific-config PATH` and `--set module.parameter=value` apply validated overrides. [User guide](GUIDA_UTILIZZO.md)

Global scheduling options precede the analysis command. `--execution-mode auto` lets the run's resource budget and work determine concurrency. `--execution-mode serial` runs one compute process at a time. `--max-workers` caps the automatic pool. Nested pools remain serial. DNP accepts `--parallel` for CLI compatibility. The global policy controls the actual number of workers.

DNP defaults are `--dnp-block-mib 32` and `--dnp-block-loci 64`. These targets describe raw input and loci per block. An indivisible group can exceed them. R memory depends on the expanded observations. Samples and blocks share a task queue. `work/dnp-blocks.json` records the resulting blocks and workers. The [input and output checks](INPUT_VALIDATION.md) describe preparatory validation separately from the scientific rules.

## Provenance

Every module entry identifies the R source path, SHA-256 and reviewed line ranges across the script. Preparation entries identify adapter sources and their hashes. CI checks both sets of references in the checkout, including the Dockerfile that pins samtools. The engine rechecks available embedded sources in the installed image. Client-only and build-only files are checked during CI.

The client ships a local catalog. To query the copy packaged with the engine, run the following inside the scientific image.

```sh
python3 /opt/nipat/engine/main.py catalog cpi --json
```

The engine identity includes catalog and plan-validator hashes. These identify the reviewed files. Numerical tests and domain validation address correctness. The [workflow contract](WORKFLOW_CONTRACT.md) explains typed links between analyses and the distinction between plan validation and execution.
