# Historical verification of NIPAT Desktop 0.8.50 on Windows

These instructions apply to the **0.8.50 installer at commit `b54ef493ba7f0539a8786b97874fe946b2d26393`**. For an installed NewPat release use the [current Windows test](COLLAUDO_INSTALLAZIONE.md).

The historical suite uses the installed Python, WSL distribution, scientific image and public CLI. Each case creates a new result directory. The harness is separate from the application. The report records both commit identities, fixture hashes and the runtime image as resolved on the device.

## Coverage

| Area | Evidence |
| --- | --- |
| DNPcall | Synthetic SAM counts, genotype and heterozygote likelihood, sample identity, summaries and plots. |
| SNPcall | All 17 expected fields and agreement between BAM/pileup inputs and multisample processing. |
| Contamination | Both marker types, denominator, include/exclude-zero modes, mean, standard deviation, selected sites and plots. |
| Prenatal CPI | Both marker types, fetal fraction, index products, full curve, minimum support, mismatch, missing metadata and no informative sites. |
| Postnatal CPIN | Both marker types, both site selection modes, compatible transmissions, mismatches, per-site indices, full curves and exclusion reasons. |
| Workflows | DNP preset, SNP batch and a five-module plan with sample roles, step references, artifacts and numerical caller results. A BAM-to-CPI chain has its own expected positive results. |
| Repeatability and rejection | Scientific table equality across serial, auto and two-worker modes. Invalid inputs must fail for their expected reason. |

There are 54 executions, comprising 48 expected successes and 6 expected input rejections, plus checks of prerequisites, integrity and cross-run agreement. The 16 analytical downstream tests and 18 batch tests use artificial counts and frequencies with directly calculable answers. Examples include CPI products of 20, 4 and 2, a median fetal fraction of 6%, and mean contamination of 0.025 with zeros or 0.05 without. SNP and DNP mismatch constants are checked separately.

The three BAMs in the complete plan test the links between modules. They do not constitute a valid biological trio. Dedicated analytical cases verify positive CPIN outcomes. Separate independent expectations distinguish correctness on these examples from agreement between two executions.

## Run the historical suite

Use `scripts/windows/test-installed-0850.ps1` in a non-elevated PowerShell session. Supply the full Git commit of the **test harness** with `-SourceCommit`. The wrapper pins the test manifest's checksum and verifies all four downloaded files. The target installation must be the identified 0.8.50 package in the `ready` state. It may include the local CPIN import fix below.

Each invocation creates a directory under `%LOCALAPPDATA%\NIPAT-Desktop\collaudi`. The suite generates BAMs from synthetic SAM inputs with installed tools. The terminal displays progress and the report is retained even when a check fails.

<a id="correzione-locale-dellautotest-cpin"></a>

## Historical CPIN self-test repair

The original 0.8.50 installer can fail CPIN self-test with `ModuleNotFoundError: No module named 'verify_contamination_update'`. The [0.8.50 repair script](../scripts/windows/repair-0850-self-test.ps1) verifies version and hashes, backs up the affected verifier, records a separate receipt, applies the known import fix and repeats preparation.

Run it from PowerShell as your regular user, passing the full Git commit from which you downloaded the script as `-HotfixSourceCommit`. Successful preparation writes the `ready` state. The receipt identifies **0.8.50 with a local repair**. Reinstalling the original 0.8.50 EXE restores the original verifier, including the import failure.

## Report files

- `report.html` gives a readable summary and case detail.
- `report.json` records individual results, commands, timing and provenance.
- `report.zip` contains the shareable report and logs.
- `runs` and `logs` hold individual outputs and diagnostics.

Read the recorded output assertions as well as the process result. The report distinguishes passed, failed and blocked checks and identifies omitted files. When reporting a failure, use the ZIP path shown by the terminal. These tests cover the listed synthetic workflows. Physical installation, interactive behavior and real-sample validation require separate observations.
