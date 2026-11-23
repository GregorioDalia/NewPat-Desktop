# NIPAT Desktop 0.8.70

The [installation guides](README.md#install-newpat) cover the Windows `NIPAT-Setup.exe`, Ubuntu 24.04 DEB and architecture-specific macOS PKGs.

## Inputs and results

- DNPcall and SNPcall preserve contig and read names as text. Contigs `01` and `1` remain distinct in Contamination, prenatal CPI and postnatal CPIN joins.
- Callers flag conflicting pileup REF bases. In BAM mode they validate marker windows against the indexed reference. DNP retains uncovered loci with zero counts and missing genotypes. SNPcall rejects repeated QNAMEs at one usable position because the pileup cannot distinguish the mates.
- Prenatal CPI computes the combined index directly in log10 space. If a product underflows or overflows, the logarithm remains available while raw CPI may be 0 or infinite. CPI and CPIN reject totals inconsistent with read counts. Contamination computes the REF ratio from observed counts.
- Output checks cover alleles in DNP tables and CPI curves for every pair and panel.

## Installation and performance

Windows setup and the acceptance test obtain their version from the build. Updates recognize the restart-required exit code. On Ubuntu, the restored package's hooks clear maintenance state after a completed dpkg rollback.

DNPcall indexes pileups with explicit types and detects duplicate BAMs in one pass. SNP batches persist state at transitions. The [technical audit](AUDIT_0.8.70.md) gives the 0.8.60 Windows real-input baseline for end-to-end measurement, reviewed cases and outstanding priorities. GitHub can start scientific tests earlier and queues publications authorized by an acceptance record.

The [Windows verification suite](WINDOWS_INSTALLATION_TEST.md) exercises the five modules with synthetic data and stores reports locally. For representative inputs, follow the [scientific and technical validation procedure](VALIDATION.md).
