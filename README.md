<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/branding/nipat-logo-dark.svg">
  <img src="assets/branding/nipat-logo.svg" alt="NewPat" width="335">
</picture>

# NewPat

NewPat is a desktop application for research on genetic markers and parentage. It calls genotypes at sites in a supplied SNP or DNP panel, estimates contamination, and calculates prenatal and postnatal combined paternity indices. Researchers can configure an experiment in the desktop window, inspect the reads in the integrated IGV viewer, and export the tables and plots.

Analyses run on your computer. NewPat packages R and samtools with the scientific engine. After you prepare the runtime, you can analyze local files offline. A command-line interface supports scripted runs using the same inputs and settings.

## Download

| System | Package | Installation guide |
| --- | --- | --- |
| Windows 11 x64 or Windows 10 22H2 x64 (build 19045) | [Windows setup](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.9.9/NewPat-Setup.exe) | [Windows](docs/WINDOWS_INSTALLER.md) |
| Windows x64, installation in an extracted folder | [Complete ZIP](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.9.9/NewPat-0.9.9-Windows-completo.zip) | [Windows](docs/WINDOWS_INSTALLER.md) |
| macOS 14 or later, Apple Silicon | [Apple Silicon package](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.9.9/NewPat-0.9.9-macos-arm64.pkg) | [macOS](docs/MACOS_INSTALLER.md) |
| macOS 14 or later, Intel | [Intel package](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.9.9/NewPat-0.9.9-macos-x86_64.pkg) | [macOS](docs/MACOS_INSTALLER.md) |
| Ubuntu 24.04 LTS x86_64 | [Debian package](https://github.com/GregorioDalia/nipat-desktop/releases/download/v0.9.9/newpat-desktop_0.9.9_amd64.deb) | [Ubuntu](docs/LINUX_INSTALLER.md) |

Windows uses WSL2, macOS uses Lima, and Ubuntu uses a local Docker Engine. The download page includes the package checksums. [NewPat 0.9.9 downloads](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.9)

## What you can analyze

| Analysis | What to supply | What you get |
| --- | --- | --- |
| **DNPcall** | One or more BAMs, an indexed reference FASTA, and a double nucleotide polymorphism (DNP) panel | Allele counts and genotypes per sample, summary tables and plots |
| **SNPcall** | A single nucleotide polymorphism (SNP) panel, plus a BAM with an indexed FASTA or a pileup with base qualities and read names | Allele counts, genotype likelihoods, genotypes, indel statistics and plots |
| **Contamination** | SNP or DNP count tables and a matching coordinate panel | Per-site contamination estimates and a summary per sample |
| **Prenatal CPI** | Count tables for maternal cell-free DNA and the alleged father, sample pairings, and population allele frequencies | Fetal fraction estimates, combined paternity index (CPI), tables and plots |
| **Postnatal CPI** | Mother, alleged father and child count tables, sample trios, and population allele frequencies | Site-level paternity indices, combined paternity index, tables and plots |

Run a module on its own or build a workflow. DNPcall and SNPcall can share BAM inputs and feed separate analyses. Each branch uses its own panels and population frequencies. For parentage analyses, assign samples to family roles explicitly.

## Run your first experiment

To try NewPat with the same inputs on every computer, use the synthetic trio. It includes three indexed BAMs, a reference FASTA, SNP and DNP panels, population frequencies, count tables and expected results. In 0.9.10 open **Environment and help → Save example data**, choose a local folder and follow the enclosed README. With 0.9.9, download and extract the ZIP first. Use the trio to check expected results, or the separate timing workload (one BAM, four contigs, 128 loci) to compare DNP and SNP runtimes. [Example ZIP](examples/newpat-synthetic-trio.zip) · [SHA-256 checksum](examples/newpat-synthetic-trio.zip.sha256)

1. Open **NewPat**, choose **New experiment**, and enter a name for the experiment.
2. For a DNP analysis, select the sample BAM, its reference FASTA and the DNP panel. Choose a saved reference, register your own FASTA, or download the UCSC hg19 or hg38 reference once. The same local references are available in IGV. [Choosing a reference genome](docs/GUI.md#choose-a-reference-genome)
3. Review the settings and results folder, then choose **Start experiment**. NewPat checks the configuration and runtime before starting the analysis.
4. Open **Experiments and results** to inspect the tables and plots. The run folder also contains `run-report.html`, `run.json` and `execution.log`.

For the same analysis from PowerShell, open the installed application folder and supply your own file paths:

```powershell
.\newpat.cmd dnp-call --bam "C:\Data\sample.bam" `
  --reference "C:\Data\genome.fa" --panel "C:\Data\dnp-panel.txt"
```

[Desktop guide](docs/GUI.md) · [Input formats and CLI examples](docs/USER_GUIDE.md) · [Reading run results](docs/RUNS.md) · [Documentation](https://github.com/GregorioDalia/nipat-desktop/blob/main/docs/README.md)

## Scientific methods

The calling and parentage modules use methods from [DNPcall](https://github.com/fravasini/DNPcall) and [NEWPAT](https://github.com/lpistacchia/NEWPAT). For the underlying methods, see [Pistacchia et al., *Bioinformatics Advances* (2025)](https://doi.org/10.1093/bioadv/vbaf209) on calling double-nucleotide polymorphisms and [D’Atanasio et al., *Genome Research* (2026)](https://doi.org/10.1101/gr.281702.125) on noninvasive prenatal paternity testing.

## License

NewPat is distributed under [GPL-3.0-or-later](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for the licenses and attributions of bundled components.
