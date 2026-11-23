# NewPat at a glance

Start with the files you have and the result you need.

| Starting material | Action | Result |
| --- | --- | --- |
| Aligned reads in BAM files | Run DNPcall or SNPcall with the reference FASTA and the appropriate marker panel | A count table and genotypes for each sample |
| A single-sample pileup with read names | Run SNPcall with the SNP panel | SNP counts, likelihoods and genotypes |
| SNP or DNP count tables | Run Contamination with a matching coordinate panel | Per-site estimates and a per-sample summary |
| Maternal cfDNA and alleged-father counts | Assign a prenatal pair and supply population frequencies | Fetal fraction estimates and a combined paternity index |
| Mother, alleged father and child counts | Assign a postnatal trio and supply population frequencies | Per-site and combined paternity indices |

In the desktop window, choose **New experiment**, add the samples and reference files, review the analysis settings and validate the configuration. You can connect the calling and downstream analyses in one workflow. For results, open **Experiments and results** or read `run-report.html` in the run folder. The integrated IGV viewer opens local alignments at a selected locus.

[Installation](docs/DISTRIBUTION.md) · [Desktop guide](docs/GUI.md) · [Input formats and command-line examples](docs/USER_GUIDE.md) · [Reading results](docs/RUNS.md)
