# NewPat 0.9.99 candidate

The public download remains version 0.9.10 while this branch undergoes qualification.

## BAM pileup depth

New DNPcall and SNPcall experiments use a maximum depth of 2147483647 reads per position in each BAM. Both callers pass the equivalent `-d 0` to samtools 1.21. DNP results can change at high-coverage positions because version 0.9.10 used a default of 8000. SNPcall already used `-d 0`. Saved profiles retain explicit limits, including 8000. Imported pileups retain the depth applied at creation.

When memory and CPU allow concurrent DNP chromosome tasks at high depth, NewPat checks the indexed target coverage for each BAM. A single acquisition process handles high or unknown coverage. The run records the selected worker count and the evidence used in `work/dnp-pileup.json`. The scientific depth setting applies in either case.

## Integrated changes

The desktop uses the same calling-table input for fetal sex, parentage and contamination. Add each file once, then choose the analyses and assign the samples and tables they require. For fetal sex, select the maternal cfDNA sample and either its combined autosomal/X DNP table or its two region-specific DNP tables, together with the SNP table for Y. The maternal BAM workflow is also available. [Desktop guide](GUI.md#set-up-an-experiment)

The candidate also includes the experiment status and archive display fixes, direct installer links, and recovery of the managed Lima environment.

On macOS, if the launch command exits with code 255 and NewPat confirms the VM stopped, the experiment is recorded as interrupted. A subsequent analysis checks and starts the managed VM through the usual launcher. NewPat retains available timestamped VM lifecycle events for diagnostic export with the default execution settings. Collecting these events does not require turning on performance measurements.

The Apple Silicon candidate packages the Linux ARM64 image tested by the native scientific oracles. An owned 0.9.10 Lima guest migrates with its disk and allocation preserved. Both R and samtools run natively. The [Apple Silicon trial](MACOS_CANDIDATE_TEST.md) checks the installed upgrade, native execution and timing against the previous synthetic runs. Physical qualification, the remaining platforms and the complete NewPat rename are tracked in the [release roadmap](ROADMAP.md).
