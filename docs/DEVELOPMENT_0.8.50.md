# Developer guide to the five scientific modules

NewPat integrates DNPcall, SNPcall 2.0, Contamination, prenatal CPI and postnatal CPIN. The client checks that the installed scientific engine provides the module interfaces and parameter registry needed by a request.

## Callers, inputs and family roles

| Source | Available downstream analyses |
| --- | --- |
| BAM → DNPcall | Contamination, prenatal CPI and postnatal CPIN |
| BAM or imported pileup → SNPcall | Contamination, prenatal CPI and postnatal CPIN |
| Imported DNP or SNP count tables | Contamination, prenatal CPI and postnatal CPIN |

`workflow analyze` supports both callers in one plan and independent selections of downstream analyses per branch. Each caller computes a sample's counts once. Downstream consumers reuse the appropriate table and marker type. Prenatal CPI takes a maternal cfDNA sample and father. Postnatal CPIN takes mother, father and child. Distinct samples are required within a pair or trio. A father may appear in multiple families. The plan uses explicit IDs for maternal cfDNA and maternal genomic DNA when these are separate specimens.

## Scientific settings

Python and R read the definitions in `src/nipat_scientific/settings_data.json`. Configurable values include pileup quality and depth thresholds, BAQ, mapping-quality adjustment, overlapping reads, anomalous pairs and excluded flags. Caller genotype thresholds, Contamination filters and zero handling, CPI and CPIN genotype filters, marker-specific error constants, minimum fetal or child read counts, CPIN site selection and CPI plot guides also come from the registry. Users choose panels, frequencies, samples and families per request. Worker limits and DNP block targets control execution. The registry documents model invariants such as ploidy, Phred encoding, PI equations and column interpretation separately.

```powershell
python -m nipat settings
python -m nipat settings cpin
python -m nipat settings --export .\scientific-settings.json
python -m nipat parameters cpin
```

A partial JSON file may contain only the overrides required for a particular run.

```json
{
  "snp-call": {"min_base_quality": 20},
  "contamination": {"include_zero": false},
  "cpi": {"min_fetal_reads": 3},
  "cpin": {"min_child_reads": 3, "site_selection": "both"}
}
```

```powershell
python -m nipat --scientific-config .\scientific-settings.json --set cpin.min_child_reads=4 settings cpin
```

Global options precede the subcommand. `--set` takes precedence over the file. Unknown keys, invalid types, nonfinite values and overlapping genotype thresholds fail validation. The guided menu can save defaults explicitly. Direct commands use supplied arguments and distributed defaults. Each step writes `work/effective-scientific-settings.json`. Run records link values to inputs and sample associations. An imported pileup already reflects its upstream acquisition settings.

## Models and execution

The [scientific source reference](../scientific/README.md) identifies the immutable regression target for each module. Contamination filters on `Other/(REF+ALT+Other)` and computes per-site contamination as `unexpected/(REF+ALT)`. Its default includes zeros. The summary reports `informative_sites`, the arithmetic mean and sample standard deviation.

Prenatal CPI selects the SNP or DNP model, with marker-specific error constants and a configurable minimum fetal read count. It reuses shared samples, supports multiple panels and computes curves over exact threshold intervals. A missing ancillary metadata value does not discard a site with complete scientific fields.

CPIN supports `other_allele`, `all` and `both`. Site details record exclusion reasons. Curves retain exact support intervals, and the script exports summaries and PDFs. Shared inputs are cached. Independent trios may run concurrently. One budget bounds compute workers across a plan, including independent SNP calls in mixed plans. Nested pools remain serial.

<a id="verifica-prima-di-una-distribuzione"></a>

## Qualification

Tests compare the R scripts with their frozen references and independent analytical expectations. The image-level verification includes two-, three- and five-element batches in serial, automatic and two-worker modes. Run the qualification from a checkout.

```bash
python -m unittest discover -s tests
python -m unittest discover -s .github/scripts
python scripts/verify_five_modules.py --output build/qualification --full
python scripts/verify_five_modules.py --image IMAGE_ID --output build/qualification-image --full
```

Local R or client tests exercise different layers from the distributed image, platform installers and desktop acceptance. Record the package, platform and evidence actually tested. The [validation worksheet](VALIDAZIONE.md) covers independent domain evaluation.

## Different analyses on the two branches

`--analyses` applies a shared selection. `--dnp-analyses` and `--snp-analyses` override the corresponding branches. An empty selection runs the caller without a downstream analysis. This example runs prenatal CPI on DNP counts and Contamination on SNP counts.

```powershell
python -m nipat workflow analyze --caller both `
  --sample Plasma .\plasma.bam --sample Father .\father.bam `
  --reference .\genome.fa --dnp-panel .\dnp.tsv --snp-panel .\snp.tsv `
  --dnp-analyses cpi --snp-analyses contamination `
  --pair Family1 Plasma Father --dnp-popfreq .\dnp-frequencies.tsv
```

Contamination uses the caller panel unless given a dedicated panel. Only the DNP branch needs population frequencies here. For existing tables use `--caller tables` with repeated `--dnp-table ID PATH` or `--snp-table ID PATH`. For a prepared SNP pileup use `--caller snp --pileup ID PATH --snp-panel PATH`. No FASTA is needed for this mode. References in `--pair` and `--trio` identify the declared samples.
