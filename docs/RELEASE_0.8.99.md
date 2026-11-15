# NIPAT Desktop 0.8.99 — due percorsi Windows indipendenti

Questa release modifica installazione, preparazione e aggiornamenti Windows.
DNPcall, SNPcall, Contamination, CPI prenatale e CPIN postnatale mantengono
i modelli scientifici della 0.8.95.

## ZIP completo locale

`NIPAT-0.8.99-Windows-completo.zip` contiene applicazione, Python e i due
archivi del runtime. Dopo l'estrazione nella posizione definitiva,
`1_INSTALLA.cmd` prepara la sottocartella `NIPAT`. Avvio e ripresa avvengono
tramite `NIPAT\2_AVVIA.cmd` e `NIPAT\1_COMPLETA_PREPARAZIONE.cmd`;
non sono necessari collegamenti nel menu Start.

Dati, risultati, cache, ambiente WSL e preferenze rimangono sotto quella
radice. Gli aggiornamenti ZIP preservano la destinazione originale e
attivano la nuova versione dopo la preparazione. Non eliminare la cartella
NIPAT dopo l'installazione. WSL rimane registrato sul computer: il pacchetto
non è un ambiente portatile fra PC.

`LEGGIMI.txt` descrive anche il recupero in PowerShell: verifica dell'hash
ufficiale, rimozione del contrassegno Internet limitata al pacchetto scelto,
estrazione nuova e avvio dello stesso installatore. La procedura non
disattiva le protezioni e non garantisce l'accettazione di ogni componente
su dispositivi con criteri differenti.

## Setup EXE con pacchetto separato

`NIPAT-Setup.exe` conserva l'installazione guidata, ma acquisisce da GitHub
`NIPAT-<versione>-Windows-payload.zip`. Il bootstrap e la versione NIPAT
hanno identità separate. La copia del setup conservata nell'applicazione
viene riutilizzata per aggiornamenti compatibili: i nuovi contenuti arrivano
come pacchetto verificato, senza richiedere un nuovo EXE per ogni release.

Una prima installazione consulta la release stabile compatibile. Un
aggiornamento usa la versione esatta proposta al client, con commit,
dimensione e SHA-256 verificati. Il feed EXE/payload è separato da quello
ZIP. Il download richiede Internet; i calcoli continuano a essere locali.
Correzioni del bootstrap o cambiamenti incompatibili possono richiedere
un nuovo setup: la sua immutabilità non è un vincolo che impedisce fix.

## Preparazione Windows

La preparazione non carica `NipatActivityNative.dll`. Il coordinamento
fra processi usa primitive Windows e controlli Python. I prerequisiti WSL
sono configurati con gli strumenti del sistema, limitando l'elevazione
alle operazioni che la richiedono.

Lo ZIP e il setup EXE hanno destinazioni e meccanismi di aggiornamento
indipendenti. Questa release non prevede migrazioni automatiche o un
contratto di retrocompatibilità con le installazioni precedenti; dati e
risultati estranei non vengono cancellati per adottare il nuovo layout.

## Verifiche e limiti

I rapporti pubblicati identificano i pacchetti, i relativi hash e le
verifiche CI effettivamente completate. La qualificazione scientifica resta
separata dai controlli dell'installer. I runner ospitati non dimostrano
l'accettazione Smart App Control su un PC reale, né un riavvio Windows/WSL
fisico. Il setup NIPAT rimane privo di firma Authenticode; una prova positiva
su un dispositivo non rappresenta un'autorizzazione universale di Windows.

Per procedure, log e controlli consultare la [guida Windows](INSTALLATORE_WINDOWS.md).
