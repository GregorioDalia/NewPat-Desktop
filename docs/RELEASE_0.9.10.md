# NewPat 0.9.10

## Experiments and results

Activity tracks concurrent experiments and shows their progress, output directory and stop control. You can queue several experiments. A desktop session prepares up to two at once, and calculations share the CPU and memory available on the same runtime. If another experiment arrives during a multi-step workflow, a compatible engine can share capacity at the next completed step or group of independent SNP samples. Activity shows when a job is waiting. You can cancel a waiting job or remove an interrupted experiment from activity and history while keeping its files.

Preferences can store named analysis profiles and select a default for new experiments. Sample names, input files and family roles are selected for each experiment. The results view identifies the caller as SNP or DNP and returns to the source table after closing details or IGV. The interface uses the names **Prenatal CPI** and **Postnatal CPI**.

The desktop summary now highlights recorded genotype, CPI and contamination measurements for the selected sample or family. The prenatal summary shows where the reported log index lies relative to the two plot guides recorded for that analysis. Postnatal output retains the estimates and curves produced by the current R script.

The installation includes an offline synthetic trio with example alignments, indexed reference, panels, frequencies and count tables for both marker types. Use **Environment and help → Save example data** to copy it to a local folder, then follow its README to check the five analyses on the trio. The separate timing workload runs both callers on a single BAM with 128 loci across four contigs.

## Human reference genomes

BAM experiments and IGV share a local reference catalog. Choose GRCh37 / hg19 or GRCh38 / hg38 and register the FASTA used for alignment, or explicitly download the corresponding UCSC reference. The application verifies the downloaded archive and prepares the reference locally for offline reuse. The synthetic datasets include their own reference FASTAs. [Choosing a reference genome](GUI.md#choose-a-reference-genome)

## Desktop appearance

The Intreccio wordmark and new palette appear throughout the desktop app. Native Windows and macOS icons use a version of the mark drawn for small sizes. Home provides a single control for starting an experiment and gives more space to the experiment list. Status labels pair text and icons with color.

## DNP and SNP resource use

On Apple Silicon with the AMD64 engine, DNP block calculation automatically uses up to two R workers when the effective run allocation is at most 4 GiB. Larger allocations use the ordinary phase estimates. An explicit worker ceiling takes precedence. Serial mode keeps one worker. With one worker reading chromosomes, the pileup writes directly to the aggregate file to avoid a full temporary copy. Windows keeps its established single-BAM reader and worker sizing at the validated allocations. When memory falls below the estimated base cost of an R worker, all platforms reduce the block target to one indivisible locus group. [Comparing worker settings on Apple Silicon](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac)

On Apple Silicon with Lima and on native x86-64 Linux, the reader can now decode a regular pileup block once for several samples within the available memory. Compact panels can also use a narrower indexed chromosome scan. With performance diagnostics enabled, an interrupted run retains a small record of completed work for troubleshooting. SNP batches can group independent samples that fit the available memory and process samples of unknown cost individually. The SNP summary releases its merge data before rendering.

## Windows upgrade from 0.9.9

The complete ZIP uses English launcher names. The 0.9.9 ZIP updater expects the previous archive layout, so this transition requires a manual download. Extract the new ZIP into a fresh directory and use its installer to target the existing installation root containing `installation.json`, `data` and `runs`. Subsequent launches use `NewPat.lnk`. [Complete ZIP installation and upgrade commands](WINDOWS_INSTALLER.md#complete-zip-installation)

## Repository rename

The updater and release tools recognize both the current repository name and `GregorioDalia/NewPat-Desktop` and check the official GitHub repository ID. The project maintainer can rename the repository after distributing the transition version. [Repository migration procedure](CI_CD.md#preparing-the-github-repository-rename)
