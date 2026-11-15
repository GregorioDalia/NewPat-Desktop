# NIPAT Desktop 0.8.81 — correzione della preparazione Windows

La 0.8.81 corregge la modifica al componente nativo Windows introdotta nella
0.8.80, associata a un blocco di Smart App Control prima dell'avvio della
preparazione. Mantiene le funzionalità e le correzioni scientifiche della
[0.8.80](RELEASE_0.8.80.md).

## Preparazione Windows

- Il componente `NipatActivityNative.dll`, usato per coordinare installazione
  e analisi, torna al sorgente della 0.8.70. La build deterministica consente
  il confronto del binario con quello distribuito in tale versione.
- Il Python già incluso nel pacchetto gestisce i limiti temporali dei
  controlli di preparazione e l'arresto dei relativi processi. Restano i log
  durante l'esecuzione, i codici di errore e la possibilità di riprendere
  una preparazione interrotta.
- I controlli automatici Windows coprono anche processi discendenti,
  timeout, diagnostica, ripresa e conservazione dei processi estranei.

Il pacchetto rimane privo di firma del distributore. La build su Windows
Server verifica il client e il confezionamento; l'accettazione da parte di
Smart App Control sul computer destinatario richiede una prova distinta.

## Installazione e verifiche

Scaricare `NIPAT-Setup.exe` dalla release e installarlo nelle stesse cartelle
già utilizzate. Anche quando la preparazione della 0.8.80 non è terminata,
l'installer della 0.8.81 può aggiornare i file e riprendere la preparazione.
Dati e risultati esistenti vengono conservati. Attendere il messaggio
**NIPAT Desktop e pronto** prima di avviare il
[collaudo dei cinque moduli](COLLAUDO_INSTALLAZIONE.md).

Sono disponibili anche il DEB Ubuntu 24.04 e i PKG macOS Intel e Apple
Silicon. Le [guide di installazione](README.md#installare) descrivono i
requisiti delle piattaforme.

Il record `desktop-acceptance.json` e i rapporti allegati identificano la
build, i pacchetti e le verifiche effettivamente eseguite. Le prove desktop
rinviate e la validazione scientifica di dominio rimangono dichiarate
separatamente; i collaudi storici restano attribuiti alle versioni provate.
