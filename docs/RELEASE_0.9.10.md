# NewPat 0.9.10

## Experiments and results

The activity screen can track concurrent experiments. Each has its own output directory, progress and stop control. Starting another experiment shares processor time, memory and storage bandwidth. An interrupted experiment can be removed from the activity and history views while keeping its files.

Preferences can store named analysis profiles and select a default for new experiments. Sample names, input files and family roles are selected for each experiment. The results view identifies the caller as SNP or DNP and returns to the source table after closing details or IGV. The interface uses the names **Prenatal CPI** and **Postnatal CPI**.

The desktop summary now highlights recorded genotype, CPI and contamination measurements for the selected sample or family. The prenatal summary shows where the reported log index lies relative to the two plot guides recorded for that analysis. Postnatal output retains the estimates and curves produced by the current R script.

The installation includes an offline synthetic trio with example alignments, indexed reference, panels, frequencies and count tables for both marker types. Use **Environment and help → Save example data** to copy it to a local folder, then follow its README to check the five analyses on the trio. The separate timing workload runs both callers on a single BAM with 128 loci across four contigs.

## Human reference genomes

BAM experiments and IGV share a local reference catalog. Choose GRCh37 / hg19 or GRCh38 / hg38 and register the FASTA used for alignment, or explicitly download the corresponding UCSC reference. The application verifies the downloaded archive and prepares the reference locally for offline reuse. The synthetic datasets include their own reference FASTAs. [Choosing a reference genome](GUI.md#choose-a-reference-genome)

## Desktop appearance

The Intreccio wordmark and new palette appear throughout the desktop app. Native Windows and macOS icons use a version of the mark drawn for small sizes. Home provides a single control for starting an experiment and gives more space to the experiment list. Status labels pair text and icons with color.

## DNP on low-memory Apple Silicon Macs

On Apple Silicon Macs with at most 8 GiB of physical memory and a Lima VM with at most 4 GiB available, automatic DNP block calculation uses up to two R workers when both memory sizes are known. An explicit worker ceiling takes precedence. Serial mode keeps one worker. With one worker reading chromosomes, the pileup writes directly to the aggregate file to avoid a full temporary copy. Windows keeps its existing single-experiment resource policy. [Comparing worker settings on Apple Silicon](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac)

## Windows upgrade from 0.9.9

The complete ZIP uses English launcher names. The 0.9.9 ZIP updater expects the previous archive layout, so this transition requires a manual download. Extract the new ZIP into a fresh directory and use its installer to target the existing installation root containing `installation.json`, `data` and `runs`. Subsequent launches use `NewPat.lnk`. [Complete ZIP installation and upgrade commands](WINDOWS_INSTALLER.md#complete-zip-installation)

## Repository rename

The updater and release tools recognize both the current repository name and `GregorioDalia/NewPat-Desktop` and check the official GitHub repository ID. The project maintainer can rename the repository after distributing the transition version. [Repository migration procedure](CI_CD.md#preparing-the-github-repository-rename)
