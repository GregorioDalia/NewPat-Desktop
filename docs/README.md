# NewPat documentation

<a id="installare"></a>

## Install NewPat

Choose the guide for your operating system. The installer prepares the desktop application and the local environment that runs R and samtools.

| Platform | Guide |
| --- | --- |
| Windows 10 or 11, x64 | [Windows setup, WSL2 and the complete ZIP](WINDOWS_INSTALLER.md) |
| macOS, Apple Silicon or Intel | [macOS packages and Lima](MACOS_INSTALLER.md) |
| Ubuntu 24.04, x86_64 | [Ubuntu package and Docker Engine](LINUX_INSTALLER.md) |

[System requirements and package formats](DISTRIBUTION.md) · [Check a Windows installation with synthetic data](WINDOWS_INSTALLATION_TEST.md)

## Analyze samples

| To do this | Read |
| --- | --- |
| Create an experiment, explore plots or inspect alignments in IGV | [Desktop guide](GUI.md) |
| Choose input files, assign family roles or run a workflow from the terminal | [Input formats, commands and workflows](USER_GUIDE.md) |
| Understand a rejected input or an output warning | [Input and output validation](INPUT_VALIDATION.md) |
| Check a formula, default, constant or allowed parameter range | [Scientific catalog](SCIENTIFIC_CATALOG.md) |
| Locate a result, log, sample mapping or incomplete run | [Run folders and records](RUNS.md) |
| Check CPU and memory allocations or investigate an interrupted process | [Resources and memory](RESOURCES.md) |
| Measure execution time and resource use | [Performance diagnostics](PERFORMANCE.md) |

## Development and verification

[Architecture](ARCHITECTURE.md) · [Workflow contract](WORKFLOW_CONTRACT.md) · [Engine interface](../engine/README.md) · [Scientific components](../scientific/README.md) · [Validation](VALIDATION.md) · [Verification priorities](ROADMAP.md)

[0.9.10 candidate code audit](AUDIT_0.9.10.md) · [CI and packaging](CI_CD.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md) · [Publication procedure](../.github/RELEASE.md)
