param([string] $OutputPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $project 'NewPat.exe'
}
$target = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
. (Join-Path $PSScriptRoot 'build-compiler.ps1')
$compiler = Get-NewPatCSharpCompiler
# Native component identity changes only with its own implementation/resources.
# Application version is reported by the verified Python client, not this bridge.
$version = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'launcher-version.txt') -Raw -Encoding ASCII).Trim()
if ($version -cnotmatch '^\d+\.\d+\.\d+$') { throw 'Versione componente launcher non valida.' }
$numeric = [regex]::Match($version, '^\d+\.\d+\.\d+').Value + '.0'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('newpat-launcher-build-' + [Guid]::NewGuid().ToString('N'))
try {
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
    $assemblyInfo = Join-Path $temporary 'AssemblyInfo.cs'
    @"
using System.Reflection;
[assembly: AssemblyTitle("NewPat")]
[assembly: AssemblyProduct("NewPat")]
[assembly: AssemblyDescription("NewPat scientific workflows launcher")]
[assembly: AssemblyVersion("$numeric")]
[assembly: AssemblyFileVersion("$numeric")]
[assembly: AssemblyInformationalVersion("$version")]
"@ | Set-Content -LiteralPath $assemblyInfo -Encoding UTF8
    $source = Join-Path $PSScriptRoot 'NewPatLauncher.cs'
    $manifest = Join-Path $PSScriptRoot 'NewPatLauncher.manifest'
    $icon = Join-Path $project 'assets\branding\newpat-icon.ico'
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw 'Icona NewPat mancante.' }
    & $compiler /nologo /target:exe /platform:x64 /optimize+ /deterministic+ /debug- "/pathmap:$temporary=/_/generated,$project=/_/src" "/win32manifest:$manifest" "/win32icon:$icon" "/out:$target" $source $assemblyInfo
    if ($LASTEXITCODE -ne 0) { throw 'Compilazione di NewPat.exe fallita.' }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'NewPat.exe non e stato prodotto.' }
    Write-Host "Launcher NewPat $version compilato: $target"
} finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
