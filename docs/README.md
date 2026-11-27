# NewPat documentation

For a first run, install the package for your operating system, then open the guided demo with the three bundled samples. [Guida rapida in italiano](QUICKSTART_IT.md) · [English demo instructions](GUI.md#try-the-shared-example) · [0.9.10 release notes](RELEASE_0.9.10.md)

<a id="installare"></a>

## Install NewPat

For the published version, choose the installer under **Assets** on the release page. Each platform guide explains how to prepare the local environment that runs R and samtools. [Latest stable release](https://github.com/GregorioDalia/NewPat-Desktop/releases/latest)

| Platform | Guide |
| --- | --- |
| Windows 10 or 11, x64 | [Windows setup, WSL2 and the complete ZIP](WINDOWS_INSTALLER.md) |
| macOS, Apple Silicon or Intel | [macOS packages and Lima](MACOS_INSTALLER.md) |
| Ubuntu 24.04, x86_64 | [Ubuntu package and Docker Engine](LINUX_INSTALLER.md) |

[System requirements and package formats](DISTRIBUTION.md) · [Check a Windows installation with synthetic data](WINDOWS_INSTALLATION_TEST.md)

## Analyze samples

| To do this | Read |
| --- | --- |
| Choose an analysis from the files you have | [NewPat at a glance](../OVERVIEW.md) |
| Set up experiments, reuse a profile, explore plots or inspect alignments in IGV | [Desktop guide](GUI.md) |
| Choose input files, assign family roles or run a workflow from the terminal | [Input formats, commands and workflows](USER_GUIDE.md) |
| Understand a rejected input or an output warning | [Input and output validation](INPUT_VALIDATION.md) |
| Check a formula, default, constant or allowed parameter range | [Scientific catalog](SCIENTIFIC_CATALOG.md) |
| Locate a result, log, sample mapping or incomplete run | [Run folders and records](RUNS.md) |
| Check CPU and memory allocations or investigate an interrupted process | [Resources and memory](RESOURCES.md) |
| Measure execution time and resource use | [Performance diagnostics](PERFORMANCE.md) |

## Development and verification

| To do this | Read |
| --- | --- |
| Find the source for a screen, a formula or a test | [Code guide](CODE_GUIDE.md) |
| Trace a workflow from the desktop client to the scientific engine | [Architecture](ARCHITECTURE.md) · [Workflow contract](WORKFLOW_CONTRACT.md) · [Engine interface](../engine/README.md) |
| Check a scientific module, its inputs and the evidence for its results | [Scientific components](../scientific/README.md) · [Scientific CI checks](CI_CD.md#scientific-checks) · [Validation worksheet](VALIDATION.md) |
| Review a change, qualify an installer set or publish an accepted release | [CI and packaging](CI_CD.md) · [Installer acceptance](INSTALLER_ACCEPTANCE.md) · [Publication procedure](../.github/RELEASE.md) |
| Review the 0.9.10 audit and outstanding verification work | [0.9.10 code audit](AUDIT_0.9.10.md) · [Verification priorities](ROADMAP.md) |
