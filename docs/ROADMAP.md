# Verification priorities

NewPat development centers on the reproducibility of research results and the operation of the local analysis environment.

| Area | What to verify |
| --- | --- |
| Scientific results | Compare tables, counts and unrounded values with declared reference results. Record input data, settings and acceptance criteria for representative cases. |
| Workflow integrity | Trace sample identities, family roles and effective settings to the correct outputs. Check records after cancellation, failure and recovery. |
| Performance | Use identical inputs and resource limits. Measure BAM acquisition, R calculation and full elapsed time separately. Compare scientific results before interpreting a timing difference. |
| Platform support | Exercise installation, launch, update and recovery on Windows, Ubuntu, and both Apple Silicon and Intel Macs. Associate each observation with its package and system. |
| Desktop usability | Walk through sample selection, validation, progress, results and diagnostic export in the supported interface languages. Check that error messages identify the next action. |

## Outstanding work for 0.9.10

| Item | Evidence needed |
| --- | --- |
| Revised prenatal and postnatal CPI | Compare the packaged workflows with the revised upstream models, including the postnatal [worked SNP and DNP trios](https://github.com/lpistacchia/NEWPAT/tree/97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4/CPI_postnatal/examples). Check the scalar and its logarithm in the postnatal summary, site audit and exported results. |
| Sixth downstream module | Obtain the sex-estimation script, invocation, required inputs and expected outputs. Use these to define the module contract and add a regression case. [Integration steps](ARCHITECTURE.md#adding-a-downstream-scientific-module) |
| Performance on physical Apple Silicon | Compare the installed stable build on the same BAM lists and fixed Lima allocation. Record actual worker counts, phase times and table agreement. [Mac benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac) |

The two CPI sources have been supplied. The sixth script is still under development. Qualify the final module set before publication. The physical Mac measurement is planned for after the stable build becomes available. [Publication procedure](../.github/RELEASE.md)

The current CPI display highlights the reported log index against two numeric limits and marks exact boundaries. User-selectable strict or inclusive comparison operators for assigning outcome categories remain a separate proposal.

Scientific reference implementations, analytical test cases and domain review serve different purposes. Record which comparison you performed and the evidence it supports. For an issue, include the software version, platform, expected behavior, observed behavior and the smallest input that reproduces it. The package acceptance process records which checks ran on an installer and which observations came from a physical device.

[Scientific components](../scientific/README.md) · [Technical and domain validation](VALIDATION.md) · [Performance measurements](PERFORMANCE.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md)

## Release requirement for 0.9.99: NewPat throughout the project

Use NewPat consistently throughout the maintained project, including package names, imports, command names, configuration keys, environment variables, runtime paths, installers, tests and build workflows. Reorganize directories by responsibility and give them descriptive English names so a reader can locate the desktop interface, experiment management, scientific input preparation and analysis code directly. Update the [code guide](CODE_GUIDE.md) to match the delivered layout.

Before release, search tracked file names, directory names and text case-insensitively for the former product name (NIPAT). Repeat the check on the installed file tree and generated package metadata. Resolve every occurrence in maintained code and delivery files. Verify a clean install and an upgrade from 0.9.10, including reopening an existing experiment and running an analysis, on each supported platform.
