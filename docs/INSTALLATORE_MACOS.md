# Installatore macOS — NewPat 0.9.5 Testing

NewPat, nuovo nome di NIPAT dalla versione 0.9.5, richiede macOS 14 o
successivo su Intel o Apple Silicon. Il pacchetto comprende l'interfaccia
grafica, la CLI guidata, Python e Lima nativi e il motore scientifico Linux AMD64.
Questa guida descrive la candidata **0.9.5 Testing**: le modifiche sono in
sviluppo e non costituiscono una release già pubblicata o una qualificazione
su Mac reale. Quando pubblicati, i pacchetti e le verifiche associate saranno
negli asset della [release corrispondente](https://github.com/GregorioDalia/nipat-desktop/releases).

## Requisiti e pacchetti

| Mac | Pacchetto | Esecuzione scientifica |
| --- | --- | --- |
| Intel x86_64 | `NewPat-0.9.5-macos-x86_64.pkg` | Guest Lima AMD64 e container Linux AMD64. |
| Apple Silicon arm64 | `NewPat-0.9.5-macos-arm64.pkg` | Guest Lima ARM64 e container Linux AMD64 tramite Rosetta. |

Python e Lima nativi per l'host sono inclusi; Homebrew, R, samtools e Docker
Desktop non sono prerequisiti. Servono spazio per applicazione, immagine,
disco della VM, input e risultati e una connessione Internet al primo avvio
per la preparazione del guest e del motore. Rosetta è necessaria alla modalità
AMD64 su Apple Silicon. La virtualizzazione deve essere disponibile.

Il pacchetto non dispone di firma Developer ID né di notarizzazione Apple.
Gatekeeper o le policy amministrative possono impedire installazione e avvio.
Il setup non disattiva le protezioni. In presenza di un blocco, conservare
messaggio, componente indicato e identità del pacchetto per la diagnosi.
L'assenza di una firma riconosciuta impedisce di garantire un'esperienza senza
intervento su ogni dispositivo del team.

### Autorizzazione del pacchetto non verificato

Se macOS mostra «Apple non è in grado di verificare» per il pacchetto scaricato
dal repository del progetto, chiudere l'avviso con **Fine**. Aprire **Impostazioni di
Sistema → Privacy e sicurezza**, individuare il pacchetto bloccato e scegliere
**Apri comunque**, quindi confermare. Può essere necessario autorizzare anche
l'applicazione al primo avvio. Questa eccezione riguarda il software selezionato;
non richiede di disabilitare Gatekeeper. La procedura ufficiale è descritta nel
[supporto Apple](https://support.apple.com/it-it/102445).
Su dispositivi gestiti l'amministratore può limitare le autorizzazioni.

## Installazione e primo avvio

1. Scaricare il `.pkg` della propria architettura dalla pagina Releases. Controllare versione e checksum associati.
2. Aprirlo con doppio clic e completare la procedura di Installer.
3. Aprire **NewPat** da Applicazioni. Compare la finestra di preparazione
   dell'ambiente scientifico; l'avvio grafico non richiede il Terminale.
4. Attendere la creazione dell'ambiente Lima, l'importazione verificata
   dell'immagine e il controllo dei contratti del motore. Un errore interrompe
   la preparazione; non viene avviata un'analisi con stato incompleto.
5. Quando compare l'interfaccia grafica, creare un esperimento o aprire i
   risultati. La CLI rimane disponibile dal launcher indicato sotto.

Gli avvii successivi usano lo stesso collegamento e lo stesso ambiente
verificato. Dopo la preparazione i calcoli sono locali; non richiedono
una connessione per scaricare componenti scientifici. Il singolo container
di analisi ha la rete disabilitata.

NewPat usa un ambiente dedicato, distinto dalle installazioni sperimentali.
Non adotta una VM Lima esistente dell'utente e non modifica configurazioni
Docker Desktop o altre VM.

## Percorsi e accesso ai file

| Risorsa | Percorso |
| --- | --- |
| Applicazione | `/Applications/NewPat.app` |
| Launcher CLI | `/Applications/NewPat.app/Contents/Resources/NewPat.command` |
| Area dell'utente | `~/Library/Application Support/NIPAT-Desktop` |
| Dati e risultati predefiniti | Sottocartelle `data` e `runs` dell'area utente. |
| Preferenze | `preferences.json` nell'area utente. |
| Stato e log runtime | `.runtime/macos/runtime.json` e `.runtime/macos/setup.log` nell'area utente. |
| Lima home | `~/.nipat/lima` |
| VM dedicata | `nipat` |

I percorsi dell'area utente, l'identità del pacchetto e della VM conservano i
nomi tecnici NIPAT per riutilizzare le installazioni e i risultati esistenti.
Nel nuovo bundle è mantenuto anche l'alias `NIPAT.command`.

La cartella Lima ha un percorso breve per rispettare i limiti dei socket
Unix. La configurazione e il registro di proprietà associano la VM a questa
installazione; il solo nome non autorizza la rimozione di una VM estranea.

La VM espone la home dell'utente, `/Volumes`, `/private/tmp` e la directory
temporanea dell'account in lettura/scrittura. La cartella applicativa è
esposta in sola lettura quando esterna alla home. Questo è l'accesso della
VM: il **container di ogni analisi** riceve soltanto gli input selezionati
in sola lettura e la directory del relativo run in lettura/scrittura.
I permessi macOS, incluse le autorizzazioni per cartelle protette, continuano
ad applicarsi. Non è garantito accesso indiscriminato a tutti i dischi.

Gli input possono contenere spazi nei percorsi. I percorsi relativi partono
dalla directory corrente indicata dal menu. Le opzioni `--data-dir` e
`--runs-dir` selezionano le destinazioni; **Configura** conserva le preferenze
del menu. La verifica dei mount può rifiutare un percorso non esposto nella VM.

Per una cartella aggiuntiva, usare il launcher con
`--runtime prepare --mount <percorso>`. Dalla 0.9.5 la configurazione della VM
gestita viene aggiornata senza ricrearla: le altre condivisioni e le risorse
assegnate restano conservate. Chiudere prima le altre sessioni NewPat/NIPAT
e attendere la conclusione delle analisi.

Lo stesso controllo viene eseguito all'avvio se l'applicazione è stata
spostata, per esempio dalla Scrivania ad Applicazioni, o rinominata in NewPat.
Prima della modifica vengono verificate proprietà e configurazione della VM;
una sessione dell'applicazione o un container ancora attivo impediscono la
manutenzione. Quando necessaria, la VM inattiva viene arrestata e riavviata.
Sono ritirati soltanto i vecchi mount in sola lettura di un bundle NIPAT/NewPat
non più presente e già registrati come appartenenti all'installazione.
Le cartelle personalizzate non vengono rimosse.

Il backup `mount-backup-*.json` in `.runtime/macos` conserva configurazione e
registro di proprietà precedenti. Se la modifica fallisce, NewPat tenta il
ripristino e indica eventuali problemi di recupero senza cancellare la VM,
i dati o i risultati. Prima di dichiarare pronto l'ambiente verifica anche
che la VM legga il manifesto dell'applicazione corrente con lo stesso checksum.

## CLI e diagnostica

Il launcher accetta i comandi NewPat con gli stessi argomenti scientifici
delle altre piattaforme. Ad esempio:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" doctor --runtime
"/Applications/NewPat.app/Contents/Resources/NewPat.command" self-test
```

La preparazione iniziale controlla archivio e contratti del motore; non
esegue automaticamente gli autotest numerici. Il comando `self-test` li
esegue esplicitamente. **8 — Verifica ambiente** dal menu offre la diagnostica.

I comandi di gestione del runtime sono separati dalle analisi:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime status
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime ensure
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime stop
```

`status` consulta lo stato e segnala `repair_required` se i mount non
corrispondono all'applicazione corrente; `ensure` verifica il runtime preparato;
`stop` arresta la VM. Non arrestare la VM durante un'analisi: annullare prima
il calcolo dal menu con Ctrl+C e attendere la conclusione della procedura.
Per una preparazione fallita conservare `setup.log`, il messaggio completo,
versione e architettura macOS e commit del pacchetto. Dopo aver risolto la
causa, riaprire l'applicazione o utilizzare `--runtime prepare`.

## Aggiornamento e rimozione

Usare **Verifica aggiornamenti** per consultare i pacchetti compatibili,
oppure scaricare il nuovo `.pkg` dalla pagina Releases. Chiudere NewPat e le
eventuali vecchie sessioni NIPAT prima
di installare l'aggiornamento. I dati e i risultati dell'account restano separati dal bundle
applicativo. Non installare un pacchetto per l'architettura diversa da quella
host per tentare di cambiare la modalità scientifica.

La rimozione dell'applicazione non elimina automaticamente VM, dati e
risultati. Per rimuovere **soltanto il runtime Lima gestito da NewPat**, dopo
aver chiuso le analisi, usare prima di rimuovere l'applicazione:

```bash
"/Applications/NewPat.app/Contents/Resources/NewPat.command" --runtime remove-runtime
```

Il comando verifica la proprietà dell'ambiente e rimuove la VM dedicata;
conserva dati e risultati. Una nuova preparazione dovrà ricreare la VM e
importare l'immagine. Non rimuovere manualmente altre istanze Lima o cartelle
con contenuto non identificato come appartenente all'installazione.

## Ambito delle verifiche

La CI è predisposta per controllare client, contratti e confezionamento
Intel/Apple Silicon. I test automatici della migrazione simulano spostamento e
rinomina dell'applicazione, sessioni attive, errore di modifica e ripristino.
Questi test non eseguono una VM macOS reale.
Le prove di VM Lima reali sono distinte e richiedono runner con virtualizzazione
appropriata. L'installazione dal Finder, le policy di sicurezza, i permessi
sui file e la ripresa su un Mac reale vanno registrati separatamente nella
[scheda di validazione](VALIDAZIONE.md). La medesima versione R e gli stessi
input attesi non sostituiscono il confronto numerico sul trasporto Rosetta.

La [guida per l'utilizzo](GUIDA_UTILIZZO.md) descrive gli input e i workflow;
le [release pubblicate](https://github.com/GregorioDalia/nipat-desktop/releases) riportano le verifiche dei singoli pacchetti.

## Configurazione delle risorse

Dal menu **Configura** consultare memoria e CPU del Mac, della VM Lima e del
container. Per modificare la RAM o le CPU della VM dedicata, verificare
l'anteprima e confermare la modifica. Un backup conserva la configurazione
precedente. Se è necessario riavviare la VM, NewPat richiede una conferma
separata e non interrompe analisi in corso.

Aumentare soltanto il limite del container non aumenta la RAM assegnata a Lima.
I valori suggeriti aiutano a ripartire le risorse del computer; non stimano il
fabbisogno scientifico dei BAM. Consultare [Risorse e memoria](RISORSE.md).
