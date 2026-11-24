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
| Revised Postnatal CPI | Obtain the updated script and a worked trio with the expected scalar. Verify its value through the engine, original output file and desktop summary. The candidate currently retains the existing summary and curves. |
| Sixth downstream module | Obtain the script, invocation, required inputs and expected outputs. Use these to define the module contract and add a regression case. [Integration steps](ARCHITECTURE.md#adding-a-downstream-scientific-module) |
| Performance on physical Apple Silicon | Compare the installed stable build on the same BAM lists and fixed Lima allocation. Record actual worker counts, phase times and table agreement. [Mac benchmark](MACOS_INSTALLER.md#compare-worker-settings-on-an-apple-silicon-mac) |

The first two items are pending for publication. The physical Mac measurement is planned for after the stable build becomes available. [Publication procedure](../.github/RELEASE.md)

Scientific reference implementations, analytical test cases and domain review serve different purposes. Record which comparison you performed and the evidence it supports. For an issue, include the software version, platform, expected behavior, observed behavior and the smallest input that reproduces it. The package acceptance process records which checks ran on an installer and which observations came from a physical device.

[Scientific components](../scientific/README.md) · [Technical and domain validation](VALIDATION.md) · [Performance measurements](PERFORMANCE.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md)
