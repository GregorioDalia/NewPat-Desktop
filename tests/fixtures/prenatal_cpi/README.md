# Prenatal CPI reference cases

The [upstream 20-marker examples](https://github.com/lpistacchia/NEWPAT/tree/c753afc4be62dfc0b81b8cb683a6e850516f5ffd/CPI_from_cffDNA/examples) provide independent reference outputs for the revised prenatal CPI model. Each marker set has maternal cfDNA and paternal counts, a marker panel, and population frequencies. The supplied results use the default fetal-read and quality thresholds and disable the experimental HOM-child option.

| Panel | CPI at median fetal support (log₁₀) | Contributing HET sites there | Matches | Mismatches |
| --- | ---: | ---: | ---: | ---: |
| DNP | 2.320 | 5 | 5 | 0 |
| SNP | −8.744 | 8 | 3 | 5 |

The native prenatal oracle compares every published summary and iteration field, the HOM table and plot generation. It also tests enabled HOM sites and coverage boundaries using separately constructed calls.
