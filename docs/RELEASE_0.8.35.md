# NIPAT Desktop 0.8.35

This release corrected an intermittent coordination error in parallel SNP batches. The model remained SNPcall 2.0. On November 11, 2026, the latest upstream SNPcall revision was [NEWPAT commit ce59f4be](https://github.com/lpistacchia/NEWPAT/tree/ce59f4beeeec710b1b42d425cb87d7aad729f71d/SNPcall), identical to the frozen 0.8.30 reference. The [0.8.30 notes](RELEASE_0.8.30.md) describe the 17 columns, genotypes, indels and multi-sample summaries.

## Worker coordination

The coordinator reads final state after each process exits. It retries transient file-visibility failures up to 20 times with at most 0.95 seconds of total waiting. Progress uses its own events. A wrong sample ID or unreadable final state is an explicit error. Diagnostics keep the error type and message.

Batch shutdown preserves the first failure even if another process's status becomes unreadable. It stops running processes and descendants and skips queued samples. The Mac cleanup path handles a permission error when signaling a process group that already exited.

## Regression tests

CI and installer qualification exercise state replacement during execution, delayed visibility, missing or malformed state, wrong identity, cancellation and preservation of the primary error. Scientific-image tests cover 2, 3 and 5 BAM paths in serial mode and with two workers, plus repeated automatic three-sample runs. The five-path test reuses three synthetic fixtures and measures batch behavior.

Checks compare independently expected counts, likelihoods and genotypes, exact tables, aggregate genotypes, sample identities, final states and the shared worker budget. They also cover all four modules, reference comparisons, presentation, clients and four installers. Linux tests with simulated read failures provide regression evidence. Reproduction on Windows/WSL and tests on the target computer require separate evidence.

## Installation and local test

Use **Check for updates** or choose a package from the [0.8.35 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.35). Finish active runs, verify version **0.8.35** and run `nipat self-test`. For a parallelism comparison, use the same three or more BAMs and panel for separately named serial, two-worker and automatic runs. Compare SNP tables and aggregate genotypes, repeat automatic runs to check for intermittent failures, and retain `run.json`, `workflow-state.json`, results and logs. Update scripts that explicitly require version 0.8.30 before using them.

Installation follows the 0.8.30 procedure. The Windows setup lacked a recognized NIPAT Authenticode signature or Smart App Control qualification. Mac packages lacked notarization. See the [Windows](INSTALLATORE_WINDOWS.md), [macOS](INSTALLATORE_MACOS.md) and [Ubuntu](INSTALLATORE_LINUX.md) guides.
