# Test an installed Windows release

For a short desktop check in 0.9.10, choose **Environment and help → Open demo**, then review and start the experiment. The [Italian quick start](QUICKSTART_IT.md) gives the expected counts.

For a full installation check, the package includes a synthetic suite for the six current modules and their workflows. It creates its own inputs. Finish setup, open **Windows PowerShell as your regular user** and select the instructions for your installation.

## Complete ZIP

Open the extracted folder containing `1_INSTALL.cmd`. Inside it, open the installed `NIPAT` folder containing `NewPat.lnk` and `current.json`. Click the File Explorer address bar, type `powershell` and press Enter. Identify the installed build.

```powershell
$current = Get-Content -LiteralPath '.\current.json' -Raw -ErrorAction Stop | ConvertFrom-Json
$current | Select-Object version, source_commit, app_dir
```

If the test requires a specific build, compare its version and commit with those displayed. Several review builds can share a version number. From the same PowerShell window, start the installed suite.

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $current.app_dir 'scripts\windows\test-installed.ps1')
```

## Guided EXE

The guided installation records its active application directory in the registry. Use this command when you installed with the setup EXE.

```powershell
$app = (Get-ItemProperty -LiteralPath 'HKCU:\Software\NIPAT\desktop' -Name app_dir).app_dir
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'scripts\windows\test-installed.ps1')
```

## Test report

The PowerShell execution policy option applies only to the process used for the test. The terminal prints the new session directory under `%LOCALAPPDATA%\NIPAT-Desktop\collaudi`. Wait for completion. The suite opens the HTML report. To share the results, use **`report.zip` from that session** and review it for local paths or device information before sharing publicly.

## Expected results

The suite selects the cases supported by the installed client. Both configurations below include fetal sex, the revised prenatal CPI model, six expected input rejections, nine reproducibility comparisons and seven setup and integrity checks.

| Installation | Scheduled runs | Expected passing checks in the report |
| --- | ---: | ---: |
| Stable 0.9.10 with separate autosomal DNP, X DNP and Y SNP tables | 68 | 84 |
| Build that also accepts a single DNP table for autosomes and X | 70 | 86 |

A complete pass has zero failed, blocked or interrupted checks. Earlier builds with fetal sex retain the 66-run suite, and five-module installations retain the 64-run suite.

It verifies:

- Installed application, runtime, settings and resource identity.
- DNP, SNP, Contamination, prenatal CPI and postnatal CPI numerical outputs against independent expected values.
- Fetal sex on the two published maternal cfDNA examples. The suite runs the three-table input for both samples. When the installed client accepts combined DNP input, it repeats each case with autosomal and X counts in one table and the original Y table. Each run compares the summary and all three site tables byte for byte with the published results.
- Prenatal read-count, percentage-only and combined filters, including empty curves. Postnatal scalar CPI and per-site reasons under genotype selection and trio coverage filters.
- Workflows from three BAMs, SNP pileup and tables, including a combined plan with all six modules.
- Sample IDs, family roles, parameters and artifacts actually produced.
- Equality of scientific tables in serial, automatic and two-worker execution.
- Invalid inputs rejected for the expected reason, and integrity of inputs, installation, preferences and test fixtures.

The suite creates its own inputs, runs and reports. A missing prerequisite, interrupted case or unrelated runtime failure cannot count as a pass. The report records the fixture provenance separately from the installed version. For execution speed on representative inputs, use the [performance guide](PERFORMANCE.md). For domain assessment, see the [validation record](VALIDATION.md).
