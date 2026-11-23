# Input and output validation

The desktop client, terminal menu and CLI use the same Python validation library. The engine repeats the relevant checks against the files visible in the container before invoking R. These checks establish that the files can be interpreted by the requested analysis. The analyst selects the appropriate genome assembly, samples, biological roles and population frequencies.

## Original files and working copies

The engine mounts original inputs read-only. Any normalization happens in the run or step's `work` directory and retains the link to the source. For example, an SNP allele supplied as `g` is written as `G`. Invalid alleles and duplicate loci produce errors. The engine preserves the reported counts and frequencies.

## File requirements

Tables must use the documented delimiters and column layout. Text files use UTF-8. Required headers must be present and column names must be nonempty and unique. Each row must have the declared number of columns. CLI numeric parameters use a decimal point. CPI frequency files also accept a decimal comma as specified by the R input format. [User guide](USER_GUIDE.md)

| Input | Checks |
| --- | --- |
| DNPcall panel | Five columns, adjacent positions with the first at least 2 (the preceding base is needed), unique loci and two-base A/C/G/T alleles. The working copy uses uppercase. |
| SNPcall panel | `chr,pos,ref,alt` or `pos,ref,alt` with `pos=chr:position`. Unique coordinates, position 2 through 2147483646 inclusive, chromosome without spaces or colon, and distinct single-base A/C/G/T alleles. The working copy has four columns and uppercase alleles. |
| SNPcall pileup | At least seven samtools fields including chromosome, positive position, reference, nonnegative depth, bases, qualities and QNAME. The validator checks each nonempty row and rejects an empty imported pileup. |
| Contamination count tables | Required fields, positive ordered coordinates, unique loci, and finite nonnegative integer `N_REF`, `N_ALT` and `N_Other`. |
| prenatal/postnatal CPI count tables | Count requirements plus one-base REF/ALT for SNP or two-base alleles for DNP. `total_count` must be a nonnegative integer or a supported missing value at an uncovered site. |
| prenatal/postnatal CPI frequencies | Marker type compatible with the count tables, unique loci, at least one data row, and finite `Ref_f.pop` and `Alt_f.pop` in (0, 1]. |

The engine checks BAM, FASTA and required indices for existence and readability. Before pileup, each BAM dictionary must contain every target contig with the same length as in the FASTA index. DNPcall with multiple BAMs also requires identical complete ordered dictionaries, whether or not the BAMs have indices. A compatible target with no reads is retained at zero coverage. A missing target or discordant length is an input error. Imported pileup validation checks structure across the file. It cannot reconstruct acquisition settings or validate the full encoded base grammar. Header-only count tables can represent a case with no sites. Empty panels and frequency tables are rejected.

Prenatal and postnatal CPI distinguish physical files, including aliases and hard links. Plans use explicit sample IDs. Standalone family IDs are local to each role. A postnatal CPI selection such as `A:A:A` therefore requires three distinct files.

Contamination computes the REF fraction from `N_REF` and `N_ALT`. A supplied numeric `ratio_REF_ALT` must be finite and within [0, 1]. A discrepancy from the count-derived value generates a warning. Sites with neither REF nor ALT reads are excluded. Prenatal and postnatal CPI require positive frequencies and a `total_count` equal to `N_REF + N_ALT + N_Other`. They accept an `NA` total at a locus where all counts are zero. For Contamination a discordant total produces a warning. A REF/ALT population-frequency sum different from one also generates a warning.

`work/input-validation.json` records warnings, normalizations and checksums of the original and normalized panels. In a plan, each step owns its `work` directory. Warnings also appear in the log. Errors identify the file and, where possible, the row or column. After correcting an input, start a new run so the failed run remains available.

## Output checks and numerical quality

Standalone analyses and plans verify expected files, schemas, sample correspondence and applicable scientific settings before reporting success. Distinguish expected missing values from numerical problems.

| Condition | Handling |
| --- | --- |
| An estimate is `NA` with no informative sites, or standard deviation is `NA` with one site | Expected in these cases. |
| Unexpected missing estimate | `output.missing_estimate` warning. |
| Nonfinite estimates, including with zero sites | `output.nonfinite` warning. |
| Blank or nonnumeric text in a required numeric field | Output validation error. |
| SNP log likelihoods | Phred zero can yield `-Inf` from `log(0)`. `NaN` and `+Inf` are rejected in GL columns. |

SNPcall retains textual contig identifiers, so `01` and `1` identify distinct contigs. Counts and coordinates must match the panel. Valid genotype values are `0/0`, `0/1`, `1/1` or `NA`. The DNP genotype summary must agree with the individual tables on samples, loci, alleles and calls. Quality warnings preserve the original values from R. A Contamination estimate does not trigger an extra CPI filter.

Each module must write `output/scientific-settings.json` with the requested values and distributed registry. Missing/extra parameters, type errors or mismatches prevent successful completion. Prenatal and postnatal CPI summaries are also checked for marker type, minimum reads and error constant. Standalone analyses write `work/scientific-validation.json`. Plan steps record `artifacts.quality_warnings` in `workflow-state.json`.

[Scientific catalog](SCIENTIFIC_CATALOG.md) · [Runs and results](RUNS.md) · [Domain validation worksheet](VALIDATION.md)
