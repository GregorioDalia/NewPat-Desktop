# Verification priorities

NewPat development centers on the reproducibility of research results and the operation of the local analysis environment.

| Area | What to verify |
| --- | --- |
| Scientific results | Compare tables, counts and unrounded values with declared reference results. Record input data, settings and acceptance criteria for representative cases. |
| Workflow integrity | Trace sample identities, family roles and effective settings to the correct outputs. Check records after cancellation, failure and recovery. |
| Performance | Use identical inputs and resource limits. Measure BAM acquisition, R calculation and full elapsed time separately. Compare scientific results before interpreting a timing difference. |
| Platform support | Exercise installation, launch, update and recovery on Windows, Ubuntu, and both Apple Silicon and Intel Macs. Associate each observation with its package and system. |
| Desktop usability | Walk through sample selection, validation, progress, results and diagnostic export in the supported interface languages. Check that error messages identify the next action. |

## Next stable release

The next planned public release is 0.9.99. Version 0.9.10 is the stable comparison build for all six analyses and the starting point for the upgrade test. Integrate changes through pull requests and use internal installer builds to test them. A direct update from the installed 0.9.10 package is part of release qualification. [0.9.10 acceptance record](https://github.com/GregorioDalia/nipat-desktop/blob/11a78744eb7f034f1e510ef6e5f9f158c957f9b5/.github/release-acceptance/v0.9.10.json) · [Publication procedure](../.github/RELEASE.md)

| Area | Work for 0.9.99 |
| --- | --- |
| Native Apple Silicon | Keep the Lima ARM64 guest and ship a Linux ARM64 scientific image with native R, its packages and samtools. The standard Apple Silicon path must run with Rosetta disabled. Build and verify the matching archives for ARM64 and AMD64, select by architecture, and verify the installed engine on each platform. |
| Automatic resources | Tune macOS using the CPU and RAM actually available inside Lima, the BAM workload and the demands of other experiments. Measure acquisition and R processing separately. Preserve the established Windows behavior and use its stable measurements to detect regressions. |
| Performance qualification | Run the same synthetic 1-, 2- and 4-BAM suite on stable and candidate installations. Repeat a representative multi-BAM workload on the same physical Mac. Use the same files, settings and VM allocation when comparing architectures. Then measure the effect of the automatic resource policy. Report repeated end-to-end times, phase times, observed workers and peak memory alongside scientific agreement. Set a meaningful improvement target from the Mac baseline before tuning the candidate. [Mac benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac) |
| Scientific qualification | Review all six modules against synthetic inputs and reference results. For prenatal and postnatal CPI retain coverage of the revised models. For fetal sex accept a combined maternal autosomal/X DNP table plus a Y SNP table, alongside the three-table format. Apply the existing filters to the supplied specificity-validated sites. Compare all four output tables for each published maternal example. [Postnatal CPI references](https://github.com/lpistacchia/NEWPAT/tree/97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4/CPI_postnatal/examples) · [Fetal sex references](https://github.com/lpistacchia/NEWPAT/tree/dde1a759e4b994a42ec9c9651f896394c546b109/Fetal_sex/examples) |
| Installation and experiment recovery | Qualify direct downloads, recovery of the managed Lima environment after an upgrade, and consistent experiment status across desktop sessions. Verify that completed, interrupted and still-active experiments remain distinguishable after an application or VM restart. |

The current CPI display highlights the reported log index against two numeric limits and marks exact boundaries. User-selectable strict or inclusive comparison operators for assigning outcome categories remain a separate proposal.

Scientific reference implementations, analytical test cases and domain review serve different purposes. Record which comparison you performed and the evidence it supports. For an issue, include the software version, platform, expected behavior, observed behavior and the smallest input that reproduces it. The package acceptance process records which checks ran on an installer and which observations came from a physical device.

[Scientific components](../scientific/README.md) · [Technical and domain validation](VALIDATION.md) · [Performance measurements](PERFORMANCE.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md)

## NewPat naming and the 0.9.10 upgrade

The repository now uses `GregorioDalia/NewPat-Desktop`. The candidate's source packages are `newpat` and `newpat_scientific`. The [code guide](CODE_GUIDE.md) follows an experiment through the desktop interface, experiment management and scientific input preparation. [Repository identity and update paths](CI_CD.md#repository-identity-after-the-rename)

Before release, verify a clean install and an upgrade from 0.9.10 on each supported platform. Reopen an existing experiment and run a new analysis. Check source paths, installed entry points and generated package metadata for obsolete names. Retain documented historical references, compatibility aliases and ownership identifiers required to recognize existing installations and their data.
