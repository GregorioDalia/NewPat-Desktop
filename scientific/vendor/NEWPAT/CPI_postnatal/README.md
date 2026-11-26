# Postnatal CPI

NewPat calculates the postnatal Combined Paternity Index (CPI) from mother, putative-father and child count tables and population frequencies. SNP and DNP are analyzed separately. NewPat supplies the R runtime, validates the role mapping and reuses samples shared across trios. [Upstream module and examples](https://github.com/lpistacchia/NEWPAT/tree/97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4/CPI_postnatal) · [License](../LICENSE)

## Run the local examples

The NewPat checkout includes two [synthetic family fixtures and their expected results](../../../../tests/fixtures/cpin/README.md). From the repository root, run either command with a configured NewPat CLI.

```sh
newpat cpin --input-dir tests/fixtures/cpin/DNP --trios M1:F1:C1 --popfreq tests/fixtures/cpin/DNP/population.txt --panel tests/fixtures/cpin/DNP/markers.tsv
newpat cpin --input-dir tests/fixtures/cpin/SNP --trios M1:F1:C1 --popfreq tests/fixtures/cpin/SNP/population.txt --panel tests/fixtures/cpin/SNP/markers.tsv
```

With the CLI's default prefixes, `M1:F1:C1` selects `MotherM1.txt`, `FatherF1.txt` and `ChildC1.txt`, in that order. Use `--mother-prefix`, `--father-prefix` and `--child-prefix` for other naming schemes. Supply comma-separated trios for a batch. Each trio requires three distinct physical files. The engine rejects duplicate trios and ambiguous filenames. The optional panel contains coordinates and REF/ALT alleles. Omitting it allows all otherwise eligible loci with population frequencies. [User guide](../../../../docs/USER_GUIDE.md) · [Engine contract](../../../../engine/README.md#postnatal-cpi)

## Model and settings

At each locus, the module checks the three samples separately. Each must have assigned genotypes, positive total coverage, REF or ALT reads, and an Other-read fraction at or below the configured maximum (default 0.10). Optional `min_coverage` applies to REF + ALT + Other in each sample. Opposite homozygous calls in the mother and child exclude the site.

All four compatible mother–child genotype combinations are enabled by default. Use `include_hom_hom`, `include_hom_het`, `include_het_hom` and `include_het_het` to select a subset. At least one must be enabled. An eligible site with an obligatory paternal allele contributes a PI of 1/f, 0.5/f or ε/f, according to the father's genotype. Here f is the population frequency of that allele and ε is the configured mismatch weight. The defaults are 0.001 for SNP and 0.0000892303778101497 for DNP, configured with `mismatch_probability_snp` and `mismatch_probability_dnp`. If the mother and child are both heterozygous, the site contributes 1/(f_REF + f_ALT) and is counted separately from matches and mismatches.

Inspect the settings with `newpat settings cpin`. For example, place `--set cpin.min_coverage=20` before the `cpin` subcommand to require at least 20 reads in each member of the trio.

## Results

| Output within the run's output directory | Contents |
| --- | --- |
| `Summary_Postnatal_CPI.txt` | One row per trio. `N_sites` counts all contributing sites. `Log10_CPI` sums their log₁₀(PI) values and `CPI` is 10 raised to that sum. The row records the four genotype counts, paternal matches and mismatches, sites without an obligatory allele, maternal incompatibilities and the selected settings. |
| `<Trio>_sites.txt` | Tab-separated site audit with genotype calls, sample-level quality checks, exclusion reasons, obligatory allele, paternal status and individual PI. |

With no eligible sites the summary records zero contributing sites and `NA` for both indices. The run log identifies the affected trio. For very large products, the logarithm can still be read when the raw CPI exceeds the floating-point range. The earlier postnatal threshold curves belong to runs made with the previous model.

The upstream worked trio provides a reproducible comparison. With all four combinations enabled and no minimum coverage, each marker panel retains 143 sites (107 HOM–HOM, 14 HOM–HET, 12 HET–HOM and 10 HET–HET).

| Marker | Expected log₁₀(CPI) | Expected CPI (rounded here) |
| --- | ---: | ---: |
| SNP | 10.2806466173021 | 19,082,998,550.23 |
| DNP | 10.8913922602561 | 77,873,960,092.42 |

These values refer to the [upstream example inputs and recorded outputs](https://github.com/lpistacchia/NEWPAT/tree/97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4/CPI_postnatal/examples). The smaller NewPat examples above have their own expected results.

## Upstream contact and citations

Upstream author: Letizia Pistacchia. The upstream project requests both citations.

- Pistacchia L et al. DNPcall: a new pipeline for accurate double nucleotide polymorphism calling. *Bioinformatics Advances*. 2025. [DOI](https://doi.org/10.1093/bioadv/vbaf209)
- D’Atanasio E et al. A new noninvasive prenatal paternity test based on double nucleotide polymorphisms abates sequencing uncertainties and improves sensitivity. *Genome Research*. 2026. [DOI](https://doi.org/10.1101/gr.281702.125)
