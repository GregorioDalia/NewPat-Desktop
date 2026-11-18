# Technical review of 0.8.50

The review covered five R scripts, scientific helpers, Python adapters and the client, workflows, presentation, installers, CI and publication. Scientific checks used frozen references. Historical runs retain their original version identities.

## Corrected defects

| Area | Finding and verification |
| --- | --- |
| CPIN with no sites | R inferred logical types for header-only tables and all-`NA` `total_count` columns at zero-coverage sites. Explicit typing and zero-length vector handling accept these inputs. SNP and DNP regressions preserve rejection of unsupported missing counts. |
| Extreme allele frequencies | Division by a tiny positive frequency could overflow before the logarithm. The overflow branch computes in log space for finite positive frequencies. Ordinary results are preserved and zero frequencies are rejected. |
| DNP panel | Early validation rejects identical REF and ALT alleles and contig names containing unsupported internal delimiters. |
| Scientific settings | Each module must emit its R settings. Validation checks the entire schema, names, types, values and constants, including the distinction between booleans and numbers. |
| CPI and CPIN summaries | Marker type, minimum reads and error constant are checked against the request before success is recorded. |
| Sample roles | Aliases and hard links could assign one physical file to two distinct family samples. Preflight rejects that assignment. A parent can still be shared across families. |
| JSON settings | Duplicate module or parameter keys are rejected. |
| HTML report | Pair and trio roles from generic workflows are displayed, including workflows with different downstream analyses on the two branches. |
| Update channel | New official profiles default to `stable`. An explicit `testing` preference is retained. |
| Test discovery | Pinned quality dependencies and pytest discovery cover unittest- and pytest-style cases. |
| Host-specific tests | Host prerequisites are declared explicitly. R verification in the exact scientific runtime requires all its cases to run. |
| Installed acceptance suite | Expectations use normalized plans with marker types and panels with alleles. The R test prerequisites match the packages the tests actually use. |

## Performance and operations

Docker test evidence uses the runner's UID/GID and private file permissions. Progress tests use a deterministic clock with real threads for success, failure and cancellation. Following exit 137 or −9, diagnostics recheck Docker's status for the same verified container identity for up to two seconds before removal. A delayed OOM flag can confirm the cause. Exit 137 alone cannot. The intentional OOM integration test requires explicit Docker confirmation.

The five-module matrix produces more than 3,500 text evidence files. The qualification archive file limit increased from 3,000 to 5,000. The size limits remain 64 MiB overall and 8 MiB per file. The verifier checks eligible formats, identity, names, sizes and digests, and distinguishes count and byte limits.

A per-preflight CPI/CPIN cache avoids rescanning shared parents. With 100 trios, two shared parents and 100 different children, complete table scans decreased from 300 to 102. The test also verifies unchanged inputs and absence of a run directory after preflight. The runtime still validates its inputs.

The DNP planner indexes locus, coordinate and pileup-row membership once. A local microbenchmark with 10,000 markers and three alternating measurements recorded **8.345, 7.913, 7.988 s** for the former planner and **0.546, 0.560, 0.620 s** for the indexed planner. Medians were **7.988 s** and **0.560 s**. All 18 plan comparisons were exactly identical, including overlapping coordinates and type-inference cases. This benchmark measures planning alone. Real BAM runtime requires an [end-to-end performance measurement](PERFORMANCE.md).

The CPU and memory budget remains shared, with a serial mode and no nested worker pools. CPIN caches samples and represents curves as intervals. CPI retains its cache and optimizations. Presentation exports still load complete tables to replace labels; streaming large tables was identified as a possible improvement. No real-BAM regression was attributed to the export during this audit.

## Scientific qualification

- DNP was compared with NIPAT 0.8.5 and SNP with NEWPAT 2.0. CPI, Contamination and CPIN used the three updated NEWPAT reference scripts and independent analytical expectations.
- Tests covered batches of 2, 3 and 5, parameter changes, absence of informative sites, and serial, automatic and manually capped modes.
- A complete workflow used three BAMs, both marker types and all downstream analyses. Thirty tables were compared between serial and two-worker runs.
- Sixteen SNP and DNP R runs covered empty samples and trios, all-zero coverage with missing totals, malformed totals, extreme positive frequencies and zero frequencies. They verified empty estimates and curves where allowed, explicit errors for invalid input, and analytical log CPI values for overflow cases.
- Checks covered cancellation, diagnostics, invalid inputs and artifact integrity. Qualification records input, output, logs, sources, reference and verifier hashes, settings emitted by R, and worker activity. The exact installed image runs the complete workflow through the public client.

Schema 7 binds both scientific reports, immutable image, commit and four installer packages. Publication tests reject missing or incomplete reports, altered data and inconsistent identities.

## Installer evidence

Review of the Windows CMD-to-PowerShell launch path, inventory, directory separation and verified archive reuse found no additional packaging defect in these areas. Each included script's local dependencies are checked. The setup leaves device Smart App Control policies in place.

Windows 10/11 setup with WSL, macOS startup with Lima, desktop acceptance, device trust decisions and domain validation each have their own scope. The acceptance record distinguishes automated checks, historical observations and deferred scenarios. See [release notes](RELEASE_0.8.50.md) and [the build-bound acceptance record](../.github/release-acceptance/v0.8.50.json).
