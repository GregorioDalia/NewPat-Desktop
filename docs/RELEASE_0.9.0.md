# NIPAT 0.9.0 Preview

La 0.9.0 è una **prerelease per provare l'interfaccia grafica**. La versione
stabile rimane la **0.8.99**. La pubblicazione della preview non modifica
il canale degli aggiornamenti stabili.

## Applicazione desktop

- Finestra NIPAT con menu permanente, italiano e inglese, colori neutri e
  animazione DNA disattivabile nelle preferenze.
- Creazione di esperimenti: campioni, scelta indipendente DNP/SNP,
  analisi facoltative, parametri e riepilogo prima dell'esecuzione.
- Parametri con etichette descrittive, intervalli e passaggio di appartenenza;
  catalogo di costanti e formule impaginate matematicamente.
- Esecuzioni reali con stato, avanzamento e interruzione controllata.
- Archivio di esperimenti, importazione di cartelle precedenti, riuso della
  configurazione, riepiloghi, tabelle, PDF e copia dei risultati originali.
- IGV integrato per riferimenti, allineamenti e tracce locali indicizzati,
  senza avviare IGV Desktop. Le dipendenze JavaScript sono incluse.
- Impostazioni di esecuzione, risorse del motore, manutenzione e aggiornamenti
  accessibili dalla GUI. La CLI e il menu testuale restano disponibili.

Il motore scientifico e gli algoritmi R sono quelli della 0.8.99. La GUI
utilizza gli stessi piani, controlli degli input e moduli di esecuzione.

## Installazione della preview

Su Windows utilizzare **NIPAT-0.9.0-Testing-installazione.zip** dalla
[release v0.9.0](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.0):
estrarre il contenuto e aprire **INSTALLA-NIPAT-TESTING.cmd**. Il percorso
predefinito è separato dalla normale installazione desktop. In alternativa
è disponibile **NIPAT-0.9.0-Windows-completo.zip**.

Il setup EXE riutilizza il bootstrap della 0.8.99: aperto direttamente,
continua a selezionare la versione stabile. Il programma di installazione
testing indica esplicitamente i pacchetti 0.9.0 e ne verifica dimensione
e SHA-256. L'opzione avanzata `-UseSetup` sostituisce invece l'installazione
desktop esistente e richiede quindi una scelta esplicita.

Su macOS e Ubuntu utilizzare i pacchetti della release v0.9.0, non i link
`latest`. Questi pacchetti aggiornano l'installazione della piattaforma.

Il runtime WebView2 Microsoft viene predisposto automaticamente su Windows
se manca; questa preparazione richiede Internet. Dopo la preparazione del
motore e dei dati, analisi e visualizzazione IGV con file locali sono offline.

## Ambito delle prove

Le verifiche di pubblicazione comprendono test della GUI e del trasporto
locale, controlli dei pacchetti e avvio dell'interfaccia nei componenti
nativi. Le evidenze effettive di build e accettazione sono allegate alla
release. La qualifica scientifica del motore viene conservata secondo le
regole di riuso della 0.8.99.

La preview serve a verificare la nuova esperienza d'uso sui dati e sulle
postazioni di lavoro. Gli avvisi e le politiche di esecuzione di Windows
dipendono dalla singola postazione; non è introdotta una firma NIPAT.

La [guida GUI](GUI.md) descrive il percorso di utilizzo e i limiti attuali.
