# Technical audit of 0.8.60

**13 November 2026.** The audit reviewed Windows runtime preparation and diagnostics, payload verification, updates and restarts, installed acceptance tests, CI selection, evidence reuse and publication. Python static checks covered the client, runtime, engine, scripts and release procedures. Manual inspection concentrated on the changed paths and result contracts.

## Findings and corrections

| Priority | Finding | Correction |
| --- | --- | --- |
| High | Embedded Python uses `._pth`. A CPIN verifier could not import an adjacent helper, causing the 0.8.50 setup to fail its self-test. | Include the script directory on the import path. Run every distributed verifier with the actual embedded interpreter. Successful self-test remains mandatory. |
| High | The PowerShell transcript alone could lose native process errors. | Capture stdout, stderr and exit status separately, in UTF-8, with logs available from setup. The targeted repair applies to the original 0.8.50. |
| Medium | The acceptance driver passed analysis-only options to `doctor`, failing before the scientific tests started. | Apply the options only to analysis runs. Test the real parser, validation and `settings`; retain the actual error message in the report. |
| Medium | A restart fixture monitored a short-lived process without retaining its handle and could skip verification. Push CI passed and PR CI failed on identical sources. | Synchronize fixture and observer, retain the handle before release, then require identity and exit-code checks. |
| Medium | The installed test was hard-coded to 0.8.50. | Supply an expected identity and include a local launcher. Reject version, commit, state and image mismatches. Verify hashes of the four files and fixtures first. |
| Medium | An immediate Ctrl+C at the BAM prompt could hang in CPython's POSIX terminal `input()`. This occurred twice in ten attempts. | Use interruptible terminal input and preserve Windows and custom-reader behavior. Repeat the same PTY test without delays or reduced checks. |
| Medium | The Windows manifest check expected the previous release. | Bind the gate to 0.8.60 and reject mismatched manifests. The repair fixtures explicitly retain the 0.8.50 contract. |

## Scientific reliability and maintenance

The five R models and frozen references are unchanged. Reusing CI evidence for an installer build requires the same Git tree and immutable image, successful CI, all expected reports and matching hashes. Tests cover missing, altered and mismatched evidence. Each built package is also checked.

Routine static checks look for syntax errors and undefined names. Additional Ruff `F` and `B` findings were reviewed in context, including unused imports, synchronous callbacks in loops and `zip` after length checks. CI records branch coverage. Installed tests compare expected values and tables, distinguish expected rejections from environment failures and interruptions, and retain source and image identities, commands, timings and hashes. Workflows reuse previously produced counts.

## Evidence and limitations

On 13 November the user's Windows PC completed the official **0.8.50 with the CPIN repair** with **70 passes**, zero failed, blocked or interrupted cases, in 657.169 s. Repository validators rechecked 48 positive analyses, six expected rejections, nine comparisons and 320 unchanged input hashes. Private data and personal paths were excluded from the repository.

For the **0.8.60 candidate**, the local suite passed **1,272 tests**, with 32 excluded for platform or prerequisite reasons. All **311 CI/publication tests** passed, alongside Ruff, links across 69 Markdown documents and 20 consecutive Ctrl+C regression runs. Combined statement and branch coverage was **86.8%**. Exact-image scientific checks and native Windows and macOS runner tests have distinct coverage.

The [0.8.60 acceptance record](../.github/release-acceptance/v0.8.60.json) ties installer qualification to its package hashes. Windows setup fixtures cover installation logic, failures and updates. Full WSL installation on Windows 10/11 and a complete Lima run on a physical Mac require separate evidence. Domain validation on representative data and deferred desktop scenarios remained open.
