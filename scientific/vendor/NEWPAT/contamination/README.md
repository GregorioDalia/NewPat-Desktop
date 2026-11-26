# Contamination estimation

This NewPat module estimates unexpected-allele read fractions at sites classified as homozygous. It accepts either SNP or DNP counts. NewPat supplies the R runtime and helpers, runs independent work within a shared budget and writes ordered results. [Upstream module and examples](https://github.com/lpistacchia/NEWPAT/tree/9c2a8be60afcb944153710da6a61cd0559e2b4cf/contamination) · [License](../LICENSE)

## Run the bundled example

Run this command with the configured NewPat CLI from the root of the NewPat repository. The example directory contains the panel alongside the two count tables, so select the sample files explicitly.

```sh
newpat contamination --input scientific/vendor/NEWPAT/contamination/examples/inputs/sample1.txt --input scientific/vendor/NEWPAT/contamination/examples/inputs/sample2.txt --panel scientific/vendor/NEWPAT/contamination/examples/inputs/DNPpanel.txt
```

For your own directory containing only calling-output tables, use `--input-dir` to select them recursively. Keep the output and panel outside that directory. Both SNP and DNP files must have the corresponding coordinate columns and `N_REF`, `N_ALT`, `N_Other`. Use one marker type per analysis. SNP coordinates are `chr,pos`; DNP coordinates are `chr,pos1,pos2`. [Bundled inputs](examples/inputs) · [Synthetic checks and expected results](../../../../tests/fixtures/contamination/README.md) · [User guide](../../../../docs/USER_GUIDE.md)

## Calculation and settings

The default filters require a nonzero REF+ALT count, an Other fraction of at most 0.10 (`N_Other / (N_REF + N_ALT + N_Other)`) and a REF fraction of at least 0.90 for REF homozygotes or at most 0.10 for ALT homozygotes. Unexpected reads are ALT observations at a REF homozygote and REF observations at an ALT homozygote. Each retained site's estimate is `N_unexpected / (N_REF + N_ALT)`. The sample estimate is the arithmetic mean across retained sites. Multiply a reported proportion by 100 to express it as a percentage. Sequencing error can also contribute unexpected reads.

Sites with zero unexpected reads are included by default. Set the global option `--set contamination.include_zero=false` before `contamination` to exclude them. Check all supported thresholds with `newpat settings contamination`. The native R adapter also accepts mutually exclusive explicit `--include_zero` and `--exclude_zero` controls. NewPat records effective settings per run.

## Output

The run writes tab-separated `contamination_<sample>.txt` for the retained sites and `contamination_summary.txt` for per-sample results. Summary fields are `individuo` (sample label), `informative_sites`, `mean_contamination` and `sd_contamination`. With zero retained sites, both estimates are `NA`. With one site the mean is available and the standard deviation is `NA`.

## Upstream contact and citations

Upstream author: Letizia Pistacchia. The upstream project requests both citations.

- Pistacchia L et al. DNPcall: a new pipeline for accurate double nucleotide polymorphism calling. *Bioinformatics Advances*. 2025. [DOI](https://doi.org/10.1093/bioadv/vbaf209)
- D’Atanasio E et al. A new noninvasive prenatal paternity test based on double nucleotide polymorphisms abates sequencing uncertainties and improves sensitivity. *Genome Research*. 2026. [DOI](https://doi.org/10.1101/gr.281702.125)
