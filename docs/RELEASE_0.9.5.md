# NewPat 0.9.5 Testing

NewPat è il nuovo nome dell'applicazione precedentemente distribuita come
NIPAT Desktop. La 0.9.5 è preparata per la distribuzione di ricerca sul canale
**Testing**, dopo il superamento dei controlli CI descritti sotto. La costruzione
e la verifica degli installatori finali precedono la pubblicazione: queste note
non attestano che i pacchetti siano già disponibili. La versione stabile resta
NIPAT 0.8.99; i download e le relative evidenze saranno nella pagina
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

## Verifiche eseguite

La [CI 43904019136](https://github.com/GregorioDalia/nipat-desktop/actions/runs/43904019136)
è completata con esito positivo sul commit `c0cb823602d69fe4998c550b8bd5a560d659655c`.
Sono passati tutti i controlli applicabili di Windows, Linux, macOS ARM64 e
Intel, runtime, confezionamento e qualificazione scientifica, incluso il
controllo finale aggregato. Le prove della finestra nativa sono riuscite con
WebView2 su Windows, WKWebView su entrambe le architetture Mac e GTK su Linux.

I **sette controlli scientifici** sono passati nell'immagine Docker Linux AMD64
esatta identificata dai rapporti CI: script incorporati, etichette e risultati,
regressioni e modalità di input, misure di prestazione e risultati DNP,
casi limite e parametri, modelli aggiornati e confronto con i riferimenti
immutabili. La qualificazione dei cinque moduli riporta **86 esecuzioni riuscite
su 86**. I rapporti sono conservati negli artefatti della stessa CI; il riuso
durante la build richiede la corrispondenza dell'albero sorgente e dell'ID
immutabile dell'immagine scientifica.

Sono stati eseguiti i test Python e JavaScript dell'applicazione, le regressioni
simulate dei launcher e della migrazione, i controlli del budget R e i
confronti numerici DNP/SNP/contaminazione con i riferimenti congelati.
I profili sintetici DNP da 2, 4 e 8 GiB verificano valori, identità delle
letture e ordinamento; non misurano le prestazioni sui BAM degli utenti.

I confronti R locali usano R 4.4.2 con dipendenze di test che possono differire
da quelle dell'immagine scientifica; la qualificazione CI nell'immagine esatta
è registrata separatamente. Su Windows sono riuscite anche compilazione,
installazione, aggiornamento e rimozione della fixture dell'installer,
conservando i dati predisposti dalla prova.

## Verifica dei pacchetti e prove sui dispositivi

La build degli installatori lega i quattro pacchetti finali allo
stesso commit e archivio scientifico, verificarne i contenuti e conservare i
checksum e i rapporti. La pubblicazione richiede questa build riuscita e il
record di accettazione corrispondente; una CI sul sorgente non sostituisce
la verifica dei byte degli installatori.

Restano da provare l'installazione finale e il funzionamento di Lima/Rosetta
sui Mac M1/M3 reali, inclusi aggiornamento da NIPAT e recupero dell'ambiente,
e il setup completo con WSL su Windows 10/11. I controlli Windows CI sono
eseguiti su Windows Server 2022 e non attestano l'accettazione dei nuovi binari
da parte di Smart App Control. Analogamente, le prove WKWebView su runner Mac
non attestano l'accettazione Gatekeeper o l'avvio della VM sul Mac destinatario.

Le prove desktop rinviate sono dichiarate nel record di accettazione della
distribuzione pre-1.0. La valutazione scientifica sui dati reali rimane affidata
ai ricercatori. La 0.9.5 resta sul canale **Testing** e non diventa stabile
per il solo superamento dei controlli automatici.
