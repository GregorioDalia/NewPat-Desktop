# Fixed launcher bridge: all user arguments are decoded as data and splatted.
# This file is called by NewPat.exe; ordinary CLI/script launchers stay available.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    $encoded = [string]$env:NEWPAT_LAUNCH_ARGUMENTS
    $countText = [string]$env:NEWPAT_LAUNCH_ARGUMENT_COUNT
    Remove-Item Env:NEWPAT_LAUNCH_ARGUMENTS -ErrorAction SilentlyContinue
    Remove-Item Env:NEWPAT_LAUNCH_ARGUMENT_COUNT -ErrorAction SilentlyContinue
    $count = 0
    if (-not [int]::TryParse($countText, [ref]$count) -or $count -lt 1) {
        throw 'Avviare NewPat.exe dalla cartella completa del programma.'
    }
    $encodedArguments = $encoded.Split([char]10)
    if ($encodedArguments.Length -ne $count) {
        throw 'Gli argomenti di avvio non sono completi.'
    }
    $arguments = @()
    foreach ($value in $encodedArguments) {
        $arguments += [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($value))
    }
    $project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $runner = Join-Path $project 'scripts\windows\run.ps1'
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw 'Pacchetto NewPat incompleto: manca lo script di avvio.'
    }
    $global:LASTEXITCODE = 0
    & $runner @arguments
    exit $LASTEXITCODE
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
