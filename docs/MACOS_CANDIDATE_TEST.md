# Apple Silicon candidate trial

1. Let current analyses finish and quit NewPat. Leave the existing installation, Lima VM and results in place.
2. Install the Apple Silicon `.pkg` in this folder. Open `Run-Mac-Comparison.command` before opening NewPat for the first time. It prepares the app through its installed launcher and records the upgrade. If NewPat already prepared the new runtime, it can still measure performance.
3. Wait for the path to `comparison.json` in Terminal. Share that file. It is in a new `NewPat-Mac-Comparison-…` folder in Downloads. Logs and synthetic runs are alongside it if a check fails.

The test uses the same six synthetic input files, sample IDs, automatic concurrency and input hashing as the 0.9.10 Mac timing run. It runs DNPcall and SNPcall together with 1, 2 and 4 BAMs, once to warm up and three more times per size. Only the test pins DNP depth to 8000 to reproduce the previous settings. The application default is 2147483647.

The original Apple M1 run used battery power and a four-CPU guest exposing 3905 MiB. Keep the same power source if practical, leave the existing VM allocation in place and close other workloads. The report shows absolute times for every run. It calculates percentage differences only when the recorded hardware, macOS, guest capacity and power conditions match. Preparation time is outside the timing comparison. Each result table must match its 0.9.10 checksum.
