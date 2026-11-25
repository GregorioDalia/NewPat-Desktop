# NewPat 0.9.10

**Candidate for review.** The five available workflows include the revised prenatal and postnatal CPI models. Stable publication awaits the sixth analysis script for sex estimation and its integration and qualification. The [0.9.9 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.9) remains the stable download during review.

## Experiments and results

The Home screen loads the five newest experiment cards. The Archive displays 25 per page and searches the entire history by experiment name, ID, start date, or sample. You can combine search with status and marker filters.

Activity tracks concurrent experiments and shows their progress, output directory and stop control. You can submit another experiment while others are running or waiting. Each desktop session prepares up to two at once. The runtime admits calculations according to available CPU and memory, so several active experiments can each take longer. If another experiment arrives during a multi-step workflow, a compatible engine can share capacity at the next completed step or group of independent SNP samples. Activity shows when a job is waiting. You can cancel a waiting job or remove an interrupted experiment from activity and history while keeping its files.

Preferences can store named analysis profiles and select a default for new experiments. Sample names, input files and family roles are selected for each experiment. The results view identifies the caller as SNP or DNP and returns to the source table after closing details or IGV. The interface uses the names **Prenatal CPI** and **Postnatal CPI**.

The DNP and SNP summaries show how many loci received a genotype for each sample. Read counts and genotype calls describe the sample at those loci. The Prenatal CPI summary compares the reported log index with the two guides recorded for that analysis. Prenatal CPI can filter maternal minor-allele support by read count, percentage or both. Postnatal CPI now reports one CPI and log₁₀(CPI) per trio, with a site table documenting exclusions. Four mother–child genotype combinations and an optional minimum coverage for every trio member determine which sites contribute. Contamination shows the recorded estimate when informative sites are available. The DNP glossary explains that `NA` means the program could not determine a value.

DNPcall and SNPcall now retain reads on supported contigs whose names contain `@`. SNPcall also accepts contig names containing `|` in both BAM and imported pileup workflows. When importing a pileup, SNPcall limits read expansion to positions within the requested panel windows.

The installation includes an offline synthetic trio with example alignments, indexed reference, panels, frequencies and count tables for both marker types. Choose **Environment and help → Open demo** to review and run a prefilled DNP/SNP experiment with those three samples. Use **Save example data** to copy the dataset to a local folder, then follow its README to check the five analyses on the trio. The separate timing workload runs both callers on a single BAM with 128 loci across four contigs. [First run in Italian](QUICKSTART_IT.md)

### PDF reports for completed results

Results can be saved as a one-page summary or a detailed PDF with the available charts and supporting measurements. Choose the sample or family and the specific analysis, marker and panel. NewPat creates the report locally in Italian or English. [Export a PDF report](GUI.md#export-a-pdf-report)

## Human reference genomes

BAM experiments and IGV share a local reference catalog. Choose the FASTA used to align the BAMs, with panels in the same coordinates. Register an existing local FASTA or download UCSC hg19 or hg38 if it matches your inputs. The catalog also accepts custom references. The application verifies the downloaded archive and prepares the reference locally for offline reuse. The synthetic datasets include their own reference FASTAs. [Choosing a reference genome](GUI.md#choose-a-reference-genome)

## Desktop appearance

The Intreccio wordmark and new palette appear throughout the desktop app. Native Windows and macOS icons use a version of the mark drawn for small sizes. Home provides a single control for starting an experiment and gives more space to the experiment list. Status labels pair text and icons with color.

## DNP and SNP resource use

On Apple Silicon with the AMD64 engine, DNP block calculation automatically uses up to two R workers when the effective run allocation is at most 4 GiB. Larger allocations use the ordinary phase estimates. An explicit worker ceiling takes precedence. Serial mode keeps one worker. With one worker reading chromosomes, the pileup writes directly to the aggregate file to avoid a full temporary copy. Windows keeps its established single-BAM reader and worker sizing at the validated allocations. When memory falls below the estimated base cost of an R worker, all platforms reduce the block target to one indivisible locus group. [Comparing worker settings on Apple Silicon](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac)

On Apple Silicon with Lima and on native x86-64 Linux, the reader can now decode a regular pileup block once for several samples within the available memory. Compact panels can also use a narrower indexed chromosome scan. With performance diagnostics enabled, an interrupted run retains a small record of completed work for troubleshooting. SNP batches can group independent samples that fit the available memory and process samples of unknown cost individually. The SNP summary releases its merge data before rendering.

## Windows upgrade from 0.9.9

The complete ZIP uses English launcher names. The 0.9.9 ZIP updater expects the previous archive layout, so this transition requires a manual download. Extract the new ZIP into a fresh directory and use its installer to target the existing installation root containing `installation.json`, `data` and `runs`. Subsequent launches use `NewPat.lnk`. [Complete ZIP installation and upgrade commands](WINDOWS_INSTALLER.md#complete-zip-installation)

## Repository rename

The updater and release tools recognize both the current repository name and `GregorioDalia/NewPat-Desktop` and check the official GitHub repository ID. The project maintainer can rename the repository after distributing the transition version. [Repository migration procedure](CI_CD.md#preparing-the-github-repository-rename)
