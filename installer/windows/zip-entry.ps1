param([ValidateSet('launch', 'resume')][string] $Mode = 'launch')
. (Join-Path $PSScriptRoot 'zip-common.ps1')
try {
    $root = Get-NipatZipRoot
    if ($Mode -ceq 'resume') {
        if (-not (Test-Path -LiteralPath (Join-Path $root 'pending.json'))) {
            Write-Host 'Nessuna preparazione ZIP in attesa. Aprire 2_AVVIA.cmd nella cartella NIPAT.'
            Read-Host 'Premere Invio per chiudere' | Out-Null
            exit 0
        }
        $pointer = Read-NipatZipPointer $root 'pending.json'
        $worker = Join-Path $pointer.app_dir 'installer\windows\install-zip.ps1'
        $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        & $powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $worker -Resume
        $code = $LASTEXITCODE
        Read-Host 'Premere Invio per chiudere' | Out-Null
        exit $code
    }
    $pointer = Read-NipatZipPointer $root
    & (Join-Path $pointer.app_dir 'scripts\windows\run.ps1') gui
    exit $LASTEXITCODE
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Aprire 1_COMPLETA_PREPARAZIONE.cmd nella cartella NIPAT oppure eseguire nuovamente 1_INSTALLA.cmd dal pacchetto estratto.'
    Read-Host 'Premere Invio per chiudere' | Out-Null
    exit 1
}
