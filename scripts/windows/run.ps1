# No named PowerShell parameters: preserve all CLI flags, including --data-dir/--runs-dir.
# Keep the caller's working directory so Python resolves relative CLI paths there.
$nipatCliArguments = @($args)
$nipatGuiLaunch = $nipatCliArguments.Count -eq 1 -and $nipatCliArguments[0] -ceq 'gui'
. (Join-Path $PSScriptRoot "common.ps1")
try {
    $project = Get-NipatProject
    if (Test-Path -LiteralPath (Join-Path $project '.distribution\installer-manifest.json') -PathType Leaf) {
        . (Join-Path $project 'installer\windows\bootstrap-common.ps1')
        $statePath = Join-Path $project '.runtime\installer\state.json'
        if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
            throw 'Installazione da completare: aprire NewPat - Resume Setup dal menu Start.'
        }
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $manifest = Read-NipatInstallerManifest (Join-Path $project '.distribution\installer-manifest.json')
        if ($state.schema_version -ne 1 -or $state.phase -ne 'ready' -or
            $state.source_commit -ne $manifest.source_commit -or $state.runtime_image -ne $manifest.runtime_image) {
            throw 'Installazione non verificata per questa versione: aprire NewPat - Resume Setup dal menu Start.'
        }
        $configuration = Get-Content -LiteralPath (Join-Path $project '.runtime\backend.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-NipatRuntimeBinding $manifest $state $configuration
    }
    Set-NipatEnvironment $project
    $python = Get-NipatPython $project
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Python NewPat non disponibile. Per l'applicazione installata riaprire NewPat - Resume Setup dal menu Start; per il sorgente configurare WSL e avviare 1_SETUP.cmd."
    }
    if ($nipatCliArguments.Count -eq 0) { $nipatCliArguments = @("--help") }
    if ($nipatGuiLaunch) {
        # pythonw is the signed, console-free interpreter from the same verified
        # embedded Python archive. Keep CLI/smoke commands synchronous on python.
        $windowedPython = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
        $guiLauncher = Join-Path $PSScriptRoot 'gui-launch.py'
        if (-not (Test-Path -LiteralPath $windowedPython -PathType Leaf) -or
            -not (Test-Path -LiteralPath $guiLauncher -PathType Leaf)) {
            throw 'Avvio grafico incompleto. Riaprire la preparazione di NewPat.'
        }
        Start-Process -FilePath $windowedPython -ArgumentList ('"' + $guiLauncher + '"') -WorkingDirectory (Get-Location).Path | Out-Null
        exit 0
    }
    & $python -m newpat @nipatCliArguments
    exit $LASTEXITCODE
} catch {
    Write-Host ("ERRORE: " + $_.Exception.Message) -ForegroundColor Red
    if ($nipatGuiLaunch -and -not [Console]::IsOutputRedirected) {
        # The normal desktop shortcut deliberately has no terminal. Retain an
        # actionable error dialog if readiness checks fail before Python starts.
        try { (New-Object -ComObject WScript.Shell).Popup($_.Exception.Message, 0, 'NIPAT - avvio non riuscito', 16) | Out-Null } catch { }
    }
    exit 1
}
