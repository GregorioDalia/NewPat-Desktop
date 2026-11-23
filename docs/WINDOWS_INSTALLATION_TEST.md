# Test an installed Windows release

The Windows package includes a synthetic test suite for all five scientific modules and their workflows. Complete guided setup first. The suite uses the installation's embedded Python and verified WSL runtime.

Open **Windows PowerShell as your regular user** and run:

```powershell
$app = (Get-ItemProperty -LiteralPath 'HKCU:\Software\NIPAT\desktop' -Name app_dir).app_dir
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'scripts\windows\test-installed.ps1')
```

The PowerShell execution policy option applies only to the process used for the test. The terminal prints the new session directory under `%LOCALAPPDATA%\NIPAT-Desktop\collaudi`. Wait for completion. The suite opens the HTML report. To share the results, use **`report.zip` from that session** and review it for local paths or device information before sharing publicly.

## Expected results

The suite contains 54 runs (48 positive cases and 6 expected input rejections), 9 reproducibility comparisons and 7 initial/final checks. A complete passing environment reports **70 PASS, 0 FAIL, 0 BLOCKED, 0 INTERRUPTED**.

It verifies:

- Installed application, runtime, settings and resource identity.
- DNP, SNP, Contamination, prenatal CPI and postnatal CPIN numerical outputs against independent expected values.
- Workflows from three BAMs, SNP pileup and tables, including compositions of the five modules.
- Sample IDs, family roles, parameters and artifacts actually produced.
- Equality of scientific tables in serial, automatic and two-worker execution.
- Invalid inputs rejected for the expected reason, and integrity of inputs, installation, preferences and test fixtures.

The suite creates its own inputs, runs and reports. A missing prerequisite, interrupted case or unrelated runtime failure cannot count as a pass. The report records the fixture provenance separately from the installed version. For execution speed on representative inputs, use the [performance guide](PERFORMANCE.md). For domain assessment, see the [validation record](VALIDATION.md).
