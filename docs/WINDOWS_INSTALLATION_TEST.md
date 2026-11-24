# Test an installed Windows release

For a short desktop check in 0.9.10, choose **Environment and help → Open demo**, then review and start the experiment. The [Italian quick start](QUICKSTART_IT.md) gives the expected counts.

For a full installation check, the package includes a synthetic suite for the five current modules and their workflows. It creates its own inputs. Finish setup, open **Windows PowerShell as your regular user** and select the instructions for your installation.

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

The suite contains 54 runs (48 positive cases and 6 expected input rejections), 9 reproducibility comparisons and 7 initial/final checks. A complete passing environment reports **70 PASS, 0 FAIL, 0 BLOCKED, 0 INTERRUPTED**.

It verifies:

- Installed application, runtime, settings and resource identity.
- DNP, SNP, Contamination, prenatal CPI and postnatal CPI numerical outputs against independent expected values.
- Workflows from three BAMs, SNP pileup and tables, including compositions of the five modules.
- Sample IDs, family roles, parameters and artifacts actually produced.
- Equality of scientific tables in serial, automatic and two-worker execution.
- Invalid inputs rejected for the expected reason, and integrity of inputs, installation, preferences and test fixtures.

The suite creates its own inputs, runs and reports. A missing prerequisite, interrupted case or unrelated runtime failure cannot count as a pass. The report records the fixture provenance separately from the installed version. For execution speed on representative inputs, use the [performance guide](PERFORMANCE.md). For domain assessment, see the [validation record](VALIDATION.md).
