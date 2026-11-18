# Verification priorities

NewPat development centers on the reproducibility of research results and the operation of the local analysis environment.

| Area | What to verify |
| --- | --- |
| Scientific results | Compare tables, counts and unrounded values with declared reference results. Record input data, settings and acceptance criteria for representative cases. |
| Workflow integrity | Trace sample identities, family roles and effective settings to the correct outputs. Check records after cancellation, failure and recovery. |
| Performance | Use identical inputs and resource limits. Measure BAM acquisition, R calculation and full elapsed time separately. Compare scientific results before interpreting a timing difference. |
| Platform support | Exercise installation, launch, update and recovery on Windows, Ubuntu, and both Apple Silicon and Intel Macs. Associate each observation with its package and system. |
| Desktop usability | Walk through sample selection, validation, progress, results and diagnostic export in the supported interface languages. Check that error messages identify the next action. |

Scientific reference implementations, analytical test cases and domain review serve different purposes. Record which comparison you performed and the evidence it supports. For an issue, include the software version, platform, expected behavior, observed behavior and the smallest input that reproduces it. The package acceptance process records which checks ran on an installer and which observations came from a physical device.

[Scientific components](../scientific/README.md) · [Technical and domain validation](VALIDAZIONE.md) · [Performance measurements](PERFORMANCE.md) · [Installer acceptance](ACCETTAZIONE_INSTALLATORI.md)
