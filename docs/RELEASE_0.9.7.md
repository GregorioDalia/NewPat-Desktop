# NewPat 0.9.7

La 0.9.7 porta l’interfaccia desktop NewPat sul canale stabile e aggiorna la pianificazione di DNPcall. I cambiamenti riguardano l’acquisizione del pileup e la suddivisione del lavoro R. Le dipendenze scientifiche e i parametri dell’analisi mantengono le versioni e i valori della 0.9.5.

## Prestazioni DNP

Con un singolo BAM indicizzato e impostazioni di acquisizione compatibili con il profilo misurato, NewPat può elaborare più cromosomi in contemporanea. L’assegnazione considera i cromosomi richiesti, la memoria del riferimento, il budget della macchina virtuale o del container e il limite di processi scelto dall’utente. La modalità seriale rimane disponibile.

Nel calcolo R, il pianificatore evita di produrre molti blocchi piccoli quando la memoria assegnata consente blocchi più grandi. Per i lavori che possono impegnare tutti i processi anche con un budget ridotto, usa la ripartizione più fine della 0.9.5. Le modalità di compatibilità per le finestre scientifiche rimangono attive.

Il confronto di sviluppo su Windows ha usato un BAM di circa 3,5 GB, gli stessi 22 cromosomi e lo stesso piano R. Con uno, due e cinque processi samtools, i tempi mediani del DNP completo sono stati rispettivamente **4 min 13 s, 2 min 45 s e 1 min 50 s**. Le due ripetizioni per configurazione hanno prodotto pileup e tabelle scientifiche identici. Queste misure descrivono il prototipo sul computer di prova. Le prestazioni dipendono dal pannello, dai dati e dalle risorse disponibili.

## Installare o aggiornare

- **Windows x64**. Avviare `NewPat-Setup.exe` per l’installazione guidata. Chi preferisce preparare l’applicazione nella cartella estratta può scegliere `NewPat-0.9.7-Windows-completo.zip`. [Guida Windows](INSTALLATORE_WINDOWS.md)
- **macOS 14 o successivo**. Scegliere il pacchetto `arm64` per Apple Silicon, incluso M1 o M3, oppure `x86_64` per Intel. [Guida macOS](INSTALLATORE_MACOS.md)
- **Ubuntu 24.04 x86_64**. Installare `newpat-desktop_0.9.7_amd64.deb`. [Guida Ubuntu](INSTALLATORE_LINUX.md)

Chi usa un’installazione separata della 0.9.5 Testing su Windows può installare la stabile con il setup. I pacchetti e i checksum della release sono disponibili nella [pagina di download](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.7).
