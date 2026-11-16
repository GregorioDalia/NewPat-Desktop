# NIPAT 0.9.1 Testing

La 0.9.1 è una **prerelease della GUI**, successiva alla 0.9.0. La versione
stabile rimane la **0.8.99**. I calcoli scientifici e gli script R restano
invariati; questa versione interviene sull'uso dell'applicazione.

## Miglioramenti

- Installazione Windows di testing con preparazione e avvio guidati,
  collegamenti riconoscibili e conservazione degli esperimenti della preview.
- Avvio ordinario della GUI senza una console separata, identità e icona NIPAT;
  le operazioni di installazione e manutenzione conservano i propri messaggi.
- Barra iniziale corretta, animazione DNA continua, fase corrente e tempo
  trascorso. La percentuale viene mostrata solo quando misurata dal motore.
- Verifica degli esperimenti rimasti in esecuzione dopo una chiusura anomala;
  comandi visibili per rieseguire o rimuovere dalla lista senza eliminare file.
- IGV con riconoscimento degli indici disponibili, controlli sui formati,
  messaggi comprensibili, selezione del cromosoma, coordinate sincronizzate,
  zoom e ritorno alla panoramica o alla vista precedente.
- Apertura dei BAM registrati da un esperimento e accesso alle regioni
  dalle tabelle che contengono coordinate utilizzabili.

## Installazione della preview

Scaricare **NIPAT-0.9.1-Testing-installazione.zip** dalla
[release v0.9.1](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.1).
Su Windows, prima di estrarlo, aprire **Proprietà** dello ZIP e, se presente,
selezionare **Annulla blocco**, quindi **Applica**. Estrarre tutto e aprire
**INSTALLA-NIPAT-TESTING.cmd**. Seguire le indicazioni di preparazione;
al termine viene aperta la GUI e sono disponibili i collegamenti NIPAT Testing.

Questa procedura rimuove l'indicazione di provenienza Internet dall'archivio
scelto, non disattiva Smart App Control o Defender. Le altre politiche della
postazione possono comunque impedire l'esecuzione di software non firmato.

Chiudere NIPAT prima di aggiornare. Il programma di testing riconosce la
precedente installazione di testing verificata e conserva le sue cartelle
di lavoro. La normale installazione stabile non viene selezionata
automaticamente come destinazione della preview.

Il **NIPAT-Setup.exe** riutilizzato dalla release stabile, se aperto direttamente,
continua a selezionare la stabile. Per questa preview usare l'archivio Testing
indicato sopra; non occorre cercare manualmente la cartella di installazione.
Il primo scaricamento e l'eventuale preparazione dei prerequisiti richiedono
Internet. Le analisi e IGV con i propri file restano locali.

Su macOS e Ubuntu usare i pacchetti della release v0.9.1, non i link `latest`.
Questi pacchetti aggiornano l'installazione della rispettiva piattaforma.

## Verifiche e limiti

Le verifiche automatiche coprono regressioni del client, pacchetti, avvio
nativo della GUI, gestione degli stati e riconoscimento dei file IGV.
I rapporti effettivi della build e la decisione di accettazione sono allegati
alla release. Le prove con dati sintetici non sostituiscono il collaudo sui
campioni reali e sulla postazione Windows dell'utilizzatore.

La rimozione dalla lista non cancella risultati o file originali. La riesecuzione
crea un nuovo esperimento; non riprende una precedente elaborazione interrotta.
IGV verifica tipi e coerenze di base dei file, ma non può certificare da solo
la correttezza biologica del riferimento o l'aggiornamento di ogni indice.

La [guida GUI](GUI.md) descrive i comandi e il percorso di utilizzo.
