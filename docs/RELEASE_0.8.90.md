# NIPAT Desktop 0.8.90 — backend fixes

Four fixes followed the [0.8.81 review](RELEASE_0.8.81.md) and installed-client testing. The release retained all five scientific modules, text menu, CLI and the Windows preparation fix from 0.8.81. The R sources and formulas remained unchanged.

- **CPI family roles.** Direct execution now rejects a sample used as a mother in one pair and a father in another. With empty prefixes, `A:B,B:C` fails before copying or engine startup. Reuse within one role is supported. Distinct prefixes can identify distinct files.
- **SNP cutoff preferences.** Configuration accepts and preserves `label=path` maps with SNP coordinate panels as well as DNP panels, using the analysis-time validation.
- **Parallel pileup regression.** The out-of-order completion test synchronizes its processes explicitly. It verifies canonical output order, worker limits, outcomes and temporary-file cleanup without timing assumptions about `sleep`.
- **Corrupt BAM test.** `reject-corrupt-bam` accepts both the `samtools view` diagnostic containing `header from` and the older `mpileup` diagnostic containing `header of`. The engine already rejected the BAM. The test had misclassified that rejection as FAIL. It still requires a negative outcome and excludes timeouts or infrastructure failures.

## Installation and evidence

Choose the Windows `NIPAT-Setup.exe`, Ubuntu 24.04 DEB or architecture-specific Mac PKG. The [installation guides](README.md#install-newpat) and [five-module test](WINDOWS_INSTALLATION_TEST.md) cover updates, verification and timing. `desktop-acceptance.json` and the attached reports identify qualified packages and tests. Physical-device evidence remains specific to the version tested. Deferred desktop tests and domain validation are recorded separately. This backend served as a base for GUI development and subsequent corrective work.
