NewPat - Windows ZIP completo

1. Scegliere una cartella definitiva su un disco locale fisso ed estrarre
   completamente lo ZIP. Lo ZIP Source code di GitHub non e un installer.
2. Fare doppio clic su 1_INSTALLA.cmd, senza eseguirlo come amministratore.
3. La preparazione crea la sottocartella NIPAT nella cartella estratta e apre
   automaticamente l'app. Per i prossimi avvii aprire NIPAT\NewPat.lnk.
   Il collegamento usa l'icona NewPat e non tiene una console aperta.

Python 3.12.10, filesystem WSL e motore scientifico sono inclusi.
Non occorre installare Python. Windows potrebbe dover scaricare/aggiornare
WSL da Microsoft e richiedere autorizzazione amministrativa o riavvio.
Dopo un riavvio aprire lo stesso NIPAT\NewPat.lnk: completa la preparazione
e apre l'app. I vecchi script restano disponibili per la diagnostica.
La ripresa usa la copia installata e gli archivi gia presenti nella cache.

Conservare la cartella NIPAT: contiene applicazione, WSL, cache, dati e risultati.
Non spostarla dopo la preparazione: WSL e registrato su questo computer e
l'installazione conserva i percorsi originali. Non e una cartella portatile
pronta per un altro PC. I risultati sono in NIPAT\runs e i dati in NIPAT\data.
Dopo la preparazione riuscita si possono eliminare lo ZIP scaricato e le
cartelle app/assets estratte inizialmente, conservando NIPAT e il suo contenuto.
Il canale EXE resta separato; i suoi dati non vengono trasferiti.
Gli aggiornamenti dall'app usano lo ZIP completo e conservano questa cartella.

SE WINDOWS BLOCCA 1_INSTALLA.cmd

La provenienza Internet puo bloccare anche gli script. Nessun automatismo
qui disabilita Smart App Control o Defender. La firma dell'interprete Python
non firma NewPat. Il doppio clic non e garantito con tutte le policy Windows.

Prima verificare il SHA-256 dello ZIP confrontandolo con la riga del suo nome
nel file SHA256SUMS della stessa release ufficiale GitHub. Se coincide, fare
clic destro sullo ZIP, Proprieta, Sblocca, Applica. Estrarre nuovamente in una
cartella nuova e riprovare 1_INSTALLA.cmd. Non usare una vecchia estrazione.

Se occorre la procedura manuale gia verificata su un PC Windows, aprire
Windows PowerShell 5.1 normalmente (NON come amministratore) e incollare
il blocco seguente. Richiede il percorso esatto dello ZIP e il suo SHA-256
ufficiale. Lo sblocco riguarda solo quello ZIP e la nuova cartella estratta.
Non inserirlo in un file .ps1 scaricato: anche quel file potrebbe essere bloccato.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    $zip = (Read-Host 'Percorso completo dello ZIP ufficiale').Trim('"')
    $atteso = (Read-Host 'SHA-256 da SHA256SUMS della stessa release').Trim()
    if ($atteso -notmatch '^[a-fA-F0-9]{64}$') { throw 'SHA-256 non valido.' }
    $zip = (Resolve-Path -LiteralPath $zip).ProviderPath
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ine $atteso) {
        throw 'Hash diverso dalla release ufficiale. Operazione interrotta.'
    }
    Unblock-File -LiteralPath $zip
    $cartella = Join-Path (Split-Path -Parent $zip) (
        'NIPAT-verificato-' + [Guid]::NewGuid().ToString('N')
    )
    Expand-Archive -LiteralPath $zip -DestinationPath $cartella
    Get-ChildItem -LiteralPath $cartella -Recurse -File -Force |
        ForEach-Object { Unblock-File -LiteralPath $_.FullName }
    $script = Join-Path $cartella 'app\installer\windows\install-zip.ps1'
    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    & $powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $script -BundleDirectory $cartella
    $codice = $LASTEXITCODE
    Write-Host "Codice finale: $codice"
    Write-Host "Cartella NIPAT: $cartella\NIPAT"
    if ($codice -eq 0) { Write-Host 'Preparazione riuscita: aprire NIPAT\NewPat.lnk.' }
    elseif ($codice -eq 3010) { Write-Host 'Riavviare Windows, poi aprire NIPAT\NewPat.lnk.' }
    else { throw 'Preparazione non completata. Conservare il messaggio e setup.log.' }
}

Questa procedura rimuove la provenienza Internet; non aggiunge una firma e
non annulla un eventuale blocco Code Integrity. In caso di ulteriore blocco,
conservare il messaggio esatto e i log, senza disabilitare le protezioni Windows.
