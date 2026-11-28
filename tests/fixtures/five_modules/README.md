# Independent downstream fixtures

Both marker types encode the same counts, with SNP `chr,pos,A,C` or DNP
`chr,pos1,pos2,AA,CC`. They are count tables, not real patient data or BAM files.
The corresponding population tables use independent, explicitly assigned
frequencies; no expected answer is derived by running the candidate.

## Contamination

Four loci have `(REF,ALT,Other)` counts `(95,5,11)`, `(100,0,0)`, `(80,20,0)`,
`(0,0,5)`. The first is retained by the Other/total filter (`11/111 <= .1`).
The first two are homozygous under the configured ratio rules. Consequently:

- Include zeros: 2 informative sites, mean `.025`, SD `sqrt(.00125)`.
- Exclude zeros: 1 informative site, mean `.05`, SD `NA`.

The denominator includes Other reads. Dividing by REF + ALT alone would
exclude the first locus and change the expected mean.

## Prenatal CPI

Maternal minor-allele counts are 2, 3, 4 and 1 out of 100; paternal genotypes
and ALT frequencies give PI contributions 5, 2, 2 and 5. With minimum support
2, CPI at thresholds 2,3,4 is therefore 20,4,2; the median fetal fraction is
6%. With minimum 1, the CPI at threshold 1 is 100 and the fraction is 5%. Minimum
5 gives no informative sites. A separate no-sites pair tests explicit NA.
With only a 2.5% filter, the 3- and 4-read sites survive and the curve starts
at threshold 1. Setting minimum reads to 2 and percentage to 3 retains the
same sites and starts the curve at threshold 2.
The metadata variant adds an unused all-NA column to population frequencies:
this must not discard scientifically usable sites.
The mismatch variant replaces the father at maternal support 3 with a REF
homozygote: that site's PI becomes `epsilon/.25`, yielding curve products
`40*epsilon,8*epsilon,2`. This separately verifies SNP/DNP mismatch constants.

## Postnatal CPI

Five of the nine loci contribute to the single trio result at default settings.

| Position | Per-site contribution |
| --- | --- |
| 100 | Heterozygous paternal transmission, PI = 0.5/0.4 |
| 200 | Paternal mismatch, PI = ε/0.4 |
| 300 | Compatible homozygous child, PI = 1/0.6 |
| 500 | Heterozygous mother and child, PI = 1/(0.6 + 0.4) = 1 |
| 600 | Paternal mismatch, PI = ε/0.4 |

The remaining loci have opposite mother/child homozygotes, no coverage, excessive Other reads or an unassigned paternal genotype. The product of the five contributions defines the expected scalar. ε is 0.001 for SNP and 0.0000892303778101497 for DNP. The summary must count two matches, two mismatches and one site with no obligatory allele.

With minimum coverage 10, site 600 drops out. Minimum coverage 101 excludes all nine loci and gives NA. Disabling the hom–het combination retains sites 300 and 500.

The optional full qualification copies these explicit fixtures to distinct
sample identities to test 2,3,5 trios, prenatal pairs or contamination samples. Copies are only
a process/identity stress fixture; they do not represent biological replication.

Run:

```sh
python scripts/verify_five_modules.py --full --output build/qualification
# CI: use the installed R/Python payload, with its hashes checked first.
python scripts/verify_five_modules.py --image "$NEWPAT_RUNTIME_IMAGE" --full --output build/qualification-image
```

The reference comparisons use scientific tables. Plot bytes are excluded from numerical comparisons. DNP/SNP calling, native installers, and the
combined workflow executor have separate mandatory checks.
