# Technical audit of 0.8.20

**9 November 2026.** The review started from `3cf998bfc49e06ca5025865ef1cd58326dab9e3b`, which contains 0.8.14. It covered the Python client and orchestration, four R modules and their helpers, packaging for Windows, Linux and macOS, CI and publication. The findings reflect source inspection and targeted testing.

## Findings and changes

| Area | Finding and response |
| --- | --- |
| Windows preparation | `activity-lock.ps1` used `Add-Type -TypeDefinition` to compile C# during installation and maintenance. This behavior predated 0.8.14. The build now produces the component, inventories it and verifies it before loading. A blocked file still has to be identified from Windows events. |
| Binary identity | Recompiling unchanged Windows sources produced different binary identities. Repeated deterministic Roslyn builds are compared by SHA-256. Whole-installer reproducibility has a broader scope. |
| Windows trust | No recognized NIPAT Authenticode signature was available. Signature inventory and read-only diagnostics record the delivered files; Smart App Control compatibility remained unqualified. |
| Setup coverage | Embedded-Python payload verification did not exercise Inno installation or removal. A compiled Inno fixture exercises these operations, updating and file retention with a simulated bootstrap. |
| macOS launcher | Ctrl+C could cause the supervisor to terminate the client and release its lock before cancellation finished. The supervisor waits for the client. The regression uses a terminal, process group and independent lock check. |
| Linux updates | Ctrl+C in the final updater could terminate a restarted client. The launcher replaces that process. APT and preparation retain their interruption handling. |
| DNP input | First position 1 produced a negative BED start for the preceding base. Validation rejects 1 before creating output and accepts the boundary at 2. |
| SNP input tests | A nonexistent backend prevented malformed-panel tests from reaching validation. Tests use a valid backend, check specific error messages and include a valid control panel. |
| Scientific concurrency | The verifier previously compared claimed budgets and overlap. It now checks overall observed concurrency, coordinators and every task outcome. Negative cases exercise oversubscription and task failure. |
| Multi-BAM publication checks | Required evidence covers 2, 3 and 6 BAMs, serial, automatic and capped modes, repeatability, and the relevant helpers. |
| Inno compiler | The official download size and SHA-256 are pinned alongside the existing distributor signature check. |

## Execution and release controls

Runs keep separate folders and mount inputs read-only. The runner passes individual process arguments, verifies container ownership and immutable identity before cleanup, and checks paths, links, archives and install ownership during update and removal. Update manifests connect version, tag, commit, file sizes and hashes.

The review found no demonstrated regression requiring a formula change. The DNP queue shares a budget across samples and preserves assembly order. The candidate keeps the R sources and the frozen 0.8.5 reference. The exact packaged image reruns the differential tests on tables, unrounded values and rendered PDFs.

CI pins actions to commits, limits permissions and requires successful checks before explicit installer builds. The two publication steps verify the same build. Vulnerability monitoring remains a separate source of evidence: a component–CVE association alone does not establish exploitability.

## Windows Smart App Control

The candidate `e04ff883fc6417748174d2a7c3b49cadad989308` and published commit `b3ee5598d86e75884ead424e6c2ad4cbd137d2a1` had identical Windows installer sources, entry points and build workflow. Reusing the 0.8.14 version affected update detection. The audit could not attribute the Smart App Control block to that choice. Rebuilding produces new setup bytes with their own reputation.

Windows evaluates component trust and signatures. Identify the particular file in the Code Integrity log. A precompiled DLL can be identified and signed during the build. On this revision the project had no recognized distributor signing identity for the applicable scripts, installer and uninstaller. No self-signed certificate, policy change or exclusion was introduced.

Microsoft references consulted on 9 November 2026: [Smart App Control FAQ](https://support.microsoft.com/it-it/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions), [application signing](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control), and [testing and event logs](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/test-your-app-with-smart-app-control).

## Scope of the evidence

Python and PowerShell tests covered exercised contracts and process behavior. The Server 2022 Inno fixture covered its installation operations. A full Windows 10/11 setup with WSL and Smart App Control required a separate device test. The Authenticode report records the hashes and signature state observed at the time of testing. Native Mac checks covered the package and architecture; Lima startup and Gatekeeper decisions on the target machine remained separate. R tests in the exact image established agreement with 0.8.5 for the cases exercised and checked observed worker budgets.

Build reports and release acceptance identify the commit, image, checksums, test results and unexecuted scenarios. The 42 runs for the 0.8.14 candidate remain attributed to that candidate. Real BAM and FASTA inputs were unavailable for a fresh end-to-end measurement in the review environment.
