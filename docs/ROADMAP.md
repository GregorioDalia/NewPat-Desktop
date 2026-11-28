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

Release 0.9.99 starts a new installation with its own workspace and runtime. Qualify the packages built from the final candidate commit. Prior scientific and performance reports remain evidence for the commits and datasets they identify. [Publication procedure](../.github/RELEASE.md)

| Area | Work for 0.9.99 |
| --- | --- |
| Native Apple Silicon | Keep the Lima ARM64 guest and ship a Linux ARM64 scientific image with native R, its packages and samtools. The standard Apple Silicon path must run with Rosetta disabled. Build and verify the matching archives for ARM64 and AMD64, select by architecture, and verify the installed engine on each platform. |
| Automatic resources | Tune macOS using the CPU and RAM actually available inside Lima, the BAM workload and the demands of other experiments. Measure acquisition and R processing separately. Preserve the established Windows behavior and use its stable measurements to detect regressions. |
| Performance qualification | Run the same synthetic 1-, 2- and 4-BAM suite on stable and candidate installations. Repeat a representative multi-BAM workload on the same physical Mac. Use the same files, settings and VM allocation when comparing architectures. Then measure the effect of the automatic resource policy. Report repeated end-to-end times, phase times, observed workers and peak memory alongside scientific agreement. Set a meaningful improvement target from the Mac baseline before tuning the candidate. [Mac benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac) |
| Scientific qualification | Review all six modules against synthetic inputs and reference results. For prenatal and postnatal CPI retain coverage of the revised models. For fetal sex accept a combined maternal autosomal/X DNP table plus a Y SNP table, alongside the three-table format. Apply the existing filters to the supplied specificity-validated sites. Compare all four output tables for each published maternal example. [Postnatal CPI references](https://github.com/lpistacchia/NEWPAT/tree/97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4/CPI_postnatal/examples) · [Fetal sex references](https://github.com/lpistacchia/NEWPAT/tree/dde1a759e4b994a42ec9c9651f896394c546b109/Fetal_sex/examples) |
| Installation and experiment recovery | Qualify direct downloads, first launch and recovery of a NewPat session. Verify that completed, interrupted and active experiments remain distinguishable after an application or VM restart. |

The current CPI display highlights the reported log index against two numeric limits and marks exact boundaries. User-selectable strict or inclusive comparison operators for assigning outcome categories remain a separate proposal.

Scientific reference implementations, analytical test cases and domain review serve different purposes. Record which comparison you performed and the evidence it supports. For an issue, include the software version, platform, expected behavior, observed behavior and the smallest input that reproduces it. The package acceptance process records which checks ran on an installer and which observations came from a physical device.

[Scientific components](../scientific/README.md) · [Technical and domain validation](VALIDATION.md) · [Performance measurements](PERFORMANCE.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md)

## Final installer checks

Install on a fresh account, launch through the normal shortcut, complete the demo, reopen it and verify its counts. Record the application, data and runtime paths, the package checksum, and the source commit. For Windows cover both the EXE and complete ZIP. On macOS record the native guest and scientific image architecture. Repeat the checks against the downloadable release assets when publishing.
