# Scientific programs and reference models

NewPat packages five R programs from [DNPcall](https://github.com/fravasini/DNPcall) and [NEWPAT](https://github.com/lpistacchia/NEWPAT). The image includes R, samtools, their dependencies and the `nipat_scientific` preparation library. Before execution the engine checks all five operational scripts against [SHA256SUMS](SHA256SUMS). Analyses use the copies inside the verified image. The host client owns file selection and run records.

| Workflow | Bundled source |
| --- | --- |
| DNPcall | [DNPcall.R](vendor/DNPcall/DNPcall.R) |
| SNPcall | [SNPcall.R](vendor/NEWPAT/SNPcall/SNPcall.R) |
| Contamination | [detect_contamination.R](vendor/NEWPAT/contamination/detect_contamination.R) |
| Prenatal CPI | [cfDNA_CPI_estimator.R](vendor/NEWPAT/CPI_from_cffDNA/cfDNA_CPI_estimator.R) |
| Postnatal CPI | [Postnatal_CPI.R](vendor/NEWPAT/CPI_postnatal/Postnatal_CPI.R) |

<a id="provenienza-e-identità"></a>

## Regression references

| Analysis | Reference used to check a build |
| --- | --- |
| DNPcall | NIPAT 0.8.5 commit `eafadf7002a9c7d7c1b9af9ccafc47d698a059e5`, frozen in `tests/reference_r/0.8.5`. |
| SNPcall | [Upstream SNPcall 2.0](https://github.com/lpistacchia/NEWPAT/tree/ce59f4beeeec710b1b42d425cb87d7aad729f71d/SNPcall), Git blob `7a2e01e94c9e278af52aa861646fec3b16df8b1c`. Local reference `tests/reference_r/2.0/SNPcall.R` has SHA-256 `855a96c897d1bcb8ce30b725baecfa739d01be323252da07554a63aa66965da4`. |
| Contamination, prenatal and postnatal CPI | [Upstream NEWPAT sources](https://github.com/lpistacchia/NEWPAT/tree/9c2a8be60afcb944153710da6a61cd0559e2b4cf), frozen in `tests/reference_r/NEWPAT_20261113`, plus independent analytical expectations. |

The [R package manifest](../docker/scientific-runtime/r-packages.tsv) pins dependencies for image construction. Each run records verified engine hashes separately from the client identity.

## DNPcall

Each panel row defines a chromosome, two adjacent positions and two-base REF/ALT alleles. The engine prepares a normalized panel, an ordered BAM list and read-only input mounts. Numbered aliases map to original files in the run metadata. R executes from the run root with `--out=output`. Summaries retain a data frame for a single genotype column. The UpSet plot requires at least two samples and is omitted in a single-sample run.

Acquisition reads the phase budget from `work/dnp-acquisition-budget.json`. With indexed BAMs, compatible sequence dictionaries and an unambiguous set of target chromosomes, each task runs one `samtools mpileup -r` over a complete chromosome with the original BAM list, BED selection and scientific settings. The helper concatenates pieces in BAM `@SQ` order. Only after completion does R index and process the pileup. A chromosome index selects the chromosome. The BED filters positions during scanning. Sparse targets on whole-genome BAMs can therefore require more reads than multi-region `view -M -L` selection.

A supported single- or multi-BAM workload can run up to five independent chromosome acquisitions when CPU, estimated memory and target count allow. Serial mode runs one compute process at a time. For an input that cannot be partitioned by chromosome, the helper stages indexed inputs to disk one at a time and passes them in original order along with unindexed inputs to one mpileup. A corrupt supplied index is an error. `work/dnp-pileup.json` records strategy, budget, tasks, observed concurrency and outcomes.

Large intermediates use the runtime's Linux scratch storage. The client manages run-volume cleanup. Successful completion removes the temporary BED and pileup and validates output tables. Block reads group byte-contiguous requested rows, preserving order, repeats and gaps. The global pileup index and column types apply across all blocks. The planner selects its byte target from the run budget and estimated work. Indivisible locus groups stay intact. Samples and blocks share one worker pool. Process RSS and whole-container peak memory are separate measures. [Performance diagnostics](../docs/PERFORMANCE.md)

## SNPcall

SNPcall 2.0 takes a panel and a pileup with reference, quality and QNAME fields. In BAM mode the engine creates three-base BED windows and calls samtools before R. For a compatible indexed BAM, concurrent tasks cover disjoint chromosomes and reassemble the pileup in header order. A failed partition or a pool that exceeds its memory allowance triggers a fresh sequential scan. A failed sequential scan stops execution. The default `-d 0` removes the depth cap. A four-column panel uses `chr,pos,ref,alt`. A three-column panel with `pos=chr:position` is normalized to the same format. Both accept positions from 2 through 2147483646 inclusive.

`output/SNPcall_output.txt` contains 17 columns covering coordinates and alleles, REF/ALT/Other counts, total, REF fraction, `GL0`/`GL1`/`GL2`, `GT`, indel statistics and observed bases with counts. GL values are natural log likelihoods using central-base Phred scores for REF/ALT observations. The default Other fraction threshold of 0.1 makes `GT` missing at or above the threshold. Central indels are counted before filtering. A flanking indel can also exclude a read. The ratio is `N_REF / (N_REF + N_ALT)`.

Each three-base window belongs to its own SNP before QNAME grouping. Positions shared by adjacent windows contribute to both. The scheduler retains complete SNP/QNAME groups and restores order before calculation. Tokenization has a compatibility path. Common aggregations and likelihood-group indices avoid redundant passes. Panel reading uses one thread.

Outputs include genotype and REF/ALT/Other plots, genotype tables and summaries with explicit missing values. Multiple samples also yield shared-coverage results. R phase duration and initial/final process memory are distinct from complete elapsed time and peak container memory.

## Contamination

This module accepts SNP coordinates (`chr,pos`) or DNP coordinates (`chr,pos1,pos2`) and a compatible panel. The Other filter uses `Other/(REF+ALT+Other)`. Per-site contamination is `unexpected/(REF+ALT)`. Genotype thresholds, the Other filter and zero inclusion are configurable. The summary reports `informative_sites`, arithmetic mean and standard deviation. With no informative sites the count is zero and estimates are `NA`.

## Prenatal CPI

Inputs are explicit maternal cfDNA–father pairs, compatible SNP/DNP population frequencies and optional panels. Shared samples are read once. The module computes curves over exact intervals. The default minimum fetal read count is 2 and the error constant depends on marker type. Missing ancillary metadata does not exclude sites with valid scientific fields. Outputs include fetal fraction, log CPI, curve data and paginated PDFs.

## Postnatal CPI

Postnatal CPI takes mother–father–child trios and SNP/DNP frequencies. Both `other_allele` and `all` require a homozygous mother. The setting `both` runs the two selections. Initial support is checked for each called allele in the child. The subsequent curve increases the support requirement for the obligate paternal allele. The upstream PI model uses configurable error constants. The module exports summaries, sites with exclusion reasons, curves and PDFs. It caches shared samples, schedules independent trios within the common budget and computes threshold intervals without rescanning every integer through maximum depth.

## Configuration and verification

`newpat settings` lists parameter defaults, limits and model constants. `--scientific-config PATH` and `--set module.parameter=value` apply validated overrides. Each step records effective settings and code references. A missing estimate (`NA`) remains distinct from zero.

`scripts/verify_engine_package.py` exercises the installed image on synthetic inputs. Fixture descriptions include inputs, expectations and limitations for [DNPcall](../tests/fixtures/dnp_engine/README.md), [SNPcall](../tests/fixtures/snp_engine/README.md), [Contamination](../tests/fixtures/contamination/README.md), [CPI](../tests/fixtures/cpi/README.md), [CPI error constants](../tests/fixtures/cpi_engine/README.md), [postnatal CPI](../tests/fixtures/cpin/README.md) and [independent model checks](../tests/fixtures/five_modules/README.md).

`scripts/verify_r_equivalence.py` compares the two callers with their frozen references in the same runtime. `scripts/verify_five_modules.py` checks CPI, postnatal CPI and Contamination against upstream and analytical expectations for both marker types. The checks include unrounded values, tables and plots. Changes to a scientific script require review of its provenance, manifest and relevant regressions. Package identity, fixture equivalence and expert assessment on independent data address separate questions.

Upstream READMEs under `vendor/` describe their respective projects and may refer to resources shipped only upstream. Consult the [NewPat user guide](../docs/USER_GUIDE.md) for installation and file locations. [Third-party notices and licenses](../THIRD_PARTY_NOTICES.md)
