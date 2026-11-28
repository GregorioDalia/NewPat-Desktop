# NewPat 0.9.99

Install 0.9.99 as a new application. First launch creates a NewPat workspace with fresh preferences, a local runtime and a new experiment archive. Keep older result folders if you need their contents. The installation does not discover or import them.

| System | Default workspace |
| --- | --- |
| Windows guided setup | `%LOCALAPPDATA%\NewPat-Desktop` |
| Windows complete ZIP | `NewPat` inside the extracted directory |
| macOS | `~/Library/Application Support/NewPat-Desktop` |
| Ubuntu | `$XDG_DATA_HOME/newpat-desktop` (defaults to `~/.local/share/newpat-desktop`) |

[Installation and requirements](DISTRIBUTION.md) · [Primo esperimento in italiano](QUICKSTART_IT.md)

## BAM pileup depth

New DNPcall and SNPcall experiments use a maximum depth of 2147483647 reads per position in each BAM. Both callers pass the equivalent `-d 0` to samtools 1.21. DNP results can change at high-coverage positions because version 0.9.10 used a default of 8000. SNPcall already used `-d 0`. Experiments can select an explicit limit, including 8000. Imported pileups retain the depth applied at creation.

When memory and CPU allow concurrent DNP chromosome tasks at high depth, NewPat checks the indexed target coverage for each BAM. A single acquisition process handles high or unknown coverage. The run records the selected worker count and the evidence used in `work/dnp-pileup.json`. The scientific depth setting applies in either case.

## Integrated changes

The desktop uses the same calling-table input for fetal sex, parentage and contamination. Add each file once, then choose the analyses and assign the samples and tables they require. For fetal sex, select the maternal cfDNA sample and either its combined autosomal/X DNP table or its two region-specific DNP tables, together with the SNP table for Y. The maternal BAM workflow is also available. [Desktop guide](GUI.md#set-up-an-experiment)

SNPcall processes input in blocks to reduce memory use on larger BAM experiments. Concurrent clients using the same runtime coordinate their CPU and memory allocations. The run report records the settings used, and the performance tools can measure timings on the user's own data. [Performance diagnostics](PERFORMANCE.md)

The desktop also includes fixes for experiment status and archive display. On macOS, startup checks detect a stale application mount in the owned Lima guest after replacing the app bundle. If the guest is idle, the launcher refreshes the mount and verifies the installed manifest.

On macOS, if the launch command exits with code 255 and NewPat confirms the VM stopped, the experiment is recorded as interrupted. A subsequent analysis checks and starts the managed VM through the usual launcher. NewPat retains available timestamped VM lifecycle events for diagnostic export with the default execution settings. Collecting these events does not require turning on performance measurements.

The Apple Silicon package includes a Linux ARM64 image. Both R and samtools run natively in a dedicated ARM64 Lima guest. The [Apple Silicon trial](MACOS_CANDIDATE_TEST.md) exercises the installed engine and compares synthetic outputs with the recorded reference. The [release roadmap](ROADMAP.md) describes the checks on the final packages.

## Source layout

The desktop client now lives under `src/newpat`, with screen code in `desktop/` and experiment planning and execution in `experiments/`. Shared scientific input preparation and engine helpers live in `src/newpat_scientific`. [Code guide](CODE_GUIDE.md)
