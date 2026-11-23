# Postnatal CPI

NewPat calculates the postnatal Combined Paternity Index (CPI) from mother, putative-father and child count tables and population frequencies. SNP and DNP are analyzed separately. NewPat supplies the R runtime, validates the role mapping and reuses samples shared across trios. [Upstream module and examples](https://github.com/lpistacchia/NEWPAT/tree/9c2a8be60afcb944153710da6a61cd0559e2b4cf/CPI_postnatal) · [License](../LICENSE)

## Run the local examples

The NewPat checkout includes two [synthetic family fixtures and their expected results](../../../../tests/fixtures/cpin/README.md). From the repository root, run either command with a configured NewPat CLI.

```sh
newpat cpin --input-dir tests/fixtures/cpin/DNP --trios M1:F1:C1 --popfreq tests/fixtures/cpin/DNP/population.txt --panel tests/fixtures/cpin/DNP/markers.tsv
newpat cpin --input-dir tests/fixtures/cpin/SNP --trios M1:F1:C1 --popfreq tests/fixtures/cpin/SNP/population.txt --panel tests/fixtures/cpin/SNP/markers.tsv
```

With the CLI's default prefixes, `M1:F1:C1` selects `MotherM1.txt`, `FatherF1.txt` and `ChildC1.txt`, in that order. Use `--mother-prefix`, `--father-prefix` and `--child-prefix` for other naming schemes. Supply comma-separated trios for a batch. Each trio requires three distinct physical files. The engine rejects duplicate trios and ambiguous filenames. The optional panel contains coordinates and REF/ALT alleles. Omitting it allows all otherwise eligible loci with population frequencies. [User guide](../../../../docs/USER_GUIDE.md) · [Engine contract](../../../../engine/README.md#postnatal-cpi)

## Model and settings

Both selections require a homozygous mother. `other_allele` selects compatible heterozygous children. `all` also includes compatible homozygous children. The default `both` reports each selection separately. Mother and child with opposite homozygous genotypes are excluded. Paternal mismatches remain eligible and use the marker-specific error constant.

A called heterozygous child must meet the configured initial minimum support for **each** allele, a homozygous child for its called allele. The curve then increases the support required for the obligate paternal allele. At each site the PI is the paternal transmission probability divided by the population frequency of that allele, using the mismatch constant for incompatible paternal genotypes. The combined log₁₀ index is the sum of site-level log₁₀ values. A selection with no eligible sites returns `NA`.

Inspect settings with `newpat settings cpin`. Place e.g. `--set cpin.min_child_reads=5` before the subcommand to override a setting. Effective parameters and invariant model constants are recorded for each run.

| Setting | Default | Interpretation |
| --- | ---: | --- |
| `other_fraction_max` | 0.1 | Highest Other-read fraction retained by this downstream module, inclusive. |
| `homozygous_ref_min` | 0.9 | Minimum REF fraction for a REF homozygote. |
| `homozygous_alt_max` | 0.1 | Maximum REF fraction for an ALT homozygote. |
| `heterozygous_min`, `heterozygous_max` | 0.4, 0.6 | Inclusive REF-fraction bounds for a heterozygote. |
| `err_const_snp`, `err_const_dnp` | 0.001, 0.0000892303778101497 | Paternal mismatch constants by marker type. |
| `min_child_reads` | 2 | Initial minimum support for each called allele in the child. |
| `site_selection` | `both` | Produce both `heterozygous_child_sites` and `all_compatible_sites`. |
| `log_cpi_lower`, `log_cpi_upper` | −4, 4 | Plot guides. They affect display only. |

## Results

| Output within the run's output directory | Contents |
| --- | --- |
| `Summary_Postnatal_CPI.txt` | One summary row per trio and selection, with counts, matches/mismatches, CPI, log₁₀(CPI) and settings. `Log10_CPI` remains available if exponentiating exceeds floating-point range. |
| `sites/<Trio>_sites.tsv` | Site records, including exclusions and their `Status`. |
| `curves/<Trio>_<Analysis>_curve.tsv` | Exact constant intervals of minimum read thresholds. Each interval includes both `Min_child_reads` and `Through_min_child_reads`. |
| `plots/` and `All_CPIplots.pdf` | Individual trio/selection plots and aggregate PDF. |

## Upstream contact and citations

Upstream author: Letizia Pistacchia. The upstream project requests both citations.

- Pistacchia L et al. DNPcall: a new pipeline for accurate double nucleotide polymorphism calling. *Bioinformatics Advances*. 2025. [DOI](https://doi.org/10.1093/bioadv/vbaf209)
- D’Atanasio E et al. A new noninvasive prenatal paternity test based on double nucleotide polymorphisms abates sequencing uncertainties and improves sensitivity. *Genome Research*. 2026. [DOI](https://doi.org/10.1101/gr.281702.125)
