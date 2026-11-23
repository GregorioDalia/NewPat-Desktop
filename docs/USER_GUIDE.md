# Input files, commands and workflows

Use the [desktop guide](GUI.md) for interactive experiments. The command line exposes the same scientific modules and lets you keep a reproducible command with each run.

<a id="comandi-diretti"></a>

## Choose your launcher

| Platform | How to start |
| --- | --- |
| Windows x64 | Start **NewPat** from the Start menu for the desktop. Use `newpat.cmd` in the installed application directory for commands. [Windows guide](WINDOWS_INSTALLER.md) |
| macOS 14 or later | Open **NewPat** in Applications. For commands use `"/Applications/NewPat.app/Contents/Resources/NewPat.command"`. Select the installer for your Mac's processor. [macOS guide](MACOS_INSTALLER.md) |
| Ubuntu 24.04 x86_64 | Run `newpat` for the desktop, `newpat wizard` for the text menu, or `newpat --help` for commands. [Ubuntu guide](LINUX_INSTALLER.md) |

For a Windows setup installation, open PowerShell and set the launcher variable once for the examples in this guide:

```powershell
$appDir = (Get-ItemProperty -LiteralPath 'HKCU:\Software\NIPAT\desktop' -Name app_dir).app_dir
$newpat = Join-Path $appDir 'newpat.cmd'
& $newpat --version
& $newpat --help
```

For a complete ZIP installation, set `$newpat` to the full path of `newpat.cmd` in the prepared application folder. Supply your own data paths in the commands below. Global options such as `--runs-dir`, `--execution-mode`, `--scientific-config` and `--dry-run` go before the module name. Each module has its own `--help`. A successful dry run writes a `planned` request; use a fresh run name for the calculation.

<a id="percorsi-e-cartelle"></a>

## File locations

| Installation | Default results directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\NIPAT-Desktop\runs` |
| macOS | `~/Library/Application Support/NIPAT-Desktop/runs` |
| Ubuntu | `$XDG_DATA_HOME/nipat-desktop/runs`, or `~/.local/share/nipat-desktop/runs` when the variable is unset |
| Source checkout | A `runs` directory next to the checkout, unless the workspace or results directory is overridden |

Use the run's open-folder action to find an experiment if a custom directory was selected. Keep data and results in writable locations separate from the installed program. On Windows the runtime uses fixed local drives. On macOS the paths must be accessible to Lima. On Ubuntu they must be accessible to the local Docker Engine. Relative paths on the command line resolve from the current directory. Relative paths inside a BAM list resolve from the list file's directory.

<a id="input-dei-cinque-moduli"></a>

## Input formats and examples

### DNPcall

For double-nucleotide polymorphism (DNP) calling, supply one or more aligned BAMs, the reference FASTA and a DNP panel. Use repeated `--bam` arguments or `--bamlist` with one file per line and no header. Give `--reference` the sequence file itself. Keep its matching `.fai` index next to it; BGZF-compressed FASTA also requires `.gzi`. A suitable BAM index enables indexed acquisition. An unindexed BAM can use the scanning path.

The DNP panel contains five space- or tab-separated fields per line and no header: `chr pos1 pos2 REF ALT`. Use unique loci, adjacent positions (`pos1 >= 2` and `pos2 = pos1 + 1`) and two-base alleles made of A, C, G or T. Check that the BAM, reference and panel describe the same assembly and contigs.

```powershell
& $newpat dnp-call --bam ".\sample.bam" --reference ".\genome.fa" --panel ".\dnp-panel.txt"
```

### SNPcall

For single-nucleotide polymorphism (SNP) calling, supply a SNP panel and either a BAM with its indexed reference or a single-sample pileup. The panel is tab-separated with headers `chr`, `pos`, `ref`, `alt`. It can also contain `pos`, `ref`, `alt` with a coordinate such as `chr1:1770788` in `pos`. Each coordinate must be unique, with distinct reference and alternate bases. The chromosome name excludes whitespace and colons. For the three-base window, positions range from 2 through 2147483646.

Imported pileups are tab-separated, have no header and include QNAME (read names) in column seven. Their acquisition filters come from the command that generated them. For BAM input NewPat generates the pileup with read names; the default SNP acquisition uses `samtools mpileup -d 0`.

```powershell
& $newpat snp-call --pileup ".\sample.pileup" --panel ".\snp-panel.tsv"
```

`SNPcall_output.txt` records coordinates and alleles, `N_REF`, `N_ALT`, `N_Other`, `total_count`, the REF fraction among REF and ALT counts, natural-log genotype likelihoods (`GL0`, `GL1`, `GL2`), the assigned genotype (`GT`), indel discard counts and ratios, and paired `combined_bases` and `combined_counts` fields. `GT` can be `NA` when informative observations are absent or the other-base filter fails.

### Contamination

Give `--input` once per individual count table or `--input-dir` for recursive discovery of TXT and TSV files. The latter excludes the selected panel; use explicit inputs if the folder also contains summaries or unrelated tables.

Count tables need nonnegative integer `N_REF`, `N_ALT` and `N_Other` and unique coordinates (`chr,pos` for SNP or `chr,pos1,pos2` for DNP). Supply a matching coordinate panel. The other-base filter uses `N_Other / (N_REF + N_ALT + N_Other)`. The per-site estimate uses unexpected counts divided by `N_REF + N_ALT`. Check the number of informative sites alongside the mean and standard deviation. A fraction of `0.025` represents 2.5%.

```powershell
& $newpat contamination --input ".\sample-counts.txt" --panel ".\dnp-panel.txt"
```

### Prenatal CPI

Supply maternal cell-free DNA and alleged-father count tables, pair assignments and population allele frequencies. Count tables contain coordinates, `REF`, `ALT`, `N_REF`, `N_ALT`, `N_Other` and `total_count`. Population tables have the same marker coordinates and the columns `Ref_f.pop` and `Alt_f.pop`. Each locus is unique and both frequencies must be finite and in (0, 1]. Check warnings about frequencies that do not sum to one.

With the default prefixes, `--pairs A1:A1` selects `MotherA1.txt` and `FatherA1.txt` in the input directory. Separate multiple pairs with commas. For an individual CPI run, choose at most one panel-selection method: `--panel PATH`, repeated `--cutoff LABEL PATH`, or `--cutoff-map "LABEL=PATH,LABEL2=PATH2"`. Omitting these uses available sites. Repeated `--cutoff` arguments also work for paths containing commas or equals signs. `--err-const` accepts a finite run-specific error constant in (0, 1].

```powershell
& $newpat cpi --input-dir ".\pairs" --pairs "A1:A1" --popfreq ".\population.tsv"
```

### Postnatal CPI

Supply the mother, alleged father and child tables, trio assignments and population frequencies. Use three distinct samples per trio, the same coordinate scheme as the frequency table, and both REF and ALT alleles in an optional postnatal CPI filter panel. With the default prefixes, `--trios A:A:A` selects `MotherA.txt`, `FatherA.txt` and `ChildA.txt`. Separate multiple trios with commas. `cpin.site_selection` accepts `other_allele`, `all` and `both`.

```powershell
& $newpat cpin --input-dir ".\trios" --trios "A:A:A" --popfreq ".\population.tsv"
```

See [input validation](INPUT_VALIDATION.md) for file checks and warnings, and the [scientific catalog](SCIENTIFIC_CATALOG.md) for formulas, thresholds and settings.

## Inspect and set scientific parameters

`settings` displays effective settings and constants. `parameters` explains the scientific parameters, rules and input preparation. A JSON configuration can contain overrides for one or more modules. Repeated `--set module.key=value` arguments take precedence over the JSON configuration. NewPat records the effective settings with the results.

```powershell
& $newpat settings cpin
& $newpat parameters snp-call --section preparation --lang en
& $newpat settings --export ".\settings.json"
& $newpat --scientific-config ".\settings.json" --set cpin.min_child_reads=4 settings cpin
```

<a id="risultati-e-analisi-in-sequenza"></a>

## Build a workflow

With `workflow analyze`, choose the callers and the downstream analyses for each marker type. DNPcall and SNPcall produce independent count tables. Contamination, prenatal and postnatal CPI read the selected caller's tables directly. Each branch uses its own panel and population frequencies.

In this example the same two BAMs feed both callers. The DNP counts go to prenatal CPI and the SNP counts go to Contamination. Family roles refer to the IDs declared by `--sample`.

```powershell
& $newpat workflow analyze --caller both `
  --sample Plasma ".\plasma.bam" --sample Father ".\father.bam" `
  --reference ".\genome.fa" --dnp-panel ".\dnp-panel.txt" --snp-panel ".\snp-panel.tsv" `
  --dnp-analyses cpi --snp-analyses contamination `
  --pair Family1 Plasma Father --dnp-popfreq ".\dnp-frequencies.tsv"
```

Use `--pair ID MATERNAL_CFDNA FATHER` for prenatal CPI and `--trio ID MOTHER FATHER CHILD` for postnatal CPI. Assign the roles explicitly for each family. If both branches use a pair or trio, its sample IDs must be present in both. The shared `--analyses` option sets the downstream analyses for all selected branches; `--dnp-analyses` and `--snp-analyses` select individual branches. Each prenatal or postnatal CPI branch needs its corresponding frequencies.

**Presets.** `workflow dnp-contamination`, `workflow dnp-cpi` and `workflow dnp-contamination-cpi` use the DNP counts for their downstream stages. An optional `--snp-panel` adds SNP calling on the same BAMs. `workflow snp-batch` accepts multiple BAMs (or a BAM list) or multiple existing pileups. Use `workflow analyze` for explicit sample IDs and branch-specific choices.

```powershell
& $newpat workflow dnp-contamination --bam ".\a.bam" --bam ".\b.bam" `
  --reference ".\genome.fa" --panel ".\dnp-panel.txt"
& $newpat workflow snp-batch --bam ".\a.bam" --bam ".\b.bam" `
  --reference ".\genome.fa" --panel ".\snp-panel.tsv"
```

<a id="utilizzo-di-tabelle-già-disponibili"></a>

## Reuse existing count tables

Choose the existing-tables option in the workflow or use `workflow analyze --caller tables`. Supply `--dnp-table ID PATH` and/or `--snp-table ID PATH` for the branches being analyzed. Define the sample pairs or trios as for a BAM workflow. The source DNP run's `output/individual_outputs/` directory holds individual counts. Use the source sample map to preserve identities and record where each table came from.

## Text wizard and troubleshooting

Launch `wizard` from your platform's command line for the guided text menu. The numbered choices cover individual modules, compound workflows, configuration, the last run, help, environment checks and updates. The wizard supports arrow keys, Enter and the displayed shortcut keys. In text prompts the literal tokens `:indietro`, `:vuoto` and `:annulla` mean back, clear an optional value and cancel. Configure persistent defaults in the settings menu. Each analysis has its own sample IDs, family roles and run name.

Before starting, review the input files, settings and destination. The performance diagnostics option adds measurements for that run. Ctrl+C requests a stop and keeps the available logs. For a partially prepared Windows installation, open the setup log at `.runtime\installer\setup.log` under the application folder. For a failed run, open its HTML report and execution log; workflow steps also have their own status and command logs. Use `doctor --runtime` to check the engine and `self-test` to run the bundled numerical examples.

[Reading results](RUNS.md) · [Resource settings](RESOURCES.md) · [Performance diagnostics](PERFORMANCE.md) · [Reporting a validation case](VALIDATION.md)
