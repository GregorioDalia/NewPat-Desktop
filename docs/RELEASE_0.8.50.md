# NIPAT Desktop 0.8.50

This release integrated DNPcall, SNPcall 2.0, Contamination, prenatal CPI and postnatal CPIN. DNP and SNP counts can feed any combination of the three downstream analyses. Results remain distinct by marker type. Fetal sex analysis falls outside these workflows.

## Workflow composition

Choose **W → 5** or `workflow analyze` to start with BAMs, SNP pileups or existing tables. The workflow computes each sample's counts once per caller. `--dnp-analyses` and `--snp-analyses` select downstream modules independently. Prenatal CPI takes maternal cfDNA–father pairs. CPIN takes mother–father–child trios. Users assign the roles explicitly, and the outputs and HTML report retain those assignments.

CPIN is also available from **N** or `nipat cpin`. It supports `other_allele`, `all` and `both` selection modes, population frequencies, optional panels, summaries, site exclusion reasons, threshold curves and PDFs. Independent trios can run in parallel. Shared samples are read once. Curves use exact support intervals to avoid rescanning loci for every possible coverage threshold.

## Scientific models

Contamination, CPI and CPIN use [NEWPAT commit 9c2a8be6](https://github.com/lpistacchia/NEWPAT/tree/9c2a8be60afcb944153710da6a61cd0559e2b4cf). The original references are frozen separately from optimized code. SNP keeps the 2.0 reference and DNP the numerical 0.8.5 baseline.

- Contamination filters on `Other/(REF+ALT+Other)`. The per-site estimate is `unexpected/(REF+ALT)`. Zeros are included by default. The overall estimate is the arithmetic mean over informative sites, counted in `informative_sites`.
- CPI uses marker-specific error constants for SNP and DNP and a configurable fetal-read threshold. It supports multiple panels, sample caching and interval curves. Missing values in auxiliary columns preserve otherwise valid sites.
- CPIN handles header-only tables and samples with zero coverage, returning an outcome with no informative sites.

The updated models can produce different values than 0.8.35. A performance comparison requires the same model, inputs and parameters.

## Settings and provenance

`nipat settings` and **Configure → S** show parameters, defaults, limits, constants and model rules. `--scientific-config` imports JSON, and `--set` supplies explicit overrides. Configurable values include pileup settings, genotype thresholds, filters, minimum reads, error constants and CPIN options.

Python and R share one registry. Each step compares the requested `work/effective-scientific-settings.json` with R's `output/scientific-settings.json` before completing. Validation rejects duplicate configurations, invalid values and modified metadata. It checks CPI/CPIN summaries against the requested marker, read threshold and constant.

## Qualification and updates

CI collects both `unittest` and `pytest` cases. It checks caller equivalence separately from independent reference comparisons for the three updated models. The built runtime executes batches of 2, 3 and 5 in serial, automatic and two-worker modes, and an entire three-BAM workflow in serial and two-worker modes. Checks cover expected values, identity, effective settings, resource limits, table equality and input integrity.

The acceptance record connects the scientific reports, immutable image, commit and four installer binaries. The release publishes the qualified artifacts without rebuilding them. Synthetic regressions do not quantify speed on real BAMs or scientific validity on real cases. The record distinguishes desktop client and package checks from end-device WSL/Lima tests.

New profiles default to `stable`. An explicit `testing` preference is retained. Finish active analyses, use **Check for updates** or download a package from the [0.8.50 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.50). Verify the version and run `nipat self-test` before starting a new case. Existing runs remain available. On Windows the launcher uses scripts and PowerShell. The setup lacked a NIPAT Authenticode signature or Smart App Control qualification. Mac packages lacked notarization. See the [Windows](WINDOWS_INSTALLER.md), [macOS](MACOS_INSTALLER.md), [Ubuntu](LINUX_INSTALLER.md) and [five-module](DEVELOPMENT_0.8.50.md) guides.
