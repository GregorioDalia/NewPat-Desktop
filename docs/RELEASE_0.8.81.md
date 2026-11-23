# NIPAT Desktop 0.8.81 — Windows preparation fix

This release addressed a change to the Windows native component in [0.8.80](RELEASE_0.8.80.md) associated with a Smart App Control block before environment preparation began. It retained the 0.8.80 features and scientific fixes.

## Preparation

The `NipatActivityNative.dll` component that coordinates installation and analysis returned to the 0.8.70 source. Deterministic compilation allows the binary to be compared with the one distributed in 0.8.70. The packaged Python now handles preparation-check timeouts and stops the associated processes. Live logs, error codes and recovery remain available. Automated Windows checks cover descendants, timeouts, diagnostics, resume and preservation of unrelated processes.

The package lacked a publisher signature. Windows Server builds verify the client and packaging. Smart App Control acceptance requires a test on the target device.

## Installation and verification

Run `NIPAT-Setup.exe` from the release using the existing installation directories. It can update files and resume incomplete 0.8.80 preparation while preserving data and results. Wait for the NIPAT Desktop ready message before the [five-module verification](WINDOWS_INSTALLATION_TEST.md).

Ubuntu 24.04 DEBs and PKGs for Intel and Apple Silicon Macs are also available. See the [installation guides](README.md#install-newpat). The release's `desktop-acceptance.json` and accompanying reports identify the actual build, packages and checks, deferred desktop tests and domain validation. Historical device results belong to the versions tested.
