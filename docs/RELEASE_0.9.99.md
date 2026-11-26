# NewPat 0.9.99 candidate

The public download remains version 0.9.10 while this branch undergoes qualification.

## BAM pileup depth

New DNPcall and SNPcall experiments use a maximum depth of 2147483647 reads per position in each BAM. Both callers pass the equivalent `-d 0` to samtools 1.21. DNP results can change at high-coverage positions because version 0.9.10 used a default of 8000. SNPcall already used `-d 0`. Saved profiles retain explicit limits, including 8000. Imported pileups retain the depth applied at creation.

When memory and CPU allow concurrent DNP chromosome tasks at high depth, NewPat checks the indexed target coverage for each BAM. A single acquisition process handles high or unknown coverage. The run records the selected worker count and the evidence used in `work/dnp-pileup.json`. The scientific depth setting applies in either case.

## Integrated changes

The candidate accepts the maternal BAM workflow for fetal sex, the combined autosomal/X DNP table with the Y SNP table, and the three-table workflow. It also includes the experiment status and archive display fixes, direct installer links, and recovery of the managed Lima environment.

The native scientific comparison runs on ARM64 and AMD64. Installer qualification, the upgrade from 0.9.10, the full NewPat rename and timing on a physical Apple Silicon Mac are tracked in the [release roadmap](ROADMAP.md).
