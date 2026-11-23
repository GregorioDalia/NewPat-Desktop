# Desktop guide

Use NewPat to set up an experiment, follow its progress, read results and inspect alignments. Choose the British or Italian flag in the top bar to switch between English and Italian. NewPat remembers this choice when you reopen the application. The labels below use English.

## Set up an experiment

1. Choose **New experiment** and give the experiment a name. Select the starting material (BAM files, SNP pileups or existing count tables). For BAM inputs, supply the reference FASTA, the marker panel for each caller and a sample ID for each file.
2. Select the analyses. Contamination, prenatal CPI and postnatal CPI can each use a caller's count tables. For parentage analyses, identify each sample's role in its pair or trio and select population frequencies for the marker type.
3. Review the scientific parameters, sample list, execution settings and destination. Select **Record performance diagnostics** if you need timing and resource measurements. Choose **Start experiment** once. NewPat checks the configuration and runtime and starts the analysis when the checks pass. If a check fails, use the displayed message to correct the problem before trying again.
4. Open **Activity** to see the current phase, the sample when available, and the elapsed time. Recent activity lists changes as they happen. Expand **Technical log** for detailed messages. The DNA animation shows activity while the engine prepares. When a phase has measurable progress, the percentage refers to that phase. Stopping an analysis can take time while its processes exit.

**New experiment** starts with the defaults in Preferences. **Run again** opens a fresh draft with an existing run's input files and settings. Review those paths before starting it. See the [input and command reference](USER_GUIDE.md) for panel formats and sample roles.

You can submit another experiment while one is running. Each has its own progress, stop control and output directory. A desktop session prepares up to two experiments at once. Others appear as **Queued** and can be cancelled from **Activity**. When inputs are ready, NewPat starts the calculation once both CPU and memory are available. An experiment can also wait specifically for those resources.

Desktop sessions of the same user share capacity on the same runtime. Experiments submitted together can start side by side. If a running experiment already uses the full budget, a compatible engine can share it when the current analysis step or group of SNP samples finishes. A single long step can therefore delay the next experiment. Each calculation keeps its current workers until they finish. With unknown capacity, one experiment calculates at a time with a single worker. Concurrent experiments share storage bandwidth, and CLI runs and other applications can affect elapsed time.

Under **Parameters → Experiment resources**, you can set CPU, memory and worker limits for a run and save them in a profile. Finished and interrupted jobs move to **Finished this session**. **Remove from list** clears the card and its archive listing while preserving the files.

In the **Parameters** step, save a named profile to reuse your scientific settings and execution limits. Select and apply a profile to change those values on the current draft. Sample files, reference, panels and family roles belong to the experiment. You can replace or remove a saved profile and choose a default for new experiments in **Preferences**.

## Choose a reference genome

For BAM experiments and the **IGV viewer**, choose **GRCh37 / hg19**, **GRCh38 / hg38**, or a custom local reference. Use the exact FASTA used for alignment and panels designed for its coordinates. The analysis records the selected file. When reopening an experiment, IGV uses the reference recorded for that run.

- **Use a local FASTA.** Select the build and register your local FASTA. For an uncompressed FASTA, NewPat can create a missing `.fai` beside it in a writable folder. A BGZF-compressed FASTA requires the matching `.fai` and `.gzi`. Keep the FASTA at its registered path so future experiments can reuse it. You can keep more than one file for the same assembly family. Use a custom reference for the bundled synthetic data or a reference with a different sequence dictionary.
- **Obtain a standard reference.** Choose the build and start its UCSC download. The download screen reports progress. After verification and indexing, the reference is available locally for both experiments and IGV. Allow about 1 GB of network traffic and at least 4.5 GB of free disk space per build for preparation. With the reference installed, subsequent selections work offline.
- **Check the variant.** The downloadable presets are the UCSC initial hg19 and hg38 FASTA releases with `chr`-prefixed names. A BAM aligned against a numbered-contig GRCh37 FASTA, for example, should use that file. The original hg19 mitochondrial sequence also differs from the GRC GRCh37 sequence. Choosing a build preserves input coordinates. [UCSC assembly conventions](https://genome.ucsc.edu/FAQ/FAQreleases.html) · [UCSC hg19 downloads](https://hgdownload.soe.ucsc.edu/goldenPath/hg19/bigZips/initial/) · [UCSC hg38 downloads](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/initial/)

NewPat verifies the full contents of a registered FASTA and its indexes when you select it or validate an experiment that uses it. Opening the picker uses a shorter check for large FASTAs. If NewPat reports a changed reference, confirm that the FASTA and indexes belong together and register them again. References saved by an earlier preview of 0.9.10 also need one new registration to record their content digests.

## Find or reopen results

In **Experiments and results**, search by experiment name, status or marker type. Open a result to see its summary, module tables, plots and original files. A paged table is a preview; export the original file to work with the complete rows and stored values. You can export a single file or a ZIP of the results.

Use **Open existing results** to add an existing run folder to the archive. NewPat records its location. **Remove from list** hides the entry and leaves its files on disk. You can register that folder again.

If NewPat closes during calculation, reopen the application and check the run status. **Needs verification** means NewPat cannot determine whether the underlying process is still active. Wait for confirmation before relaunching or removing the entry. Completed output from one step may be available while the overall experiment is still incomplete. The [run guide](RUNS.md) explains how to inspect the runtime.

<a id="read-cpi-and-cpin-plots"></a>

## Read the result summary

Select the marker branch and the sample, pair or trio in **Experiments and results**. The summary describes the selected analysis. Keep different panels or site selections separate when comparing estimates.

| Analysis | Summary |
| --- | --- |
| DNP and SNP genotyping | Called and unassigned genotypes for the selected sample. The original tables identify calls as `0/0`, `0/1`, `1/1` or missing. These modules produce the inputs for the parentage analyses. |
| Prenatal CPI | The reported log₁₀(CPI) at the median fetal allele support for that pair and panel (`CPI_medianFF`). It differs from the median of the CPI curve. When the two original plot guides are available, the summary locates the reported point below, between, above or on them. The default guides are −4 and +4. R rounds this CSV value to three decimals, so a point displayed on a guide may have been rounded from either side. The source script provides a curve and the underlying values. It does not issue a categorical parentage finding. |
| Postnatal CPI | The stored CPI and log₁₀(CPI) for the selected trio and site selection, plus the number of contributing sites. If both selections were requested, each has its own summary. Read the curves and original tables for the full output. |
| Contamination | Mean contamination and number of informative sites for the selected sample. An unavailable estimate is distinct from a measured zero. |

### Try the shared example

In **Environment and help**, choose **Save example data**. Select a parent folder for a fresh `synthetic-trio` directory. Open its README to use the same sample IDs, panels, family roles and worker settings. Use the trio to check all five analyses. For comparable DNP and SNP timings, use the dedicated BAM and panels in the timing folder (four contigs, 128 loci and 1,000 reads per locus). Both workloads run offline. The downloadable copy is also usable with 0.9.9. [Example ZIP](../examples/newpat-synthetic-trio.zip)

## Read prenatal and postnatal CPI plots

Hover over a point or click it to see the original table values. With the keyboard, press **Tab** to focus the plot, use the arrow keys to move through the points on the page, **Home** or **End** to reach its ends, and **Esc** to dismiss the details.

| Result | Horizontal axis | Index series | Site counts |
| --- | --- | --- | --- |
| Prenatal CPI | `Iteration`, the minimum fetal read count | `log_CPI`, already on a base-10 logarithmic scale | `NotMismatch` and `Mismatch` |
| Postnatal CPI | Inclusive interval from `Min_child_reads` to `Through_min_child_reads` | `Log10_CPI`, already on a base-10 logarithmic scale | `N_sites`, `Matching_sites` and `Mismatching_sites` |

The separate views give the index and counts their own panels. The combined view shows log CPI in black, matching sites in green and mismatching sites with a dashed orange line. Read the index on the left axis and counts on the right. Total postnatal site counts remain available in the separate view and point details.

Prenatal lines connect consecutive integer thresholds with recorded values. Postnatal segments show values that apply across the stated interval. The postnatal count axis uses a linear transformation of the counts to fit the log CPI display range; point details always show the original counts. The plot uses stored guide values when available and identifies when it uses the observed range. The scale is shared across pages. Missing or invalid values remain available in the original table.

Interactive files are limited to 20,000 rows and 16 MiB each. The plot and detail table display 1,000 rows per page. For larger files, open the results table or original PDF. The PDF includes the scientific plot's layout, guides and annotations.

## Inspect alignments in IGV

The fastest way to see reads is to start with a covered site. In a result table with coordinates and available BAM and FASTA inputs, choose **View in IGV**. To open your own files, use **IGV viewer** and select the reference genome and its tracks. The information button beside the viewer title opens the official introduction in your system browser. Your local tracks stay in the NewPat window. [About IGV](https://igv.org/doc/webapp/)

| Input | Matching index |
| --- | --- |
| Reference FASTA (`.fa` or `.fasta`) | Its `.fai`. A BGZF-compressed reference also needs its `.gzi` alongside it. |
| Sample BAM | Its `.bai` or `.csi` |
| Sample CRAM | Its `.crai` |

Place each index next to the corresponding file for automatic detection, or select the required index explicitly where the control allows. NewPat reads the supplied indices. You can open the reference on its own; add an alignment track to view sample reads. A reported contig length mismatch calls for checking which reference assembly was used for alignment.

Select a chromosome from the list of names in the loaded reference. Enter a locus in the form `chromosome:start-end`, then choose **Go to region**. For example, `1:100000-101000` describes the interval only if the reference uses `1` as a contig name. Coverage depends on your sample. Select `X` by name when the reference labels it `X`.

The whole-genome overview shows the chromosomes. Use **Zoom in** on a covered region to see individual reads. The previous-region and overview controls return to an earlier view or the whole genome. Saving the IGV session records the local file configuration and view. IGV reads large local inputs by range.

## Settings and diagnostics

**Preferences** covers language, reduced motion, folders, scientific defaults and resource settings. The catalog explains scientific parameters, constants and formulas. **Environment and help** provides checks and diagnostic export, even when an experiment fails before producing results. To locate a run, use its open-folder action.

A diagnostic export contains selected metadata and size-limited logs. Logs can include sample names and local paths. Review the archive before sharing. Keep the original data files at their recorded locations if you plan to reopen them in NewPat.

The desktop runs in WebView2 on Windows, WKWebView on macOS and WebKitGTK on Ubuntu. The application communicates with its engine through a local loopback service. You open the installed application directly.
