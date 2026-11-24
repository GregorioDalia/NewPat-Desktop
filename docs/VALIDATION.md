# Technical and domain validation worksheet

Record installation, execution and scientific agreement separately. Identify the exact package, commit, platform and data used. Use **not run** or **not assessable** where appropriate. The installed self-test covers its fixtures. Scientific suitability on representative data requires independent domain review. [Installed synthetic suite](WINDOWS_INSTALLATION_TEST.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md)

## Environment and installation

Use a separate record for Windows 10 22H2 x64 build 19045, Windows 11 x64, macOS 14+ Intel, macOS 14+ Apple Silicon and Ubuntu 24.04 x86_64 as applicable. Windows uses WSL2. The Mac uses Lima and an AMD64 scientific image, with Rosetta on Apple Silicon. Ubuntu uses its local Docker daemon. Distinguish installed packages from source checkouts.

| Field | Observed value |
| --- | --- |
| OS version, hardware and architecture | |
| NewPat version, commit or package identity | |
| Package source and available checksum | |
| Windows WSL2 version and initial availability | |
| Mac model, Lima version, guest architecture and Rosetta availability | |
| Ubuntu Docker Engine and Compose versions, origin and daemon access | |
| Clean install, repair or upgrade from which version | |
| Data and results roots | |
| Setup outcome, permissions, restarts and manual steps | |
| `doctor --runtime` and final `self-test` result | |
| Desktop launch, interaction and terminal menu access | |
| Isolation from other or experimental installations | |
| Saved preferences and actual values in the run summary | |
| Input checksum mode and CPU, RAM and process limits | |

On Windows, launch the distributed setup and open the installed NewPat shortcut. Retain `setup.log` and `state.json` in the installation's `.runtime\installer` directory. Test initial WSL enablement, reboot/resume, installation on a working WSL system and upgrade as separate cases.

On the Mac, open the architecture-specific `.pkg`, launch NewPat from Applications, check Lima provisioning and open both the desktop interface and the packaged CLI. Retain `runtime.json` and `setup.log` in `~/Library/Application Support/NIPAT-Desktop/.runtime/macos`. Record Gatekeeper messages and path or authorization issues. On Apple Silicon, confirm that the AMD64 workload actually executes through Rosetta.

For each platform test reopening, reinstalling, resuming interrupted setup and retention of user files. Distinguish reinstalling the same build from upgrading between versions. Use the documented ownership check for Mac VM removal. Check the package actually used, in addition to reviewing [automated build evidence](CI_CD.md).

<a id="prima-prova-con-docker-desktop"></a>

## First end-to-end check

For a first check without study data, open **Environment and help → Open demo**, review the three prefilled BAMs and run both callers with the supplied reference and panels. For each caller, the three maternal loci should each have 96 REF, 4 ALT and genotype `0/0`. The paternal and child loci should each have 50 REF, 50 ALT and genotype `0/1`. All have zero Other reads. Choose **Save example data** to copy the instructions and inputs for the downstream analyses. In the source repository, `tests/fixtures/synthetic-trio-v1/expected.tsv` lists the expected rows and coordinates.

For a representative case with your own inputs, follow these steps.

1. Open NewPat, check the version and choose a results folder for the test.
2. Run the environment check (option **8** in the terminal menu).
3. Run DNPcall on a known BAM, matching indexed reference and DNP panel. Record settings before launch.
4. Verify final state, sample count, alias mapping, loci, counts and genotypes.
5. Use the matching panel and individual count tables for Contamination. Compare the summary and per-site results.
6. Exercise SNPcall, prenatal CPI and postnatal CPI on cases with the required inputs, roles and independent expectations. [User guide](USER_GUIDE.md)

`--dry-run` exercises request preparation. Record it as a simulation. A scientific comparison requires an executed run and actual outputs.

### Composite plans

Check both the plan outcome and its individual steps. Compare every DNP or SNP table with the one consumed downstream. Keep marker types distinct. Verify the original BAM-to-table mapping, roles and IDs for pairs or trios, including families sharing a parent. Compare single-module results with the same steps inside a plan at identical settings. For SNPcall compare the BAM and imported-pileup routes from the same case and test same-named files in separate directories. Exercise invalid input and cancellation. Pending dependants should stay blocked and existing evidence should remain available. A repeated experiment gets a new folder.

For prenatal CPI, supply appropriate maternal cfDNA and paternal samples and compatible frequencies. For postnatal CPI, supply distinct mother, father and child samples. SNP and DNP calls can each feed Contamination, prenatal and postnatal CPI on their respective branches. A contamination estimate is a separate output and does not drive an automatic CPI filter.

## Repeat the scientific correctness suite

From the repository root, build the candidate scientific image and run the same native suite as CI. These commands work with Linux containers in Docker Desktop on Windows PowerShell, macOS, or Docker on Linux. They generate tiny artificial reads and tables locally. The inputs, reference bases and expected observations are defined in the tests. No study BAMs or external genome downloads are required.

```sh
docker build --platform linux/amd64 -f docker/scientific-runtime/Dockerfile -t newpat-science-check .
docker run --rm --platform linux/amd64 --network=none --cpus=4 --memory=8g -v "${PWD}:/qualification:ro" -v "${PWD}/build/oracle-results:/evidence" -w /qualification -e PYTHONPATH=/opt/nipat/lib:/qualification/src --entrypoint python3 newpat-science-check /qualification/.github/scripts/check_native_r.py --report /evidence/native-r.json
```

A successful run exits with code 0 and writes `"passed": true` in `build/oracle-results/native-r.json`. The report records the scientific manifest and test-source digests, R and samtools versions, duration by test method, parameterized comparisons, and any failures or skips. A missing required suite or a skipped native test prevents a pass. The scientific job attaches the same report to its diagnostics in the native R check directory. Runs on different machines can be compared using the same revision, manifest and test case IDs. Durations include fixture construction and validation.

| Question | Inputs and expected result |
| --- | --- |
| Are the counts, genotypes and likelihoods right? | Cross all 12 ordered SNP allele pairs and all 240 ordered DNP haplotype pairs with ten read mixtures. Each mixture specifies the reads before BAM creation. Compare REF, ALT, Other and GT and independently calculate the three diploid log-likelihoods at known Phred scores. Separate cases vary Phred and mapping quality, zero-quality observations, depth limits, orphaned pairs, excluded flags and acquisition modes. [Caller oracle](../tests/test_native_r_caller_oracle.py) |
| Is the correct reference and sample used? | Run three distinguishable BAM profiles with plain and BGZF FASTA, changed reference bases, sample order and indexing. A matching panel on an allele-swapped reference must produce the predicted counts. An old panel against those same bases or a missing compression index must fail. These are small custom assemblies. The hg19/GRCh37 and hg38/GRCh38 catalog checks are separate. [Reference oracle](../tests/test_native_r_reference_oracles.py) |
| Does contamination use the right sites and denominator? | Sweep all 91 splits of 90 allele observations at four Other-read levels. Test default, asymmetric and strict settings on both marker types. Check site membership, unexpected-read counts, fractions, the sample mean, sample standard deviation and the expected missing values in empty or one-site samples. [Contamination oracle](../tests/test_native_r_contamination_oracle.py) |
| Does prenatal CPI change by the predicted amount? | Multiply independently specified rational per-site indices and compare both the product and its base-ten logarithm at each fetal-read threshold. Repeat with exchanged alleles, altered settings and two panels. In a separate batch, six pairs share parents. Their six different single-locus indices are known in advance and must stay attached to the right pair when ordering and worker settings change. [Threshold and panel oracle](../tests/test_native_r_prenatal_oracle.py) · [Family oracle](../tests/test_native_r_family_oracle.py) |
| What does the current postnatal model report at each site? | Exercise all 27 combinations of maternal, paternal and child diploid genotypes for each marker type. Check site status, obligate allele and compatibility in the existing output. The revised scalar will need its own author-confirmed example and scale. [Postnatal site contract](../tests/test_native_r_postnatal_contract.py) |

For example, in the shared-parent case the synthetic maternal sample contains 97 REF and three ALT observations. At an ALT frequency of 0.2, a homozygous ALT father gives a single-site index of 5, a heterozygous father 2.5, and a homozygous REF father 0.1 with the selected mismatch weight of 0.02. The table is checked separately for each pair and fetal-read threshold. These are software checks against the specified model. Accuracy on representative family data requires separate domain validation.

## Per-analysis record

| Field | Observed value |
| --- | --- |
| Case ID suitable for sharing | |
| NewPat version, image identity and run name | |
| Workflow, input mode and configured parameters | |
| Input provenance, genome reference, panels and frequencies | |
| Plan step IDs, sample IDs, marker types, pairs or trios | |
| Output location | |
| Expected result and source of that expectation | |
| Observed counts, estimates and relevant plots | |
| Columns, ordering, comparison criteria and numerical tolerance | |
| Technical outcome (completed, failed or interrupted) | |
| Scientific outcome (agreement, discrepancy or not assessable) | |
| Usability problems, exact messages and reproducible materials | |

For a revised scientific script, retain the upstream revision, a shareable example input, the author’s invocation and the independently checked expected result. For the pending postnatal CPI revision, record which site selection the scalar summarizes, whether it is on the CPI or log₁₀ scale, and the expected output when no sites qualify. For the planned sixth module, use the [integration guide](ARCHITECTURE.md#adding-a-downstream-scientific-module) once the script and its example arrive.

A rerun of the same implementation measures repeatability. Use an independent analytical result, validated dataset or reference implementation when evaluating accuracy.

## Coverage by module

| Area | Cases and observations |
| --- | --- |
| DNPcall | One and multiple BAMs, list and repeated arguments, serial and parallel execution, sample aliases, locus counts and genotypes. |
| SNPcall 2.0 | BAM and matching pileup, REF/ALT/Other, qualities, likelihoods, genotypes at the configured Other threshold (default 10%), central and neighboring indels, overlapping windows, uncovered loci and multiple samples. |
| Contamination | Identical inputs selected by file or directory, optional `ratio_REF_ALT`, no informative sites. |
| Prenatal CPI | Explicit pairs, compatible frequencies, all loci, one panel or several labeled cutoffs, fetal fraction, CPI curves and no informative sites. |
| Postnatal CPI | Explicit trios, SNP and DNP frequencies, compatible transmission, mismatch and no informative sites. |
| Composite plans | Both caller branches, all three consumers, explicit families, single and batch SNPcall, standalone parity and blocked steps on failure or interruption. |
| Paths and validation | Spaces, paths outside the project, custom results roots, missing files, invalid encoding, duplicate headers, aliases and case collisions. |
| User interaction | Saved defaults, a clean new experiment form, per-run overrides, cancellation, results access and reopening after failure. |

Repeat a known case with identical explicit parameters and compare effective values in `run.json`. Test changing, discarding and restoring preferences and a saved reference that becomes unavailable. Direct CLI runs should use their own explicit arguments. Test upper/lowercase SNP alleles and both supported panel representations. Original files must remain intact. Reject negative counts, duplicate loci, zero or nonfinite frequencies. Record warnings separately when supplied values are retained, for example a ratio inconsistent with the counts. [Input and output checks](INPUT_VALIDATION.md)

For equivalent modes, compare the actual tables using the preselected order and tolerance. Keep CPI cutoff labels separate. For plots check zero, class boundaries, missing values, sample labels and legibility with many loci. An `NA` estimate can be expected without informative sites. For DNP, check the samtools exit and artifact validation. [Scientific references](../scientific/README.md)

Test cancellation through both the supported interface and CLI. A failed run must remain accessible with its log. Incomplete-run inspection should distinguish unavailable runtime, absent container and active container while preserving the original record. [Run states](RUNS.md)

## Isolation, updates and resource settings

Record the initial and final application versions, package checksum and update log. Confirm that the offered package is compatible and that an upgrade retains paths, preferences, experiments and results. Run a known case afterwards. Verify isolation from any experimental installation.

For resource configuration, record physical RAM, saved and effective VM settings and container limits. Test preview cancellation, saving with restart deferred and applying after confirmation. Verify backups and unrelated settings. Coordinate a WSL restart with work running in other distributions.

Use sample filenames with spaces and identical basenames in different folders. Verify sample maps and labels in tables and PDFs against canonical outputs. For failures distinguish an observed cause, unavailable diagnostics and an inference based on an exit code.

## Evidence and reporting

Retain the run, including `run.json`, `execution.log`, `work`, outputs and the inputs needed to repeat the case. The default `auto` provenance policy records size and modification time for files larger than 16 MiB. Use `--input-hashes full` when the protocol requires full checksums and account for the additional I/O.

Report the software version, platform, exact operations, expected and observed results and complete error message. Logs, names and paths may identify samples. Review materials before sharing them through an appropriate channel.
