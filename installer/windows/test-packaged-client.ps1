param(
    [Parameter(Mandatory = $true)][string]$StageDirectory,
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$WorkDirectory,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$stage = (Resolve-Path -LiteralPath $StageDirectory).Path
$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
$work = [IO.Path]::GetFullPath($WorkDirectory)
$output = [IO.Path]::GetFullPath($OutputPath)
if (Test-Path -LiteralPath $work) {
    throw "La cartella di verifica deve essere nuova: $work"
}
$sourceApp = Join-Path $stage 'app'
$pythonArchive = Join-Path $sourceApp '.distribution\python-3.12.10-embed-amd64.zip'
if (-not (Test-Path -LiteralPath $pythonArchive -PathType Leaf)) {
    throw 'Python incorporato assente: la verifica non scarica componenti sostitutivi.'
}
if (Test-Path -LiteralPath $output) {
    throw "Il resoconto esiste gia: $output"
}

# Exercise the actual stable downloader with the exact pinned interpreter and
# the independently distributed payload. This is not an installed-Windows/SAC test.
New-Item -ItemType Directory -Path $work | Out-Null
$manifest = Get-Content -LiteralPath (Join-Path $sourceApp '.distribution\installer-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$payload = Join-Path (Split-Path -Parent $installer) ('NIPAT-' + $manifest.version + '-Windows-payload.zip')
$payloadHash = (Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash.ToLowerInvariant()
$payloadSize = (Get-Item -LiteralPath $payload).Length
$extracted = Join-Path $work 'downloaded payload'
$bootstrapPython = Join-Path $stage 'bootstrap\python\python.exe'
$downloader = Join-Path $stage 'bootstrap\bootstrap_download.py'
& $bootstrapPython -I $downloader --package $payload --destination $extracted `
    --version $manifest.version --source $manifest.source_commit --sha256 $payloadHash --size $payloadSize `
    --error-file (Join-Path $work 'bootstrap-error.txt') --report-file (Join-Path $work 'bootstrap-result.ini')
if ($LASTEXITCODE -ne 0) { throw 'The production bootstrap did not verify/extract the release payload.' }
$inventoryPath = Join-Path $sourceApp '.distribution\application-files.json'
$extractedInventory = Join-Path $extracted 'app\.distribution\application-files.json'
if ((Get-FileHash -LiteralPath $inventoryPath -Algorithm SHA256).Hash -cne
    (Get-FileHash -LiteralPath $extractedInventory -Algorithm SHA256).Hash) {
    throw 'Extracted payload differs from the application reviewed before compilation.'
}
$app = Join-Path $work 'app'
Copy-Item -LiteralPath (Join-Path $extracted 'app') -Destination $app -Recurse
. (Join-Path $app 'scripts\windows\common.ps1')
$python = Install-NipatPython $app
# Exercise the production setup supervisor with the exact embedded interpreter
# and relocated payload. Host Python tests cannot establish this dependency path.
. (Join-Path $app 'installer\windows\bootstrap-common.ps1')
$checkLogs = Join-Path $work 'setup checks'
Invoke-NipatSetupCheck $python @('-c', 'print("embedded setup check")') $checkLogs 'doctor' -TimeoutSeconds 10
if (([IO.File]::ReadAllText((Join-Path $checkLogs 'doctor.stdout.log'))).Trim() -cne 'embedded setup check') {
    throw 'Il controllo incorporato non ha conservato il suo output.'
}
foreach ($case in @(
    @{ Code = 7; Script = 'raise SystemExit(7)'; Limit = 10 },
    @{ Code = 124; Script = 'import time; time.sleep(30)'; Limit = 2 }
)) {
    $failed = $false
    try {
        Invoke-NipatSetupCheck $python @('-c', $case.Script) $checkLogs 'self-test' -TimeoutSeconds $case.Limit
    } catch {
        $failed = $_.Exception.Message.Contains(('codice ' + $case.Code))
    }
    $exitPath = Join-Path $checkLogs 'self-test.exit-code.txt'
    if (-not $failed -or ([IO.File]::ReadAllText($exitPath)).Trim() -cne [string]$case.Code) {
        throw "Il controllo incorporato non ha restituito il codice atteso $($case.Code)."
    }
}
Write-Host 'PASS: embedded Python setup supervision: success, failure and timeout.'
& $python -B -X utf8 (Join-Path $app 'scripts\verify_windows_payload.py') `
    --app-dir $app --work-dir $work --installer $installer --output $output
if ($LASTEXITCODE -ne 0) {
    throw "Verifica del client incorporato fallita (codice $LASTEXITCODE). Diagnosi: $work"
}
if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw 'La verifica non ha prodotto il resoconto atteso.'
}
$payloadCheck = [ordered]@{
    schema_version = 1; version = $manifest.version; source_commit = $manifest.source_commit
    package_sha256 = $payloadHash; scope = 'staged-bootstrap-payload'
    complete_payload_verified = $true; embedded_python_executed = $true
    production_downloader_executed = $true; wsl_execution = $false; smart_app_control = 'not-performed'
}
$payloadReport = Join-Path (Split-Path -Parent $output) 'windows-payload-check.json'
[IO.File]::WriteAllText($payloadReport, ($payloadCheck | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
Write-Host 'Client Windows incorporato verificato: catalogo, menu e pianificazione dei workflow.'
Write-Host 'Questa prova non esegue Inno Setup, WSL, Docker o i calcoli scientifici.'
