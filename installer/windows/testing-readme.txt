NIPAT 0.9 - versione sperimentale con interfaccia grafica

Estrarre tutti i file di questo ZIP in una cartella e aprire
INSTALLA-NIPAT-TESTING.cmd. Il programma scarica il pacchetto completo
della versione indicata in testing-release.json e ne controlla SHA-256
e dimensione prima dell'installazione.

La destinazione predefinita e una cartella distinta:
%LOCALAPPDATA%\NIPAT-Testing\<versione>\pacchetto\NIPAT
La versione stabile gia installata rimane disponibile. Questa versione
sperimentale non riceve aggiornamenti dal canale stabile.

Al termine aprire 2_AVVIA.cmd nella cartella NIPAT per la finestra grafica.
L'installazione richiede una connessione Internet. L'applicazione comprende
IGV; non richiede di scaricare o aprire IGV Desktop o un browser esterno.

Solo per sostituire esplicitamente l'installazione desktop esistente:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\install-testing.ps1 -UseSetup
Questa opzione usa il medesimo NIPAT-Setup.exe della versione stabile con
il payload sperimentale verificato; non e un'installazione affiancata.
Aprire direttamente NIPAT-Setup.exe, senza questo script, seleziona invece
la versione stabile pubblicata.
