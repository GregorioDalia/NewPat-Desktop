# Prenatal CPI and fetal fraction

NewPat estimates fetal fraction and the Combined Paternity Index (CPI) for explicit pairs of maternal cell-free DNA and putative-father samples. The module accepts one marker type per run, SNP or DNP. The scientific runtime supplies R, dependencies, settings, bounded scheduling and plotting helpers. [Upstream module and examples](https://github.com/lpistacchia/NEWPAT/tree/c753afc4be62dfc0b81b8cb683a6e850516f5ffd/CPI_from_cffDNA) · [License](../LICENSE)

## Run the bundled example

From the root of this repository, run the configured NewPat CLI with the [bundled inputs](examples/inputs). The first pair selects `MotherA1.txt` and `FatherA1.txt`; the second selects `MotherA2.txt` and `FatherA2.txt`. The default role prefixes are `Mother` and `Father`.

```sh
newpat cpi --input-dir scientific/vendor/NEWPAT/CPI_from_cffDNA/examples/inputs/DNPcall_output --pairs A1:A1,A2:A2 --popfreq scientific/vendor/NEWPAT/CPI_from_cffDNA/examples/inputs/pop_allFreq.txt --panel scientific/vendor/NEWPAT/CPI_from_cffDNA/examples/inputs/DNPpanel.txt
```

For a single pair, use `--pairs A1:A1`. Omit `--panel` to use eligible loci without a cutoff panel. To compare multiple selections, supply repeated `--cutoff LABEL PATH` options. The labels identify coordinate panels. [User guide](../../../../docs/USER_GUIDE.md) · [Engine contract](../../../../engine/README.md#prenatal-cpi)

## Inputs and settings

The count tables contain coordinates, `REF`, `ALT`, `N_REF`, `N_ALT`, `N_Other` and `total_count`. For SNPs, the frequency table uses `chr,pos,Ref_f.pop,Alt_f.pop`. For DNPs it uses `chr,pos1,pos2,Ref_f.pop,Alt_f.pop`. Frequencies refer to the corresponding REF and ALT alleles. A locus needs matching population frequencies to contribute a PI.

The module selects the error constant by marker type. If the putative father is homozygous for the allele opposite to the inferred paternal allele, the model uses the mismatch constant in place of zero. The defaults are 0.001 for SNPs and 0.0000892303778101497 for DNPs. Maternal informative sites can be filtered by minor-allele read count, percentage, or both. With neither setting specified, the minimum is two reads. The percentage is 100 × minor-allele reads / (REF reads + ALT reads), before the diploid factor used to estimate fetal fraction. Equality passes each active threshold. With only the percentage enabled the curve starts at one read.

Inspect settings with `newpat settings cpi`. Place an override such as `--set cpi.min_fetal_reads=5` before the `cpi` subcommand, or use `--scientific-config PATH`. Settings include genotype and Other-read thresholds, marker-specific mismatch constants and plot guides. The direct R adapter accepts native argument names. Its explicit `--err_const` overrides the detected marker's constant, including a separately supplied marker-specific value. NewPat records the effective scientific settings in the run.

The optional setting `cpi.min_coverage` requires each parent to meet the same minimum total read count (REF + ALT + Other). The Other fraction must be at most `cpi.other_fraction_max` in each sample (default 0.10). A site exactly on either limit passes.

By default the prenatal CPI uses putative heterozygous fetal sites (HET). Enable `cpi.include_homozygous_child` to include presumed homozygous fetal sites (HOM). The experimental rule considers sites where the maternal REF and ALT counts support a single expected allele. The inferred paternal allele is the maternal allele at HOM sites and the non-maternal allele at HET sites. Only finite, positive paternity indices contribute to the CPI and to the matching and mismatching counts. The HOM contribution stays fixed across read thresholds. Fetal fraction and the median fetal-read threshold use HET candidates alone.

## Results

`output/Summary_FetalFraction_CPI.csv` records each pair and selected panel, the effective filters, fetal fraction, CPI statistics, separate HET and HOM counts and their contributions to log₁₀(CPI). `CPI_medianFF` is the log₁₀(CPI) at the median-support threshold. With no eligible HET candidates, this value and fetal fraction are unavailable even when a HOM contribution exists.

For each pair and panel, `*_CPI_iterations.csv` records the threshold series and `*_HOM_child_sites.txt` lists qualifying HOM sites with their paternal allele, mismatch status and PI. With HOM disabled, the site table contains its header only. `curves/` holds the plotting data and `plots/` holds the per-pair and combined PDFs. The distribution includes [worked SNP and DNP examples with the expected tables](../../../../tests/fixtures/prenatal_cpi/README.md).

## Upstream contact and citations

Upstream author: Letizia Pistacchia. The upstream project requests both citations.

- Pistacchia L et al. DNPcall: a new pipeline for accurate double nucleotide polymorphism calling. *Bioinformatics Advances*. 2025. [DOI](https://doi.org/10.1093/bioadv/vbaf209)
- D’Atanasio E et al. A new noninvasive prenatal paternity test based on double nucleotide polymorphisms abates sequencing uncertainties and improves sensitivity. *Genome Research*. 2026. [DOI](https://doi.org/10.1101/gr.281702.125)
