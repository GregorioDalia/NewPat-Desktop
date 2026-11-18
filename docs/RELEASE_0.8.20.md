# NIPAT Desktop 0.8.20

This release revised Windows packaging and installer tests and strengthened scientific concurrency checks. It retained the four analyses, the 0.8.14 multi-BAM DNP queue, the scientific formulas and the frozen 0.8.5 reference.

## Corrections

- The Windows build compiles the component that coordinates installation, updates and removal. Preparation verifies the inventoried component before loading it, replacing the earlier compilation of a temporary DLL on the user's computer. Repeat builds test deterministic output for the listed native binaries. The report also records their hashes and Authenticode status.
- Tests compile a fixture from the Inno definition and exercise copying, updating, removal and preservation of user files. The fixture substitutes the WSL bootstrap and desktop prerequisites. The distributed setup retains these checks.
- The Mac launcher passes Ctrl+C to the client and holds the installation lock even when a cancellation returns to the menu. The Linux updater hands control directly to the launcher on restart.
- DNP rejects a first coordinate of 1 before writing output because its preceding window would produce a negative BED interval.
- Publication requires DNP comparisons on 2, 3 and 6 BAMs, helper tests and evidence of actual task overlap, outcomes and process ceilings. See the [0.8.20 audit](AUDIT_0.8.20.md).

## Windows security evidence

The release lacked a recognized NIPAT Authenticode signature. Removing temporary compilation reduced device-generated components. Smart App Control acceptance remained unverified and requires separate evidence on Windows 11 with the protection enabled. The signing status of each inspected file remains visible.

Reusing 0.8.14 for two builds had prevented the updater from distinguishing them. The available evidence did not connect that version number to the Windows block. The higher 0.8.20 number is visible to both earlier builds. Published packages remain immutable. The [Windows security guide](INSTALLATORE_WINDOWS.md#windows-security-and-browser-messages) explains how to identify the blocked component.

## Installation and scope

Choose a package from the [0.8.20 release](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.8.20).

| System | Package |
| --- | --- |
| Windows 10 22H2 x64 / Windows 11 x64 | `NIPAT-Setup.exe` |
| macOS 14 or later, Apple Silicon | `NIPAT-0.8.20-macos-arm64.pkg` |
| macOS 14 or later, Intel | `NIPAT-0.8.20-macos-x86_64.pkg` |
| Ubuntu 24.04 LTS x86_64 | `nipat-desktop_0.8.20_amd64.deb` |

Finish active analyses before updating. The setup preserves data, preferences and results of recognized installations. Earlier candidates labeled 0.8.14 can use **Check for updates**.

Windows Server 2022 checks do not exercise a complete Windows 10/11 WSL installation or qualify Smart App Control. Mac packages lacked notarization. Native package checks, end-device Lima tests and scientific domain validation are separate. Real-data measurements from earlier candidates remain attributed to those candidates.
