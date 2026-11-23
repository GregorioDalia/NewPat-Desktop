# SNPcall 2.0

NewPat uses the SNPcall 2.0 model to calculate per-sample allele counts, genotype likelihoods and genotypes. The application includes its R dependencies, input validation, bounded scheduling and plot helpers. The original work and GPL license belong to the upstream project. [Upstream implementation](https://github.com/lpistacchia/NEWPAT/tree/ce59f4beeeec710b1b42d425cb87d7aad729f71d/SNPcall) · [Frozen reference](../../../../tests/reference_r/2.0/SNPcall.R) · [License](../LICENSE)

## Run the bundled example

From the root of this repository, use the configured NewPat CLI and the included [panel](examples/SNPlist.txt) and [pileup](examples/pileup.txt).

```sh
newpat snp-call --pileup scientific/vendor/NEWPAT/SNPcall/examples/pileup.txt --panel scientific/vendor/NEWPAT/SNPcall/examples/SNPlist.txt
```

A new run contains the generated results. For your own BAM, select BAM, FASTA and panel in NewPat or use the CLI's `snp-call --bam` mode. For multiple samples use `workflow snp-batch`. The engine prepares three-base windows and a QNAME pileup with samtools. By default, SNP acquisition uses `-d 0` (unlimited depth). The R adapter receives one prepared sample. [User guide](../../../../docs/USER_GUIDE.md) · [Scientific implementation](../../../README.md)

## Inputs and results

A tab-separated panel uses `chr,pos,ref,alt`, or `pos,ref,alt` with coordinates such as `chr1:1770788`. Positions range from 2 to 2147483646, inclusive. REF and ALT are distinct single A/C/G/T bases, normalized to uppercase in a working copy. The pileup includes reference, bases, Phred qualities and QNAME in columns 3, 5, 6 and 7. The caller associates three-base observations with their SNP, then groups by SNP and read name. Overlapping windows can use the same observation. The reference resolves the `.` and `,` pileup symbols. An indel anywhere in a retained window can exclude the read.

| Columns in `output/SNPcall_output.txt` | Meaning |
| --- | --- |
| `chr`, `pos`, `REF`, `ALT` | Panel coordinate and alleles. |
| `N_REF`, `N_ALT`, `N_Other`, `total_count` | Retained read counts, including Other in the total. |
| `ratio` | REF fraction among REF and ALT observations. |
| `GL0`, `GL1`, `GL2` | Natural-log likelihoods of genotypes 0/0, 0/1 and 1/1 using central-base qualities. |
| `GT` | Maximum-likelihood call. Missing when there are no informative observations or the Other fraction reaches the configured threshold (default 0.1). |
| `reads_discarded_for_indels`, `ratio_reads_discarded_for_indels` | Central-base indel count and fraction before filtering. Reads excluded for flanking indels can differ. |
| `combined_bases`, `combined_counts` | Matching hyphen-separated observed bases and counts. |

The run also contains genotype and read-count plots and summary tables. Multi-sample workflows add merged genotypes and shared coverage. R start/end RSS, phase duration, whole-container peak and complete elapsed time measure different quantities.

## Upstream contact and citation

Upstream author: Letizia Pistacchia.

Pistacchia L, Ravasini F, Bella E, D’Atanasio E, Cruciani F, Trombetta B. DNPcall: a new pipeline for accurate double nucleotide polymorphism calling. *Bioinformatics Advances*. 2025;5(1):vbaf209. [DOI](https://doi.org/10.1093/bioadv/vbaf209)
