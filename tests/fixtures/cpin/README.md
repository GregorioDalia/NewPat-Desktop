# Analytical postnatal CPI fixture

Nine synthetic loci exercise postnatal SNP and DNP analysis with identical counts.
They are designed independently of the implementation; no human data are included.
Population REF/ALT frequencies are 0.6/0.4. The mother is homozygous REF except at the uncallable sixth and heterozygous ninth loci.

| Locus | Expected outcome with defaults |
|---|---|
| 1 | Heterozygous child, heterozygous father: PI = 0.5 / 0.4 = 1.25 |
| 2 | Homozygous REF child and father: PI = 1 / 0.6 |
| 3 | Heterozygous child, REF father: mismatch PI = epsilon / 0.4 |
| 4 | Mother/child incompatible homozygotes |
| 5 | Maternal Other/total = 11/100 exceeds 0.1 |
| 6 | Zero maternal coverage; missing total is legitimate and becomes zero in memory |
| 7 | Heterozygous child with two total reads, homozygous REF father: PI = epsilon / 0.4; retained with default coverage |
| 8 | Father REF ratio 0.7 is unassigned |
| 9 | Heterozygous mother and child: no obligatory allele, PI = 1 / (0.6 + 0.4) = 1 |

With all four mother/child genotype combinations enabled, five loci contribute
to one CPI per trio, given by `1.25 × (1 / 0.6) × (epsilon / 0.4)² × 1`.
There are two matches, two mismatches and one site without an obligatory
paternal allele. The default epsilon is 0.001 for SNPs and 0.0000892303778101497
for DNPs. The optional panel restricts the inputs to loci 1–3.
