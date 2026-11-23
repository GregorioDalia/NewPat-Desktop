# NewPat 0.9.7

This release brings the NewPat desktop interface to the stable channel and changes how DNPcall schedules pileup acquisition and divides work among R processes. Scientific dependencies and analysis parameter values match 0.9.5.

## DNP performance

For a single indexed BAM and acquisition settings covered by the measured profile, NewPat can process several chromosomes concurrently. It considers the chromosomes requested, reference memory requirements, the VM or container budget, and the user's process limit. Serial execution remains available.

The R scheduler avoids splitting work into many small blocks when the assigned memory supports larger ones. For jobs that can keep all workers busy on a smaller budget, it uses the finer partition from 0.9.5. Scientific window compatibility modes remain available.

The Windows development benchmark used one BAM of about 3.5 GB, the same 22 chromosomes and the same R execution plan throughout. With one, two and five samtools processes, median elapsed times for the complete DNP analysis were **4 min 13 s, 2 min 45 s and 1 min 50 s**, respectively. Both runs of every configuration produced identical pileups and scientific tables. These measurements describe the prototype on the test computer. Panel, input data and available resources affect performance.

## Installation and upgrades

- **Windows x64.** Run `NewPat-Setup.exe` for guided installation. To prepare the application inside an extracted directory, use `NewPat-0.9.7-Windows-completo.zip`. [Windows guide](WINDOWS_INSTALLER.md)
- **macOS 14 or later.** Choose the `arm64` package for Apple Silicon, including M1 and M3, or `x86_64` for Intel. [macOS guide](MACOS_INSTALLER.md)
- **Ubuntu 24.04 x86_64.** Install `newpat-desktop_0.9.7_amd64.deb`. [Ubuntu guide](LINUX_INSTALLER.md)

Users with a separate Windows 0.9.5 Testing installation can install the stable version with the setup program. Packages and checksums are on the [release page](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.7).
