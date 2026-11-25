# DNPcall in NewPat

DNPcall groups sequencing observations by read name to call the two adjacent bases of a double nucleotide polymorphism together. Its R implementation comes from a separate upstream project by Letizia Pistacchia and Francesco Ravasini. NewPat bundles its own adapted copy alongside the other scientific programs. [Upstream project](https://github.com/fravasini/DNPcall) · [License](LICENSE)

## Inputs and results

Select one or more BAM files, their matching reference FASTA and a five-column DNP panel (chromosome, first position, second position, REF and ALT). The engine prepares the inputs, runs samtools and passes the observations to the caller. A local example includes the reads, panel, reference and expected genotypes. [Synthetic DNP fixture](../../../tests/fixtures/dnp_engine/README.md) · [Desktop usage](../../../docs/USER_GUIDE.md#dnpcall)

Each sample produces a table with a row per locus. It contains the REF, ALT and Other read counts, genotype likelihoods (`GL0`, `GL1`, `GL2`) and the genotype call (`GT`). The combined genotype table puts the samples side by side. The count tables can feed Contamination, prenatal CPI or postnatal CPI. [Engine interface](../../../engine/README.md#dnpcall)

## Citation

Pistacchia L, Ravasini F, Bella E, D’Atanasio E, Cruciani F, Trombetta B. DNPcall: A New Pipeline for Accurate Double Nucleotide Polymorphism Calling. *Bioinformatics Advances*. 2025, vbaf209. [Original publication](https://doi.org/10.1093/bioadv/vbaf209)

Upstream contact: fravasini01@gmail.com
