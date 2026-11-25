<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/branding/nipat-logo-dark.svg">
  <img src="assets/branding/nipat-logo.svg" alt="NewPat" width="335">
</picture>

# NewPat

NewPat is a desktop application for research on genetic markers and parentage. It calls genotypes at sites in a supplied SNP or DNP panel, estimates contamination, and calculates prenatal and postnatal combined paternity indices. Researchers can configure an experiment in the desktop window, inspect the reads in the integrated IGV viewer, and export the tables and plots.

Analyses run on your computer. NewPat packages R and samtools with the scientific engine. After you prepare the runtime, you can analyze local files offline. A command-line interface supports scripted runs using the same inputs and settings.

## Download

Open the **latest stable research release** and expand **Assets**. Select the package for your computer using the table below. The release page also lists the checksums. [Download NewPat](https://github.com/GregorioDalia/nipat-desktop/releases/latest)

This guide describes **0.9.10**. The release notes record its status and changes. If you use 0.9.9, its tagged guide covers the launcher names and features available in that build. [0.9.9 documentation](https://github.com/GregorioDalia/nipat-desktop/blob/v0.9.9/README.md) · [What changes in 0.9.10](docs/RELEASE_0.9.10.md)

| System | Asset to choose | Installation guide |
| --- | --- | --- |
| Windows 11 x64 or Windows 10 22H2 x64 (build 19045) | `NewPat-Setup.exe` for standard setup, or the complete Windows ZIP for a folder-based installation | [Windows and WSL2](docs/WINDOWS_INSTALLER.md) |
| macOS 14 or later, Apple Silicon (M-series) | The package ending in `macos-arm64.pkg` | [macOS and Lima](docs/MACOS_INSTALLER.md) |
| macOS 14 or later, Intel | The package ending in `macos-x86_64.pkg` | [macOS and Lima](docs/MACOS_INSTALLER.md) |
| Ubuntu 24.04 LTS, x86_64 | The package ending in `amd64.deb` | [Ubuntu and Docker Engine](docs/LINUX_INSTALLER.md) |

## What you can analyze

| Analysis | What to supply | What you get |
| --- | --- | --- |
| **DNPcall** | One or more BAMs, an indexed reference FASTA, and a double nucleotide polymorphism (DNP) panel | Allele counts and genotypes per sample, summary tables and plots |
| **SNPcall** | A single nucleotide polymorphism (SNP) panel, plus a BAM with an indexed FASTA or a pileup with base qualities and read names | Allele counts, genotype likelihoods, genotypes, indel statistics and plots |
| **Contamination** | SNP or DNP count tables and a matching coordinate panel | Per-site contamination estimates and a summary per sample |
| **Prenatal CPI** | Count tables for maternal cell-free DNA and the alleged father, sample pairings, and population allele frequencies | Fetal fraction estimates, combined paternity index (CPI), tables and plots |
| **Postnatal CPI** | Mother, alleged father and child count tables, sample trios, and population allele frequencies | One CPI per trio, its base-10 logarithm and a table of included and excluded sites |

Run a module on its own or build a workflow. DNPcall and SNPcall can share BAM inputs and feed separate analyses. Each branch uses its own panels and population frequencies. For parentage analyses, assign samples to family roles explicitly.

## Run your first experiment

**Try the demo.** Open **Environment and help → Open demo**. NewPat opens a draft for three simulated samples with DNP and SNP selected. Review the settings and choose **Start experiment**. Open **Experiments and results** when it finishes. Each caller should report three loci per sample, with 100 reads per locus. [Guida rapida in italiano](docs/QUICKSTART_IT.md) · [English desktop walkthrough](docs/GUI.md#try-the-shared-example)

Choose **Save example data** to copy the BAMs, reference, panels, expected results and instructions to a local folder. The separate timing dataset lets you compare runs on different computers with the same BAM and panels. [Example ZIP](examples/newpat-synthetic-trio.zip) · [SHA-256 checksum](examples/newpat-synthetic-trio.zip.sha256)

**Use your own files.** Open **New experiment**, select the sample BAMs, the exact reference FASTA used for alignment and the panel for each caller. Review the configuration and start the experiment. You can reopen the results in the desktop window or read `run-report.html` in the run folder. [Choosing a reference genome](docs/GUI.md#choose-a-reference-genome) · [Reading run results](docs/RUNS.md)

For a DNP run from PowerShell, open the application directory containing `newpat.cmd` and substitute your file paths.

```powershell
.\newpat.cmd dnp-call --bam "C:\Data\sample.bam" `
  --reference "C:\Data\genome.fa" --panel "C:\Data\dnp-panel.txt"
```

[Input formats and CLI examples](docs/USER_GUIDE.md) · [Code guide](docs/CODE_GUIDE.md) · [All guides](docs/README.md)

## Scientific methods

The calling and parentage modules use methods from [DNPcall](https://github.com/fravasini/DNPcall) and [NEWPAT](https://github.com/lpistacchia/NEWPAT). For the underlying methods, see [Pistacchia et al., *Bioinformatics Advances* (2025)](https://doi.org/10.1093/bioadv/vbaf209) on calling double-nucleotide polymorphisms and [D’Atanasio et al., *Genome Research* (2026)](https://doi.org/10.1101/gr.281702.125) on noninvasive prenatal paternity testing.

## License

NewPat is distributed under [GPL-3.0-or-later](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for the licenses and attributions of bundled components.
