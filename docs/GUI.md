# Usare NIPAT 0.9.1 Testing

La preview aggiunge una finestra desktop al motore della 0.8.99. Non è
necessario aprire un browser né installare IGV Desktop. Scaricare i pacchetti
dalla [release 0.9.1](https://github.com/GregorioDalia/nipat-desktop/releases/tag/v0.9.1)
seguendo le [note di installazione](RELEASE_0.9.1.md#installazione-della-preview).

## Creare un esperimento

1. Aprire **Nuova analisi**, assegnare un nome all'esperimento e scegliere
   **Aggiungi campioni**. È possibile partire da BAM, pileup SNP, tabelle
   compatibili precedenti o una combinazione supportata di questi input.
2. Scegliere **DNP**, **SNP** o entrambi. Per BAM aggiungere riferimento e
   pannelli appropriati; per input già elaborati indicare i file richiesti
   dal ramo scelto.
3. Selezionare le analisi desiderate: contaminazione, CPI prenatale e CPIN
   postnatale sono scelte indipendenti. Per CPI e CPIN assegnare i campioni
   ai ruoli delle coppie e dei trii e indicare le frequenze di popolazione.
4. Controllare i parametri del passaggio pertinente. Ogni campo espone una
   descrizione, i limiti e il valore predefinito; l'esecuzione può essere
   seriale o con parallelismo automatico e limiti espliciti.
5. Verificare il riepilogo, convalidare il piano e avviare l'analisi.

**Attività** mostra lo stato e l'avanzamento. L'animazione non sostituisce
una percentuale misurata: quando il motore non la fornisce viene mostrato
il passaggio in corso. L'interruzione richiede l'arresto dei processi del
run prima di considerare conclusa l'attività.

L'animazione a doppia elica continua anche durante i controlli iniziali.
Sono indicati la fase attuale e il tempo trascorso; l'eventuale percentuale
si riferisce alla fase, non a una stima dell'intera analisi.

## Aprire risultati ed esperimenti precedenti

**Esperimenti** raccoglie le esecuzioni e consente di cercarle per nome,
stato o tipo di marcatori. I risultati recenti sono raggiungibili anche
dalla pagina iniziale. Per un esperimento conservato altrove, selezionare
l'azione di apertura della cartella: i dati vengono registrati nell'archivio
senza essere copiati o modificati.

Aprire un esperimento per consultare riepiloghi, risultati dei moduli,
tabelle dettagliate, grafici PDF e file originali. È possibile esportare
un singolo file o l'intera cartella in ZIP e riutilizzare una configurazione
per un nuovo esperimento.

**Riesegui** riapre la configurazione precedente per una nuova analisi:
non riprende un calcolo da un punto intermedio. **Rimuovi dalla lista**
nasconde l'esperimento dopo una conferma, conservando risultati e input.
Per mostrarlo nuovamente è possibile importare la sua cartella.

Dopo una chiusura anomala NIPAT verifica se un'esecuzione è ancora attiva.
Se non è attiva e non risulta finalizzata, appare come interrotta. Se il
runtime non è verificabile, lo stato resta da verificare: un singolo modulo
completato non basta a dichiarare concluso l'esperimento. La rimozione dalla
lista è bloccata quando l'attività potrebbe essere ancora in corso.

I valori mancanti sono distinti da zero. L'indice CPI e il suo logaritmo
sono presentati con la scala appropriata; le celle delle tabelle conservano
il valore originale. Le anteprime paginate non sostituiscono i file completi
esportabili. Il completamento tecnico del run non costituisce da solo una
validazione scientifica dei risultati.

## Esplorare i dati con IGV

Aprire **IGV**, scegliere il FASTA locale e aggiungere i BAM come tracce.
Se gli indici corrispondenti si trovano accanto ai file, NIPAT li riconosce
automaticamente quando si apre il visualizzatore. In caso contrario,
selezionarli nei campi dedicati:

| File | Contenuto | Indice corrispondente |
| --- | --- | --- |
| `.fa` o `.fasta` | Genoma di riferimento | `.fai` dello stesso FASTA |
| `.bam` | Allineamenti del campione | `.bam.bai` oppure `.bai` dello stesso BAM |

Gli indici mancanti non vengono generati dal visualizzatore. Per FASTA
compresso BGZF serve anche il file `.gzi` corrispondente accanto al FASTA.
Gli altri formati indicizzati richiedono il proprio indice.

Una volta aperto IGV, scegliere un **Cromosoma** dall'elenco dei nomi
effettivamente presenti nel riferimento. Per una regione precisa usare
`cromosoma:inizio-fine`, per esempio `1:100000-110000`: è un esempio di
sintassi, non una regione necessariamente coperta dal proprio campione.
I controlli per ingrandire, ridurre, tornare alla panoramica e tornare alla
vista precedente sono sincronizzati con il visualizzatore. In un riferimento
con cromosomi `1`–`22`, `X`, `Y`, il nome `23` non indica automaticamente `X`.

La vista dell'intero genoma non mostra i singoli allineamenti BAM. Ingrandire
una regione coperta dal campione, preferibilmente partendo da **Visualizza in IGV**
in una tabella di risultati con coordinate e input BAM/FASTA disponibili.
Le letture possono mancare in una regione anche quando il file è valido.
La sessione esportata conserva la configurazione locale dei file e della vista.

Riferimento, nomi dei contig e coordinate devono essere coerenti con gli
allineamenti. La preview utilizza file locali: non carica automaticamente
genomi, annotazioni o dati da servizi remoti. I grandi file sono letti
per intervalli, senza trasferire l'intero BAM all'interfaccia.

## Preferenze e manutenzione

La lingua è selezionabile dalla barra superiore. Le preferenze includono
riduzione delle animazioni, cartelle, impostazioni predefinite e limiti
delle risorse. Il catalogo scientifico raccoglie parametri, costanti e
formule. Le funzioni di ambiente e manutenzione riutilizzano quelle della
CLI, comprese le conferme per le operazioni che modificano il runtime.

La CLI resta disponibile con `nipat gui`, `nipat wizard` e i singoli comandi
scientifici. Nelle distribuzioni Windows i comandi si richiamano tramite
`nipat.cmd`; il normale avvio `2_AVVIA.cmd` apre la GUI.

## Implementazione e limiti della preview

L'applicazione usa WebView2 su Windows, WKWebView su macOS e WebKitGTK su
Ubuntu. L'interfaccia e igv.js sono incluse nel pacchetto. Un servizio
riservato al processo su loopback collega la finestra al motore locale,
con una porta temporanea e un token di sessione; non è un servizio cloud
e non richiede di gestire indirizzi nel browser.

Le impostazioni scientifiche e i calcoli rimangono quelli della 0.8.99.
La preview non converte gli esperimenti storici in nuovi formati distruttivi.
I file devono rimanere nei percorsi originali per essere riaperti; per
conservarli altrove è possibile esportarli insieme ai record dell'esecuzione.
