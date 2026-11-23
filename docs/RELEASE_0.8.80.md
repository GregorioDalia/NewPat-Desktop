# NIPAT Desktop 0.8.80 — stable text-menu and CLI release

Release 0.8.80 consolidated the five scientific modules and composed workflows before GUI development. Corrective maintenance could continue on the backend.

## Data and run integrity

SNPcall preserves contig names including `01`, `1` and `NA`. The callers check BAM dictionaries against the reference and requested markers. DNP summary validation compares the genotypes for every locus and sample with the individual tables.

The plan and guided menu agree on active branches, files and family roles. Results, reporting and recovery use the outcome recorded after the final input checks. A samtools failure during header reading or SNP preparation retains its exit code and log path.

## Client and installation

Concurrent preference saves merge independent changes and signal edits to the same field. Resource configuration and run-stop commands return a nonzero exit code for incomplete operations. Preparation checks have live logs, separate time limits, diagnostics and resume support. Scientific analyses and the interactive menu keep their existing duration behavior.

The Ubuntu updater launches its update component separately from package verification and checks the digest before invoking APT. Built-in help covers complete workflows and the update channel.

## Verification

Download the Windows `NIPAT-Setup.exe`, Ubuntu 24.04 DEB or macOS PKG for the host architecture. See the [installation guides](README.md#install-newpat), [Windows five-module test](WINDOWS_INSTALLATION_TEST.md) and [validation procedure](VALIDATION.md). Build reports and `desktop-acceptance.json` identify tests on the distributed packages. Historical results, deferred desktop tests and domain validation have separate records.
