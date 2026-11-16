param([ValidateSet('auto', 'launch', 'resume')][string] $Mode = 'launch')
. (Join-Path $PSScriptRoot 'zip-common.ps1')
try {
    $root = Get-NipatZipRoot
    if ($Mode -ceq 'auto' -and (Test-Path -LiteralPath (Join-Path $root 'pending.json'))) {
        $pending = Read-NipatZipPointer $root 'pending.json'
        $worker = Join-Path $pending.app_dir 'installer\windows\install-zip.ps1'
        $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        # Setup progress needs a visible window; subsequent normal launches do
        # not. Resume from the installed copy even after the ZIP was removed.
        $process = Start-Process -FilePath $powershell -ArgumentList ('-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $worker + '" -Resume') -Wait -PassThru
        if ($process.ExitCode -eq 3010) {
            (New-Object -ComObject WScript.Shell).Popup('Riavvia Windows, poi apri nuovamente NIPAT per completare la preparazione.', 0, 'NIPAT - riavvio richiesto', 64) | Out-Null
            exit 3010
        }
        if ($process.ExitCode -ne 0) { throw 'Preparazione non completata. Riapri NIPAT per riprovare; i dettagli sono in .runtime\installer\setup.log nella cartella della versione.' }
    }
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
    if ($Mode -ceq 'auto') {
        (New-Object -ComObject WScript.Shell).Popup($_.Exception.Message, 0, 'NIPAT - avvio non riuscito', 16) | Out-Null
        exit 1
    }
    Write-Host 'Aprire 1_COMPLETA_PREPARAZIONE.cmd nella cartella NIPAT oppure eseguire nuovamente 1_INSTALLA.cmd dal pacchetto estratto.'
    Read-Host 'Premere Invio per chiudere' | Out-Null
    exit 1
}
