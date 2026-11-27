# Mini-suite NewPat 0.9.99 per Mac Apple Silicon

1. Installa la candidata 0.9.99 destinata alla prova, se necessario. È sufficiente questa versione.
2. Estrai lo ZIP e fai doppio clic su **Mini-Test-NewPat.command** dal Finder. Tieni il comando e il file Python nella stessa cartella. NewPat prepara il proprio runtime e avvia tre prove. Puoi lasciare chiusa la finestra dell’app.
3. Alla fine il Terminale mostra l’esito e il percorso. In **Download**, apri la nuova cartella **NewPat-Mini-…** e invia **Esito-NewPat.html**, anche in caso di FAIL. Il file si apre anche offline.

| Prova | Riferimento per il PASS |
| --- | --- |
| CPI prenatale da BAM materno e paterno | Tre loci, conteggi 96/4 e 50/50, frazione fetale 8% e CPI 8 |
| Sesso fetale da tabelle materne di calling | DNP autosomi + X e SNP del cromosoma Y, risultato M e corrispondenza delle quattro tabelle pubblicate |
| DNPcall e SNPcall su un BAM sintetico | 128.000 letture su quattro cromosomi, entrambe le tabelle uguali ai riferimenti della 0.9.10 |

La suite usa il parallelismo automatico e i parametri scientifici predefiniti della candidata. Ogni caso gira una sola volta. Il report riporta i secondi del comando e delle fasi disponibili, i processi previsti e il picco simultaneo osservato. Un picco di uno può essere coerente con le risorse del Mac e con la dimensione del lavoro. Il PASS riguarda i risultati scientifici verificati. Per vedere come si comporta NewPat con un carico rappresentativo, resta la prova con un esperimento di laboratorio scelto da Letizia.

I dati delle prove e i log si trovano nella nuova cartella in Download.
