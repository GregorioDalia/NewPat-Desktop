# Distribuzione e requisiti

NewPat distribuisce l’applicazione grafica, la CLI e lo stesso motore scientifico
su Windows, macOS e Ubuntu. Lo ZIP completo Windows e i pacchetti macOS/Ubuntu
contengono l'immagine scientifica. Il setup EXE Windows scarica il pacchetto
applicativo e gli archivi necessari, verificandoli prima dell'installazione.

Questa guida descrive NewPat 0.9.5 Testing, ancora candidato. I pacchetti
pubblicati si trovano negli **Assets** delle [release](https://github.com/GregorioDalia/nipat-desktop/releases);
la stabile 0.8.99 e la preview 0.9.1 conservano il nome NIPAT. I nomi NewPat
riportati di seguito si applicano dalla 0.9.5, quando pubblicata.
Gli archivi **Source code** servono a consultare o costruire i sorgenti. Per la
revisione di una build candidata, seguire invece la [procedura di accettazione](ACCETTAZIONE_INSTALLATORI.md).

## Piattaforme

| Sistema | Ambiente scientifico | Pacchetto |
| --- | --- | --- |
| Windows 10 22H2 x64, build 19045, o Windows 11 x64 | WSL2 con Docker Engine gestito da NewPat | `NewPat-Setup.exe` |
| Windows x64, installazione nella cartella estratta | WSL2 con Docker Engine gestito da NewPat | `NewPat-VERSIONE-Windows-completo.zip` |
| macOS 14 o successivo, Intel | VM Lima AMD64 con Docker Engine | `.pkg` x86_64 |
| macOS 14 o successivo, Apple Silicon | VM Lima ARM64, Rosetta e Docker Engine | `.pkg` arm64 |
| Ubuntu 24.04 LTS x86_64 | Docker Engine locale | `newpat-desktop_VERSIONE_amd64.deb` |

I diversi percorsi distribuiscono lo stesso archivio scientifico Linux AMD64.
L'immagine contiene gli script R, samtools, dipendenze, validazione degli
input e orchestrazione. Ogni analisi usa un container con rete disabilitata,
input selezionati in sola lettura e cartella del run scrivibile.

## Pacchetto Windows

Avviare `NewPat-Setup.exe` dal proprio account. Il setup include il Python
necessario alla preparazione e scarica da GitHub il pacchetto della release,
verifica il sistema e prepara i componenti WSL mancanti. Non occorre installare Docker Desktop, R o samtools.
L'attivazione o l'aggiornamento di WSL può richiedere Internet, autorizzazione
amministrativa e riavvio. Windows ARM, Server e 32 bit non sono supportati.

L'installatore permette di scegliere cartelle di applicazione, ambiente WSL,
cache, dati e risultati. Conserva i percorsi delle installazioni NewPat
riconosciute e non svuota cartelle estranee. Attendere **NewPat: ready**, poi
avviare **NewPat** dal menu Start o dal collegamento sul desktop.
La [guida Windows](INSTALLATORE_WINDOWS.md) descrive aggiornamento, riparazione,
rimozione e gestione degli avvisi di sicurezza.

Per installare dallo ZIP completo, estrarlo nella posizione definitiva e
avviare `1_INSTALLA.cmd`: la sottocartella tecnica `NIPAT` viene conservata
per compatibilità. Il collegamento locale `NewPat.lnk` sceglie automaticamente
l’avvio o il completamento della preparazione. Non viene creato un collegamento
nel menu Start. Applicazione, dati, risultati e preferenze rimangono in quella
cartella; non eliminarla dopo la preparazione. Il motore e Python sono inclusi,
ma i prerequisiti Windows possono richiedere Internet. La registrazione WSL è
specifica del computer: la cartella non è un ambiente portatile fra PC.
Gli aggiornamenti dei due percorsi rimangono separati.

## Pacchetto macOS

Scegliere il `.pkg` della propria architettura, completare l'installazione e
aprire **NewPat** da Applicazioni. Dopo la preparazione si apre la GUI;
il menu testuale resta disponibile dal launcher con il comando `wizard`.
Python e Lima sono inclusi; il primo avvio prepara la VM e richiede Internet.
Homebrew e Docker Desktop non sono prerequisiti. Su Apple Silicon l'immagine
scientifica AMD64 viene eseguita tramite Rosetta nel guest ARM64.

I pacchetti non hanno firma Developer ID o notarizzazione Apple. Per il
messaggio di software non verificato, la [guida macOS](INSTALLATORE_MACOS.md)
spiega l'autorizzazione specifica da Privacy e sicurezza. Le policy di un
Mac gestito possono richiedere l'intervento dell'amministratore.

L'applicazione è in `/Applications/NewPat.app`; dati e risultati sono
nell'area utente `~/Library/Application Support/NIPAT-Desktop`.
Il runtime Lima dedicato non adotta le altre VM dell'utente.
Le installazioni sperimentali hanno identità separata e non vengono rimosse.

## Pacchetto Ubuntu

Installare il `.deb` con il gestore pacchetti oppure aprire il terminale nella cartella del download.
Nel comando di esempio usare il nome effettivo del file scaricato:

```bash
sudo apt install ./newpat-desktop_0.9.5_amd64.deb
```

APT installa le dipendenze mancanti dai repository configurati, inclusi Python,
Docker Engine e Compose. L'accesso dell'utente al daemon deve essere autorizzato
secondo la configurazione del sistema. Il pacchetto non concede automaticamente
questi privilegi. Consultare la [guida Ubuntu](INSTALLATORE_LINUX.md).

## Ubuntu: installazione da sorgenti

Per sviluppo servono Python 3.12 con `venv`, Docker Engine locale e Compose v2.
Dalla radice del checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
newpat build-runtime
newpat doctor --runtime
newpat self-test
newpat wizard
```

La build richiede Internet. Usare directory di sviluppo distinte dall'applicazione
installata. `--data-dir` e `--runs-dir`, prima del sottocomando, selezionano i percorsi.

## Risorse e risultati

Il menu **Configura** permette di consultare risorse disponibili e limiti
applicati. La memoria fisica, quella della VM e il limite del container sono
valori distinti. Le [istruzioni sulle risorse](RISORSE.md) spiegano il loro
significato e le modifiche che richiedono un riavvio.

Ogni analisi conserva una mappa dei campioni e un resoconto leggibile.
Le esportazioni per la consultazione riportano i nomi originali; i risultati
scientifici e i loro metadati conservano gli identificativi necessari a collegare
le fasi. Consultare [Risultati e registrazione](ESECUZIONI.md).

## Aggiornamenti dall'applicazione

**Verifica aggiornamenti** consulta le release compatibili con il sistema.
Le nuove preferenze usano il canale **Stabile**. Il menu **Configura →
Aggiornamenti** permette di selezionare **Testing**; una selezione già salvata
rimane invariata. Il controllo automatico all'avvio è facoltativo e disattivato
per impostazione predefinita.
Il download viene verificato prima dell'installazione. L'aggiornamento dell'app
è distinto dall'aggiornamento dei componenti del sistema, come WSL.
Chiudere le analisi prima di aggiornare; dati e risultati restano nelle loro
cartelle. La guida del proprio sistema descrive il passaggio all'installatore.

Il controllo propone aggiornamenti con un numero di versione superiore e
accetta soltanto il pacchetto della piattaforma in uso. È possibile anche
scaricare manualmente il pacchetto dalla pagina Releases. Versione, commit
e checksum permettono di identificare il pacchetto esatto.

## Integrità e verifiche

Versione, commit, manifest e checksum identificano i pacchetti esatti.
I checksum rilevano differenze di contenuto ma non costituiscono una firma
riconosciuta da Windows o Apple. Il setup non disattiva le protezioni del sistema.

Le note della release riportano le prove effettivamente svolte. La CI controlla
client, pacchetti e regressioni scientifiche; i runner macOS ospitati non
qualificano automaticamente l'avvio di una VM Lima reale. Le prove Windows 10,
le installazioni desktop e la valutazione di dominio restano evidenze distinte,
come descritto in [CI/CD](CI_CD.md) e nella [scheda di validazione](VALIDAZIONE.md).

Il codice originale NewPat usa la licenza [GPL-3.0-or-later](../LICENSE).
Le attribuzioni sono in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
