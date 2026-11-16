# Usare NewPat 0.9.5 Testing

NewPat offre una finestra desktop con analisi, risultati e IGV integrato.
Non è necessario aprire un browser né installare IGV Desktop. Questa guida
descrive il candidato 0.9.5, ancora in sviluppo: consultare le
[note 0.9.5](RELEASE_0.9.5.md) per il perimetro e le verifiche richieste.
La preview già pubblicata resta la [0.9.1](RELEASE_0.9.1.md).

## Creare un esperimento

1. Aprire **Nuovo esperimento**, assegnare un nome all'esperimento e scegliere
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

**Nuovo esperimento** apre una scheda pulita: non conserva campioni, ruoli,
nome o selezioni dell'analisi precedente. Sono applicate soltanto le
impostazioni predefinite salvate nelle preferenze. Per partire invece da
un esperimento esistente usare esplicitamente **Riesegui** o il riuso della
configurazione. Tornare a una bozza tramite la navigazione non equivale
a chiedere un nuovo esperimento.

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

Dopo una chiusura anomala NewPat verifica se un'esecuzione è ancora attiva.
Se non è attiva e non risulta finalizzata, appare come interrotta. Se il
runtime non è verificabile, lo stato resta da verificare: un singolo modulo
completato non basta a dichiarare concluso l'esperimento. La rimozione dalla
lista è bloccata quando l'attività potrebbe essere ancora in corso.

I valori mancanti sono distinti da zero. L'indice CPI e il suo logaritmo
sono presentati con la scala appropriata; le celle delle tabelle conservano
il valore originale. Le anteprime paginate non sostituiscono i file completi
esportabili. Il completamento tecnico del run non costituisce da solo una
validazione scientifica dei risultati.

## Grafici interattivi CPI e CPIN

Nelle schede **CPI prenatale** e **CPIN postnatale**, i grafici locali
consentono di passare sui punti o fare clic per leggere i valori originali
in un riquadro HTML. Non richiedono Internet. Con la tastiera, **Tab**
raggiunge il grafico, le **frecce** scorrono i punti della pagina,
**Home/Fine** raggiungono il primo/ultimo punto ed **Esc** chiude il dettaglio.

| Analisi | Asse orizzontale | Asse verticale | Secondo pannello |
| --- | --- | --- | --- |
| CPI prenatale | `Iteration`: numero minimo di letture fetali | `log_CPI`, già in scala log10 | `NotMismatch` e `Mismatch`, conteggi dei siti |
| CPIN postnatale | Da `Min_child_reads` a `Through_min_child_reads`, estremi inclusi | `Log10_CPI`, già in scala log10 | `N_sites`, `Matching_sites` e `Mismatching_sites` |

Il riquadro mostra i valori testuali originali delle colonne, senza
ricalcolare CPI o arrotondarne la precisione. Le soglie prenatali sono
punti discreti; gli intervalli postnatali sono segmenti costanti. Non
vengono calcolati valori intermedi tra righe né collegati intervalli separati.
Valori mancanti/non finiti, conteggi non validi e soglie non valide sono
segnalati e non disegnati; rimangono consultabili nei dati originali.

Le curve complete sono caricate solo entro **20.000 righe e 16 MiB per
file**. Superato un limite, la schermata spiega il problema e lascia
consultabili riepilogo, PDF e tabelle originali. Per mantenere reattiva
l'interfaccia, grafici e tabella dei dettagli mostrano **1.000 righe per
pagina**, con intervallo visualizzato e pulsanti per le altre righe:
non è un campionamento. Una riga con intervallo postnatale può rappresentare
più soglie incluse senza essere espansa artificialmente.

**Viste separate** mantiene log CPI e conteggi in pannelli distinti.
**Vista combinata** riunisce le tre serie richieste: nero per `log_CPI` /
`Log10_CPI`, verde per `NotMismatch` / `Matching_sites` e arancione
tratteggiato per `Mismatch` / `Mismatching_sites`. `N_sites` resta nel
pannello separato e nel dettaglio, senza introdurre una quarta curva combinata.

La vista prenatale combinata mantiene la scala numerica condivisa della
versione storica: asse sinistro log10(CPI), asse destro conteggi interi
non negativi. I collegamenti uniscono solo soglie intere consecutive con
valori registrati, senza attraversare dati mancanti o aggiungere stime.
La vista postnatale usa la trasformazione reversibile del grafico R:
`y_conteggio = conteggio × scala + offset`, dove l'intervallo log CPI
comprende le guide del passo archiviate, `offset` è il suo minimo e
`scala` è la sua ampiezza divisa per il massimo dei due conteggi (almeno 1).
L'asse destro applica l'inversa e il dettaglio mostra sempre i conteggi
originali. In assenza delle guide archiviate, l'interfaccia lo dichiara e
usa l'intervallo osservato, ampliato solo per la visualizzazione se costante:
non inventa soglie scientifiche. La scala combinata usa tutte le righe della
curva caricata e rimane invariata passando da una pagina all'altra.

Le viste interattive rappresentano i dati tabellari; i **PDF originali**
conservano l'impaginazione, le guide e tutte le annotazioni del grafico
scientifico. Esportazioni e file statici restano disponibili invariati.

## Esplorare i dati con IGV

Aprire **IGV**, scegliere il FASTA locale e aggiungere i BAM come tracce.
Se gli indici corrispondenti si trovano accanto ai file, NewPat li riconosce
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
allineamenti. Se le lunghezze di un contig differiscono, il messaggio indica
contig, file e lunghezze rilevate: occorre scegliere il riferimento usato
per allineare quel BAM. Non basta cambiare il nome del cromosoma o ignorare
la differenza di lunghezza. Il riferimento può essere esplorato anche senza
un BAM; per visualizzare le letture bisogna aggiungere il campione e il suo
indice. I messaggi di navigazione distinguono questi casi.

La preview utilizza file locali: non carica automaticamente
genomi, annotazioni o dati da servizi remoti. I grandi file sono letti
per intervalli, senza trasferire l'intero BAM all'interfaccia.

## Preferenze e manutenzione

La lingua è selezionabile dalla barra superiore. Le preferenze includono
riduzione delle animazioni, cartelle, impostazioni predefinite e limiti
delle risorse. Il catalogo scientifico raccoglie parametri, costanti e
formule. Le funzioni di ambiente e manutenzione riutilizzano quelle della
CLI, comprese le conferme per le operazioni che modificano il runtime.

La CLI resta disponibile con `newpat gui`, `newpat wizard` e i singoli comandi
scientifici. Nelle distribuzioni Windows i comandi si richiamano tramite
`newpat.cmd`; `nipat` e `nipat.cmd` restano alias compatibili. Il normale
avvio `2_AVVIA.cmd` apre la GUI.

**Apri cartella esperimento** porta alla directory effettiva del run, anche
quando non coincide con il percorso predefinito. **Esporta diagnostica**
raccoglie metadati e log limitati per dimensione; è disponibile anche senza
un esperimento completato. Non include automaticamente BAM, FASTA o tabelle
genetiche. I log possono comunque contenere nomi e percorsi dei campioni.

## Implementazione e limiti della preview

L'applicazione usa WebView2 su Windows, WKWebView su macOS e WebKitGTK su
Ubuntu. L'interfaccia e igv.js sono incluse nel pacchetto. Un servizio
riservato al processo su loopback collega la finestra al motore locale,
con una porta temporanea e un token di sessione; non è un servizio cloud
e non richiede di gestire indirizzi nel browser.

Le formule scientifiche sono conservate. La 0.9.5 modifica la pianificazione
dei processi e dei blocchi: i confronti numerici sono parte della sua
qualificazione, separatamente dalle regressioni dell'interfaccia.
La preview non converte gli esperimenti storici in nuovi formati distruttivi.
I file devono rimanere nei percorsi originali per essere riaperti; per
conservarli altrove è possibile esportarli insieme ai record dell'esecuzione.
