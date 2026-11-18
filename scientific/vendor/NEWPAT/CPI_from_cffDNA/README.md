# Prenatal CPI and fetal fraction

NewPat estimates fetal fraction and the Combined Paternity Index (CPI) for explicit pairs of maternal cell-free DNA and putative-father samples. The module accepts one marker type per run, SNP or DNP. The scientific runtime supplies R, dependencies, settings, bounded scheduling and plotting helpers. [Upstream module and examples](https://github.com/lpistacchia/NEWPAT/tree/9c2a8be60afcb944153710da6a61cd0559e2b4cf/CPI_from_cffDNA) · [License](../LICENSE)

## Run the bundled example

From the root of this repository, run the configured NewPat CLI with the [bundled inputs](examples/inputs). The first pair selects `MotherA1.txt` and `FatherA1.txt`; the second selects `MotherA2.txt` and `FatherA2.txt`. The default role prefixes are `Mother` and `Father`.

```sh
newpat cpi --input-dir scientific/vendor/NEWPAT/CPI_from_cffDNA/examples/inputs/DNPcall_output --pairs A1:A1,A2:A2 --popfreq scientific/vendor/NEWPAT/CPI_from_cffDNA/examples/inputs/pop_allFreq.txt --panel scientific/vendor/NEWPAT/CPI_from_cffDNA/examples/inputs/DNPpanel.txt
```

For a single pair, use `--pairs A1:A1`. Omit `--panel` to use eligible loci without a cutoff panel. To compare multiple selections, supply repeated `--cutoff LABEL PATH` options. The labels identify coordinate panels. [User guide](../../../../docs/GUIDA_UTILIZZO.md) · [Engine contract](../../../../engine/README.md#cpi)

## Inputs and settings

The count tables contain coordinates, `REF`, `ALT`, `N_REF`, `N_ALT`, `N_Other` and `total_count`. For SNPs, the frequency table uses `chr,pos,Ref_f.pop,Alt_f.pop`. For DNPs it uses `chr,pos1,pos2,Ref_f.pop,Alt_f.pop`. Frequencies refer to the corresponding REF and ALT alleles. A locus needs matching population frequencies to contribute a PI.

The module selects the error constant by marker type. If a putative father is homozygous for the maternal allele at an informative site, the model uses the mismatch constant in place of zero. The defaults are 0.001 for SNPs and 0.0000892303778101497 for DNPs. The default minimum minor-allele support in maternal cfDNA is two reads. The threshold controls eligible maternal sites, fetal-fraction estimation and the starting support for the CPI curve.

Inspect settings with `newpat settings cpi`. Place an override such as `--set cpi.min_fetal_reads=5` before the `cpi` subcommand, or use `--scientific-config PATH`. Settings include genotype and Other-read thresholds, marker-specific mismatch constants and plot guides. The direct R adapter accepts native argument names. Its explicit `--err_const` overrides the detected marker's constant, including a separately supplied marker-specific value. NewPat records the effective scientific settings in the run.

## Results

`output/Summary_FetalFraction_CPI.csv` reports a row for each pair and selected cutoff. The CSV records maternal and paternal informative site counts, raw and percentage median fetal fraction, minimum, maximum, mean and median log₁₀(CPI), `CPI_medianFF` (the log₁₀(CPI) at the selected median-support threshold), `Min_fetal_reads`, `Marker_type` and `Error_constant`. The `curves/` directory contains the threshold data for each pair and cutoff. The `plots/` directory holds per-pair PDFs and `All_CPIplots.pdf`. Counts of matching and mismatching sites help interpret the change in log₁₀(CPI) across support thresholds. [Scientific reference and regression fixtures](../../../README.md)

## Upstream contact and citations

Upstream author: Letizia Pistacchia. The upstream project requests both citations.

- Pistacchia L et al. DNPcall: a new pipeline for accurate double nucleotide polymorphism calling. *Bioinformatics Advances*. 2025. [DOI](https://doi.org/10.1093/bioadv/vbaf209)
- D’Atanasio E et al. A new noninvasive prenatal paternity test based on double nucleotide polymorphisms abates sequencing uncertainties and improves sensitivity. *Genome Research*. 2026. [DOI](https://doi.org/10.1101/gr.281702.125)
