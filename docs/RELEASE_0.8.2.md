# NIPAT Desktop 0.8.2

Release 0.8.2 provided the CLI and automatic workflows on Windows 10/11, Intel and Apple Silicon Macs, and Ubuntu 24.04 x86_64. The distributed R algorithms remained unchanged.

## Results and resource management

Files, tables and plots use the original sample names. Internal identifiers link workflow steps unambiguously. Each run adds a sample map and a readable report alongside structured metadata and logs.

Resource settings distinguish the host, VM and container. WSL2 and Lima changes have a preview, backup and confirmation step. Saved changes that still require a restart appear explicitly. When the container state is available, persistent diagnostics distinguish an out-of-memory exit from an exit of unknown cause. Simulated failures test the reporting path. They do not measure memory use on real data.

## Installation and evidence

The Windows installer, Ubuntu package and both Mac packages share the same commit and scientific archive. Choose the package for the host from [GitHub Releases](https://github.com/GregorioDalia/nipat-desktop/releases). Windows and Ubuntu retain the desktop installation identity. **NIPAT Desktop** on Mac uses a dedicated Lima environment. Experimental installations remain separate. The [distribution guide](DISTRIBUZIONE.md) covers platform-specific procedures. The packages lacked a recognized NIPAT signature and the Mac packages lacked Apple notarization.

Release records identify package hashes, the commit and executed checks. CI covers contracts, naming, resources, numerical regressions, installers and common archive provenance. Hosted Mac builds verify clients and packaging. Testing Lima and Rosetta requires an environment with virtualization support. The reports identify deferred desktop tests.

- [User guide](GUIDA_UTILIZZO.md)
- [Results and provenance](ESECUZIONI.md)
- [Resources and memory](RISORSE.md)
- [CI and distribution](CI_CD.md)
- [Validation record](VALIDAZIONE.md)
