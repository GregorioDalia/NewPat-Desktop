param([Parameter(Mandatory = $true)][string] $LauncherPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('nipat-native-build-' + [Guid]::NewGuid().ToString('N'))
try {
    $dll = Join-Path $temporary 'NipatActivityNative.dll'
    & (Join-Path $PSScriptRoot 'build-native.ps1') -OutputPath $dll
    $original = Join-Path $PSScriptRoot 'NipatActivityNative.dll'
    $activitySha256 = (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant() -cne $activitySha256) {
        throw 'Activity helper builds from identical sources differ.'
    }
    Write-Host "Windows activity helper SHA-256: $activitySha256"
    if ($activitySha256 -cne '1640de90891d859b89d5b796ea2587496a7dfc9ca3b0c2f07a863276c4b87013') {
        throw 'Activity helper differs from the unchanged 0.8.81 component.'
    }
    $launcher = Join-Path $temporary 'NIPAT.exe'
    & (Join-Path $PSScriptRoot 'build-launcher.ps1') -OutputPath $launcher
    if ((Get-FileHash -LiteralPath $launcher).Hash -cne (Get-FileHash -LiteralPath $LauncherPath).Hash) {
        throw 'Launcher builds from identical sources differ.'
    }
    if ((Get-FileHash -LiteralPath $launcher).Hash.ToLowerInvariant() -cne 'd73e19071731fd917998c03afdd370dfc40e6232d719370099523571c12251cc') {
        throw 'Launcher differs from its unchanged 0.8.81 component identity.'
    }
    $wslFirst = Join-Path $temporary 'first\EnableWsl.exe'
    $wslSecond = Join-Path $temporary 'second\EnableWsl.exe'
    & (Join-Path $PSScriptRoot 'build-wsl-helper.ps1') -OutputPath $wslFirst
    & (Join-Path $PSScriptRoot 'build-wsl-helper.ps1') -OutputPath $wslSecond
    if ((Get-FileHash -LiteralPath $wslFirst).Hash -cne (Get-FileHash -LiteralPath $wslSecond).Hash) {
        throw 'WSL prerequisite helper builds from identical sources differ.'
    }
    Write-Host 'PASS: repeated activity helper, WSL helper and launcher builds have identical SHA-256 values.'
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
