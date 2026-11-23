# Synthetic trio

Use the trio to check DNP and SNP calling, prenatal CPI, postnatal CPI and Contamination from the same three indexed BAMs. The reads cover three loci at a depth of 100 reads per sample at each locus. For a timing comparison across computers, use the single, larger sample in [the timing experiment](#run-the-timing-experiment). All reads, roles and population frequencies are synthetic.

## Run from BAMs

This dataset is `synthetic-trio-v1`. The ZIP has a companion `.sha256` file and the extracted folder contains `SHA256SUMS` for all its inputs. In NewPat 0.9.10, select **Environment and help → Save example data** and choose a local folder. Alternatively, download and extract the complete example ZIP from GitHub. Keep each `.bam.bai` beside its `.bam` and `synthetic.fa.fai` beside `synthetic.fa`. All paths below are relative to this folder. The BAM workflow is available in desktop versions 0.9.9 and 0.9.10.

1. Open **New experiment**. Under **Samples**, select **BAM or SNP pileup**, **DNP and SNP**, and the **BAM** file type. Add the following files and check their sample IDs.

   | Sample ID | File | Expected REF / ALT reads at each locus |
   | --- | --- | --- |
   | `mother` | `alignments/mother.bam` | 96 / 4 |
   | `father` | `alignments/father.bam` | 50 / 50 |
   | `child` | `alignments/child.bam` | 50 / 50 |

2. Select `reference/synthetic.fa` as the **Reference genome FASTA**. For **Site panel DNP** choose `panels/dnp.tsv`. For **Site panel SNP** choose `panels/snp.tsv`.
3. In **Analysis**, select **Prenatal CPI**, **Postnatal CPI** and **Contamination** on **both** the DNP and SNP cards. Under **Prenatal CPI · Family**, add one family, name it `pair1`, and assign `mother` to **Maternal cfDNA** and `father` to **Father**. Under **Postnatal CPI**, add one trio named `trio1` and assign `mother`, `father` and `child` to their corresponding roles. Both callers and Contamination use all three samples. Prenatal CPI uses the pair and postnatal CPI uses the trio.
4. Set the population frequencies and open **Additional panels and site selection**. Use the following files in their corresponding marker branches. Under **Prenatal CPI site selections**, choose **Add selection** twice per branch and enter the labels `Full` and `First`.

   | Field | DNP | SNP |
   | --- | --- | --- |
   | Population frequencies | `frequencies/dnp.tsv` | `frequencies/snp.tsv` |
   | Contamination panel | `panels/dnp-full.tsv` | `panels/snp-full.tsv` |
   | Prenatal CPI selection `Full` | `panels/dnp-full.tsv` | `panels/snp-full.tsv` |
   | Prenatal CPI selection `First` | `panels/dnp-first.tsv` | `panels/snp-first.tsv` |

   The frequency tables supply artificial per-site proportions of 0.75 for REF and 0.25 for ALT. Leave the optional postnatal marker panel empty so the trio uses all sites in the population table. The full panels select all three loci. The first-site panels select one. DNP coordinates use `chr, pos1, pos2` and SNP coordinates use `chr, pos`.

5. Under **Parameters**, use the application's default scientific parameters and automatic execution. Check for any saved personal overrides. In **Review**, verify the three sample IDs, both marker branches and the selected analyses, then start the experiment. In the results, compare the per-sample `N_REF` and `N_ALT` columns with the table above.

## Check the results

With the standard scientific settings, the three loci have the same read proportions in both marker branches. These checkpoints identify sample or panel substitutions quickly.

| Analysis | Checkpoint |
| --- | --- |
| DNP and SNP calls | Three assigned genotypes per sample. Each locus has 100 observations, zero Other reads and the REF/ALT counts listed above. |
| Contamination | The mother has three informative sites and mean 4%. Father and child each have zero informative sites and an unavailable mean. |
| Prenatal CPI | `Full` has three informative sites and `First` has one. The reported median fetal fraction is 8% in both. The expected `CPI_medianFF` values, already on the log₁₀ scale, are 0.903 and 0.301, respectively. |
| Postnatal CPI | For trio `trio1` with the default **Both** site selections, each marker branch reports two rows. All maternally compatible sites and the subset with a heterozygous child each give 3 sites, 3 matching and 0 mismatching. Both rows record CPI = 8 and log₁₀(CPI) ≈ 0.903090. |

The expected postnatal values above refer to the current script and these synthetic inputs. The two prenatal rows use overlapping selections of the same loci. Compare each selection separately. No clinical or individual-level verdict forms part of this exercise.

## Run the timing experiment

Use dataset `synthetic-timing-v1` in the `timing/` folder to measure both callers over four synthetic contigs. Its indexed BAM contains 128,000 aligned reads. All files are ready to open in the installed desktop app.

1. In **New experiment** select **BAM or SNP pileup**, **DNP and SNP** and **BAM**. Add only `timing/timing.bam` with sample ID `timing`. Choose `timing/reference.fa` as the reference, `timing/dnp.tsv` as the DNP site panel and `timing/snp.tsv` as the SNP site panel. Leave all three downstream analyses unchecked on both cards.
2. Use the default scientific parameters. For a common serial baseline choose **Serial** in **Parameters → Execution mode**. For a second condition, choose **Automatic** and set **Maximum computation workers** to **2**. In both cases use **32 MiB** and **64 sites** per DNP block, automatic input verification, and enable **Record performance diagnostics**. Leave the experiment CPU, memory and container process limits empty. Record any CPU and memory limits imposed by the desktop runtime.
3. Expect **128 assigned genotypes per marker** in each run. The panels contain 32 loci on each of `chrTiming01` through `chrTiming04`. On each contig, the first SNP is at position 64, the last at 4032, spaced 128 bases apart. The DNP at each SNP position includes the following base. Each caller should report **600 REF, 400 ALT, zero Other, total 1,000, genotype 0/1** at every locus. Compare the two conditions only after checking these counts.

On 0.9.10, **Parameters → Save as profile** stores the scientific parameters and computation options. Files, marker selections and performance diagnostics belong to the experiment. On either version use **Run again** on the completed experiment to reuse its configuration. Check files, settings and diagnostics before each repetition.

Record the dataset ID, ZIP SHA-256, release tag or commit, desktop and engine versions, OS and architecture, runtime CPU and memory allocation, worker settings and diagnostics status. After installation or a runtime restart, record the first run separately, including whether setup was already complete. Keep the runtime running and perform three further repetitions for each condition, one at a time with no other experiments running. Give each run a distinct name. Subtract `started_at` from `finished_at` in each successful `run.json` and report the median of the three warm-run durations in seconds. Keep the individual measurements and first-run duration alongside the median. These timings characterize this specific calling workload. For the three-locus trio above, startup and orchestration can dominate the elapsed time.

## Start from existing counts

To exercise the downstream modules separately, choose **Existing count tables** in a new experiment. For a DNP run, choose **DNP table** and add `mother.txt`, `father.txt` and `child.txt` from `counts/dnp/`. For a separate SNP run, choose **SNP table** and use the corresponding files in `counts/snp/`. Use the same three sample IDs, prenatal pair, postnatal trio, marker-specific frequencies and coordinate panels as above. This path skips BAM processing, so keep its timing separate from the BAM workflow.
