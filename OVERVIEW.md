# NewPat at a glance

Choose the analysis from your starting files. To try NewPat with the bundled samples, open **Environment and help → Open demo**. [Guida rapida in italiano](docs/QUICKSTART_IT.md) · [English demo instructions](docs/GUI.md#try-the-shared-example)

| Starting material | Action | Result |
| --- | --- | --- |
| Aligned reads in BAM files | Run DNPcall or SNPcall with the reference FASTA and the appropriate marker panel | A count table and genotypes for each sample |
| A single-sample pileup with read names | Run SNPcall with the SNP panel | SNP counts, likelihoods and genotypes |
| SNP or DNP count tables | Run Contamination with a matching coordinate panel | Per-site estimates and a per-sample summary |
| Maternal cfDNA and alleged-father counts | Assign a prenatal pair and supply population frequencies | Fetal fraction estimates and a combined paternity index |
| Mother, alleged father and child counts | Assign a postnatal trio and supply population frequencies | Per-site and combined paternity indices |

In a new experiment, DNPcall and SNPcall can read the same BAMs using a separate panel for each marker type. Their count tables can feed Contamination or CPI in the same workflow. A caller's summary describes the sample's genotypes. To obtain a CPI, select the corresponding analysis and assign the samples in each family. [Desktop guide](docs/GUI.md)

To compare runs, save a named parameter profile and reuse it when setting up another experiment. Each experiment keeps its own input selection, progress and results. Open **Experiments and results** for the tables, or use **View in IGV** on a covered site to inspect its reads when the BAM and reference are available. [Results and run records](docs/RUNS.md)

[Installation](docs/DISTRIBUTION.md) · [Input formats and command-line examples](docs/USER_GUIDE.md) · [All guides](docs/README.md)
