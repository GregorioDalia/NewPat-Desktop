param(
    [Parameter(Mandatory = $true)][string] $Package,
    [Parameter(Mandatory = $true)][string] $ManifestPath,
    [Parameter(Mandatory = $true)][string] $OutputPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$temporary = Join-Path $env:RUNNER_TEMP ('NIPAT ZIP & ' + [char]0x00e8 + '-' + [Guid]::NewGuid().ToString('N'))
try {
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $hash = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash.ToLowerInvariant()
    & python (Join-Path $PSScriptRoot 'zip_package.py') extract-update --package $Package --destination $temporary --version $manifest.version --source $manifest.source_commit --sha256 $hash
    if ($LASTEXITCODE -ne 0) { throw 'ZIP verification/extraction failed.' }
    $app = Join-Path $temporary 'app'
    & powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'installer\windows\install-zip.ps1') -BundleDirectory $temporary -VerifyOnly
    if ($LASTEXITCODE -ne 0) { throw 'ZIP double-click entry validation failed.' }
    . (Join-Path $app 'scripts\windows\common.ps1')
    $python = Install-NipatPython $app
    & $python -m nipat --version
    if ($LASTEXITCODE -ne 0) { throw 'ZIP embedded Python client failed.' }
    $record = [ordered]@{
        schema_version = 1; version = $manifest.version; source_commit = $manifest.source_commit
        package_sha256 = $hash; scope = 'staged-zip-payload'
        complete_payload_verified = $true; embedded_python_executed = $true
        smart_app_control = 'not-performed'; live_wsl_installation = 'not-performed'
    }
    [IO.File]::WriteAllText($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath), ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Write-Host 'PASS: complete ZIP extraction, setup preflight and embedded client. Live WSL/SAC acceptance remains separate.'
} finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force } }
