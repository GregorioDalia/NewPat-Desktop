# NIPAT Desktop 0.8.95 — ZIP completo aggiuntivo per Windows

La 0.8.95 mantiene i quattro installer della 0.8.90 e aggiunge
`NIPAT-0.8.95-Windows-completo.zip`. Il setup `NIPAT-Setup.exe` resta un
singolo file completo. I cinque moduli scientifici e le formule R non cambiano.

## Installazione ZIP

Estrarre completamente il pacchetto e fare doppio clic su `1_INSTALLA.cmd`.
Non occorre installare Python: il pacchetto include Python 3.12.10, il
filesystem WSL e lo stesso archivio scientifico degli altri installer.
Windows può richiedere Internet, autorizzazione amministrativa e un
riavvio per abilitare o aggiornare i propri componenti WSL.

Il programma verifica i file, prepara l'ambiente e crea i collegamenti
**NIPAT Desktop ZIP** e **NIPAT Desktop ZIP - completa preparazione** nel
menu Start. L'applicazione risiede in `%LOCALAPPDATA%\NIPAT-Desktop-Zip`,
con dati, risultati, cache e preferenze propri. Non modifica la cartella
né la registrazione dell'installazione EXE.

Le nuove versioni vengono preparate in cartelle distinte. Solo una
preparazione riuscita aggiorna il puntatore della versione attiva;
interruzioni, riavvii richiesti ed errori non selezionano una versione
ancora da verificare. Gli aggiornamenti dal menu scaricano lo ZIP completo
e mantengono il metodo di installazione. Le precedenti cartelle applicative
restano disponibili; la pulizia automatica di queste cartelle non è prevista.

## Componenti Windows e controlli

Il launcher nativo ha una versione di componente indipendente dalla versione
applicativa: `0.8.81`, corrispondente al codice invariato. La build controlla
che launcher e DLL di coordinamento abbiano gli stessi SHA-256 dei componenti
della 0.8.81. `nipat --version` continua a riportare la versione applicativa.

Il nuovo ZIP evita l'esecuzione del contenitore Inno Setup, ma non costituisce
una garanzia di accettazione da parte di Smart App Control. Script, DLL e
helper WSL restano soggetti ai controlli del dispositivo. Nessuna protezione
viene disattivata e nessuna firma NIPAT viene dichiarata.

I rapporti della release distinguono verifiche dei pacchetti, test del client
con Python incluso e regressioni scientifiche dai collaudi su Windows fisico
con WSL e SAC attivo. `windows-zip-check.json` descrive il controllo del
pacchetto ZIP; `desktop-acceptance.json` vincola anche il suo SHA-256 alla build
accettata. La validazione scientifica di dominio resta separata.

La [guida Windows](INSTALLATORE_WINDOWS.md#zip-completo-aggiuntivo) descrive
installazione, ripresa e percorsi. Lo ZIP automatico **Source code** di GitHub
contiene i sorgenti e non sostituisce questo pacchetto installabile.
