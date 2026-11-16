NIPAT 0.9 - versione sperimentale con interfaccia grafica

1. Estrarre tutti i file di questo ZIP in una cartella.
2. Aprire INSTALLA-NIPAT-TESTING.cmd, senza eseguirlo come amministratore.
3. Attendere: NIPAT si apre automaticamente quando la preparazione termina.

Per i prossimi avvii usare NIPAT Testing sul Desktop o nel menu Start.
Si puo anche riaprire lo stesso INSTALLA-NIPAT-TESTING.cmd: riconosce
l'installazione e apre l'app, senza ripetere il download.
Se Windows richiede un riavvio, dopo il riavvio usare lo stesso collegamento
NIPAT Testing: completa la preparazione e apre automaticamente l'app.

Il programma scarica il pacchetto della versione indicata in testing-release.json
e ne controlla SHA-256 e dimensione prima dell'installazione. Le nuove
installazioni sono in %LOCALAPPDATA%\NIPAT-Testing\NIPAT.
Se trova la precedente 0.9.0 Testing nella sua cartella predefinita, aggiorna
quella stessa installazione conservando esperimenti, dati e preferenze.
La versione stabile gia installata rimane disponibile e non viene modificata.
Conservare la cartella installata: contiene anche dati, risultati e runtime.

L'installazione richiede una connessione Internet. L'applicazione comprende
IGV; non richiede di scaricare o aprire IGV Desktop o un browser esterno.

SE WINDOWS BLOCCA LO SCRIPT

Prima di estrarre, confrontare il SHA-256 dello ZIP con la riga del suo nome
in SHA256SUMS della stessa release ufficiale GitHub. Se coincide, fare clic
destro sullo ZIP, Proprieta, Sblocca, Applica. Estrarre nuovamente in una
cartella nuova e aprire INSTALLA-NIPAT-TESTING.cmd.
Lo sblocco rimuove la provenienza Internet dal file verificato; non disabilita
Smart App Control o Defender e non equivale a una firma digitale. Lo script
non puo sbloccare se stesso prima che Windows lo autorizzi a partire.
Se il blocco resta, conservare il messaggio esatto senza disattivare le protezioni.

Solo per sostituire esplicitamente l'installazione desktop esistente:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\install-testing.ps1 -UseSetup
Questa opzione usa il medesimo NIPAT-Setup.exe della versione stabile con
il payload sperimentale verificato; non e un'installazione affiancata.
Aprire direttamente NIPAT-Setup.exe, senza questo script, seleziona invece
la versione stabile pubblicata.
