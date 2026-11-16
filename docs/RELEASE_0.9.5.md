# NewPat 0.9.5 Testing — candidato in sviluppo

NewPat è il nuovo nome dell'applicazione precedentemente distribuita come
NIPAT Desktop. La 0.9.5 è un candidato del canale **Testing**: questo documento
descrive il lavoro della versione e non attesta la pubblicazione dei pacchetti
o il completamento dei collaudi. La versione stabile pubblicata resta NIPAT
0.8.99; i pacchetti e gli esiti effettivi vanno verificati nella pagina
[Releases](https://github.com/GregorioDalia/nipat-desktop/releases).

## Esperimenti e messaggi

- **Nuovo esperimento** apre una bozza vuota e ripristina le preferenze salvate.
  Nome, file, campioni, famiglie, riepilogo ed errori del run precedente non
  vengono riutilizzati. Le risposte tardive a una vecchia richiesta non devono
  ripopolare la nuova bozza.
- **Riesegui** e **Prepara analisi** conservano il riuso esplicito della
  configurazione e degli input pertinenti; ogni esecuzione produce un nuovo run.
- Gli errori di validazione vengono mostrati con la loro spiegazione, anche
  quando provengono dal motore scientifico.
- IGV distingue riferimento assente, campioni non caricati, regione troppo
  ampia e incompatibilità dei file. Per lunghezze dei cromosomi incompatibili
  indica i file e i valori confrontati. Non ignora il controllo per consentire
  una visualizzazione potenzialmente scorretta.

## Ambiente macOS

La preparazione controlla la visibilità effettiva della cartella applicativa
nella VM. Il passaggio dalla Scrivania ad Applicazioni, o dal vecchio nome
a **NewPat.app**, richiede che la condivisione corrisponda al percorso corrente.
Il recupero conserva la VM e le cartelle dell'utente, verifica la proprietà
dell'ambiente e salva la configurazione prima di modificarla. Una sessione
attiva impedisce una manutenzione incompatibile con l'analisi in corso.

Il percorso ordinario diventa `/Applications/NewPat.app`. L'area dati
`~/Library/Application Support/NIPAT-Desktop` e l'identità tecnica della VM
restano compatibili con le installazioni precedenti.

## Risorse e ripetibilità

Il budget di CPU e memoria è determinato dalle capacità assegnate all'ambiente
e dai limiti del container. La scelta viene registrata all'inizio del run e
non segue le oscillazioni della memoria libera causate da altre applicazioni.
Il tetto globale dei processi rimane fisso durante l'analisi; una fase con
meno attività indipendenti può impiegarne meno.

Il valore universale di 2 GiB per processo viene sostituito da una pianificazione
che distingue risorse assegnate, memoria del coordinatore e lavoro previsto.
Per DNP gli obiettivi dei blocchi devono rispettare le risorse e i limiti
scelti dall'utente, senza spezzare gruppi indivisibili o modificare i filtri
scientifici. Le fixture locali verificano equivalenza numerica e ordinamento;
le misure sui dati reali e il runtime distribuito restano requisiti distinti
di qualificazione. L’acquisizione DNP e i cicli esterni dei campioni SNP e
delle tabelle di contaminazione restano seriali quando il loro fabbisogno
non è osservato. Le fasi interne con dati caricati possono parallelizzare:
non si presume un miglioramento delle prestazioni dal solo cambio di politica.

## Diagnostica

La GUI offre l'apertura della cartella dell'esperimento e l'esportazione di
un archivio diagnostico. Questo raccoglie informazioni sulla versione,
sull'ambiente e i log pertinenti, con limiti di dimensione. Non include
automaticamente BAM, FASTA o tabelle dei risultati genetici.
L'esportazione completa dei risultati rimane un'azione distinta.

## Grafici CPI e CPIN

I risultati prenatali e postnatali offrono il dettaglio interattivo dei valori
calcolati. La **Vista combinata** riprende le tre serie degli script originali:
nero per log₁₀(CPI), verde per i siti compatibili, arancione tratteggiato per
i siti incompatibili. Gli assi distinguono indice e numero di siti;
il dettaglio riporta i valori nativi, anche quando il disegno usa una
trasformazione di scala. Le viste separate restano disponibili.

Le esportazioni statiche e le tabelle originali sono conservate. La vista
combinata HTML è una rappresentazione dei dati registrati, non una sostituzione
del PDF prodotto dal run. Le viste interattive funzionano localmente, senza
inviare dati a servizi esterni. Curve troppo grandi o senza le colonne
necessarie rinviano ai file originali con un messaggio esplicito.

## Nome, pacchetti e compatibilità

Il nome pubblico è **NewPat** nelle finestre, nei collegamenti, negli installer,
nelle icone e nelle guide correnti. Il comando principale è `newpat`; `nipat`
rimane disponibile per gli script esistenti. I nomi tecnici delle installazioni
e i percorsi già configurati possono conservare NIPAT per permettere
aggiornamenti e riapertura degli esperimenti senza spostare i dati.

I pacchetti pubblici della versione usano i nomi `NewPat-Setup.exe`,
`NewPat-0.9.5-Testing-installazione.zip`, `NewPat-0.9.5-Windows-completo.zip`,
`NewPat-0.9.5-macos-arm64.pkg`, `NewPat-0.9.5-macos-x86_64.pkg` e
`newpat-desktop_0.9.5_amd64.deb`. Gli alias destinati ai client precedenti
devono avere gli stessi byte e checksum dei pacchetti corrispondenti.

Il repository resta all'URL storico. Attribuzioni, licenze, riferimenti congelati,
record degli esperimenti e note delle release precedenti conservano i nomi
originali. Il cambio di nome non modifica la provenienza dei moduli scientifici.

Un setup Windows ricompilato ha una nuova identità binaria. Il comportamento
osservato per il precedente eseguibile non costituisce una verifica del nuovo
pacchetto con Smart App Control. Le protezioni del sistema restano attive.

## Criteri prima della distribuzione

1. Regressioni GUI: nuova bozza, riuso esplicito, file e richieste asincrone,
   errori IGV, stati degli esperimenti e diagnostica.
2. Ambiente Mac: installazione nuova e cambio di percorso/nome, proprietà
   verificata, configurazione conservata, recupero dopo un errore e sessioni
   concorrenti. Le simulazioni non sostituiscono la VM su un Mac reale.
3. Budget: configurazione stabile del run, limiti e modalità seriale, gruppi
   indivisibili e confronto numerico dei risultati tra configurazioni.
4. Pacchetti: installazione pulita e aggiornamento da NIPAT, dati e preferenze
   conservati, identità NewPat e compatibilità degli aggiornamenti precedenti.
5. Evidenze legate al commit e ai pacchetti effettivi; nessuna promozione
   automatica a stabile per il solo numero di versione.

## Verifiche locali del candidato

Sono stati eseguiti i test Python e JavaScript dell'applicazione, le regressioni
simulate dei launcher e della migrazione, i controlli del budget R e i
confronti numerici DNP/SNP/contaminazione con i riferimenti congelati.
I profili sintetici DNP da 2, 4 e 8 GiB verificano valori, identità delle
letture e ordinamento; non misurano le prestazioni sui BAM degli utenti.

I confronti R locali usano R 4.4.2 con dipendenze di test che possono differire
da quelle dell'immagine distribuita. La CI deve verificare anche il runtime
Docker esatto. I controlli simulati non attestano l'installazione e il
funzionamento di Lima sui Mac M1/M3 reali, né l'accettazione dei nuovi binari
da parte delle protezioni Windows.
