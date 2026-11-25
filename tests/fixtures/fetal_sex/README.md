# Fetal sex reference cases

The six calling tables in `inputs/` and the eight expected tables in `outputs/` are exact copies of [the two upstream examples](https://github.com/lpistacchia/NEWPAT/tree/dde1a759e4b994a42ec9c9651f896394c546b109/Fetal_sex/examples). Each case uses three tables from one maternal sample. The sample name in the resulting summary comes from the autosomal input filename.

| Example | Informative autosomal sites | Informative X sites | Covered Y sites | Ratio A | Ratio B | Ratio C | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Female_fetus | 16 | 6 | 0 | 1 | 0 | 0 | F |
| Male_fetus | 16 | 4 | 10 | 0.125 | 1.5 | 12 | M |

The native regression suite compares all four output tables for each case. It also checks values at decision thresholds, disagreement among ratios, missing information, zero Y coverage and the interaction between the two fetal read filters. The examples establish reproducibility for these inputs. The upstream authors describe the classification thresholds as preliminary.
