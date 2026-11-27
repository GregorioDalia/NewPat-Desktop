# Mini-suite NewPat 0.9.99 per Mac Apple Silicon

1. Estrai lo ZIP scaricato. Se al suo interno trovi **NewPat-Mac-Final-Trial.zip**, estrai anche questo secondo archivio. Apri la cartella che contiene **Mini-Test-NewPat.command**.
2. Nel kit completo, chiudi NewPat e installa il file che termina in **-macos-arm64.pkg** presente nella stessa cartella. È l’installer associato a questa prova. Se hai ricevuto soltanto lo ZIP della mini-suite, usa la candidata 0.9.99 già installata sul Mac.
3. Fai doppio clic su **Mini-Test-NewPat.command**. Lascia il comando e il file Python nella cartella estratta. NewPat prepara il proprio runtime e avvia tre prove.
4. Il Terminale mostra l’esito e il percorso del report. In **Download**, apri la nuova cartella **NewPat-Mini-…** e invia **Esito-NewPat.html**, anche in caso di FAIL. Il report si apre offline.
5. Per il collaudo finale, dopo i tre PASS apri NewPat ed esegui un tuo esperimento dal risultato già noto, preferibilmente con più BAM. Indica se hai ottenuto il risultato atteso e quanto è durata l’analisi.

| Prova | Riferimento per il PASS |
| --- | --- |
| CPI prenatale da BAM materno e paterno | Tre loci, conteggi 96/4 e 50/50, frazione fetale 8% e CPI 8 |
| Sesso fetale da tabelle materne di calling | DNP autosomi + X e SNP del cromosoma Y, risultato M e corrispondenza delle quattro tabelle pubblicate |
| DNPcall e SNPcall su un BAM sintetico | 128.000 letture su quattro cromosomi, entrambe le tabelle uguali ai riferimenti della 0.9.10 |

La suite usa il parallelismo automatico e i parametri scientifici predefiniti della candidata. Ogni caso gira una sola volta. Il report riporta i secondi del comando e delle fasi disponibili, i processi previsti e il picco simultaneo osservato. Un picco di uno può essere coerente con le risorse del Mac e con la dimensione del lavoro. Il PASS riguarda i risultati scientifici verificati.

I dati delle prove e i log si trovano nella nuova cartella in Download.
