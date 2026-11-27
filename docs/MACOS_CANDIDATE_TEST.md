# Apple Silicon candidate trial

1. Let current analyses finish and quit NewPat. Leave the existing installation, Lima VM and results in place.
2. Install the Apple Silicon `.pkg` in this folder. Open `Run-Mac-Comparison.command` before opening NewPat for the first time. It prepares the app through its installed launcher and records the upgrade. If NewPat already prepared the new runtime, it can still measure performance.
3. Wait for the path to `comparison.json` in Terminal. Share that file. It is in a new `NewPat-Mac-Comparison-…` folder in Downloads. Logs and synthetic runs are alongside it if a check fails.

The test uses the same six synthetic input files, sample IDs, automatic concurrency and input hashing as the 0.9.10 Mac timing run. It runs DNPcall and SNPcall together with 1, 2 and 4 BAMs, once to warm up and three more times per size. Only the test pins DNP depth to 8000 to reproduce the previous settings. The application default is 2147483647.

The original Apple M1 run used battery power and a four-CPU guest exposing 3905 MiB. Keep the same power source if practical, leave the existing VM allocation in place and close other workloads. The report shows absolute times for every run. It calculates percentage differences only when the recorded hardware, macOS, guest capacity and power conditions match. Preparation time is outside the timing comparison. Each result table must match its 0.9.10 checksum.

## Measured on Apple M1

Candidate `f106f3e` completed all 12 runs on a MacBook Air M1 with 8 GiB of RAM, on battery, with the same four CPUs and 3905 MiB available to the guest as in the [0.9.10 baseline](validation/0.9.10-apple-silicon-timing.json). The guest and R ran on ARM64 with Rosetta disabled. All 56 DNP and SNP table checksums, including the warm-up runs, matched the baseline.

| Synthetic BAMs | 0.9.10 median | 0.9.99 median | Time reduction | Concurrent samtools processes in DNP | Concurrent R workers in DNP |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 31.273 s | 23.880 s | 23.6% | 2 | 2 |
| 2 | 59.872 s | 40.479 s | 32.4% | 1 | 2 |
| 4 | 106.122 s | 67.241 s | 36.6% | 1 | 2 |

The times are medians of three measured experiments per size after warm-up. The process counts are observed peaks for each phase. This Mac had already prepared the 0.9.99 runtime before the benchmark. Direct upgrade from 0.9.10 and completion time on representative multi-BAM inputs require separate tests.
