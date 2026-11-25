# Fetal sex determination

The R program uses three calling tables from the same maternal cell-free DNA sample. Supply autosomal DNP calls with `--autosomes`, X-chromosome DNP calls with `--X` and Y-chromosome SNP calls with `--Y`. The X and Y markers must have been validated for specificity. The program writes a summary and three site tables into a new output directory.

The summary records the result as `F`, `M` or `Undetermined`, with the three observed ratios and the thresholds applied. The author describes the classification thresholds as preliminary.

The bundled program is byte-identical to [Letizia Pistacchia's NEWPAT revision dde1a75](https://github.com/lpistacchia/NEWPAT/tree/dde1a759e4b994a42ec9c9651f896394c546b109/Fetal_sex). The upstream guide describes all parameters and their defaults. The [example inputs and expected results](../../../../tests/fixtures/fetal_sex/README.md) reproduce both published examples.
