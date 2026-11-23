# NIPAT Desktop 0.7.2

DNPcall, SNPcall, Contamination and CPI are available through the guided text menu and reproducible commands. Automatic workflows connect compatible analyses and retain each step's inputs, parameters, status, logs and results. A self-contained image includes the R scientific core.

## Packages and usage

| Platform | Package | Environment |
| --- | --- | --- |
| Windows 11 x64 | `NIPAT-Setup.exe` | Bundled Python, dedicated WSL2 distribution and NIPAT-managed Docker Engine. |
| Ubuntu 24.04 LTS x86_64 | `nipat-desktop_0.7.2_amd64.deb` | Python 3.12, local Docker Engine and Compose v2 accessible to the user. |

On Windows, double-click the single EXE using your normal account. Select directories and let setup prepare the engine. Use the **NIPAT Desktop** shortcut for later launches. WSL2 activation may require elevation, internet access and a restart. The Windows package has no NIPAT digital signature. Workstation policies can restrict installation or launch.

On Ubuntu install the `.deb` with APT. It resolves dependencies from configured repositories. Docker access requires separate authorization. Use **NIPAT Desktop** or `nipat` to open the menu. See the [user guide](USER_GUIDE.md) and [distribution requirements](DISTRIBUTION.md).

## Validation and reliability

A shared Python layer checks inputs before R and verifies outputs of individual and composed analyses. Normalization creates working copies of SNP and DNP panels. Messages distinguish format errors, data constraints and quality observations for review. The [input contract](INPUT_VALIDATION.md) details coverage.

The menu includes failed runs. Cancellation attempts to stop computation before returning to the main menu. Logs and partial results remain available. See [run provenance and incomplete runs](RUNS.md). Select `--input-hashes full` for full SHA-256. The default `auto` hashes files up to 16 MiB and records metadata for larger files. Separate container CPU, memory and process limits leave the R parameters unchanged. `runs inspect` displays incomplete runs. `runs stop` verifies container identity and asks for confirmation.

On Windows, **Guida e informazioni → Installazione e spazio** displays verified environments and caches, supports selective cleanup of older components and can resume preparation of the installed version. It protects the active environment, the most recent previous environment, data and results. It does not roll back the app. WSL has an identity independent of the application, allowing published archives to be reused when sources and resolved dependencies match.

## Distribution scope

The release supports research and domain evaluation. Regressions verify numerical expectations on synthetic cases. Separate evidence identifies installer checks and real-sample tests. [CI/CD](CI_CD.md) describes coverage. Acceptance identifies the actual packages and evidence. Published records include component inventories, synthetic verification reports and archives, and the Ubuntu upgrade from 0.7.1. GitHub release immutability protects published tags and assets. Historical manual observations remain attributed to the earlier build. A manual Windows installation of 0.7.2 was not claimed. The R sources remained unchanged. Python adapters and other changes underwent separate verification. Use the [validation sheet](VALIDATION.md) for additional reproducible observations.

This version retained internal DNPcall parallelism. It provided no GUI, automatic run resumption or parallel execution of different plan steps. The main interface was in Italian. The catalog offered English and `runs` diagnostics offered both languages. Technical status `succeeded` describes execution. It does not establish scientific validity for a sample or use case.
