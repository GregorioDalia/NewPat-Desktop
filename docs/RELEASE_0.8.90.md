# NIPAT Desktop 0.8.90 — consolidamento del backend

La 0.8.90 corregge quattro difetti individuati nella revisione della
[0.8.81](RELEASE_0.8.81.md) e nel collaudo dell'installazione. Mantiene
i cinque moduli scientifici, il menu testuale e la CLI.

## Correzioni

- **Ruoli CPI tra coppie.** Anche l'esecuzione diretta rifiuta un campione
  usato come madre in una coppia e padre in un'altra. Per esempio,
  `A:B,B:C` con entrambi i prefissi vuoti viene rifiutato prima delle copie
  e dell'avvio del motore. Resta possibile riutilizzare un campione nello
  stesso ruolo; prefissi diversi continuano a identificare file diversi.
- **Preferenze dei cutoff SNP.** La configurazione accetta e conserva le
  mappe `etichetta=percorso` con pannelli di coordinate SNP, oltre ai DNP,
  usando la stessa validazione disponibile durante l'analisi.
- **Test del pileup parallelo.** La prova del completamento fuori ordine
  sincronizza esplicitamente i processi di test. Non dipende più da ritardi
  stimati con `sleep`; continua a verificare ordine dei risultati, limite
  dei processi, esiti e pulizia dei file temporanei.
- **Collaudo del BAM corrotto.** `reject-corrupt-bam` riconosce sia il
  messaggio di `samtools view` (`header from`) sia quello precedente di
  `mpileup` (`header of`). Il motore rifiutava già il file: era il collaudo
  a classificare erroneamente tale rifiuto come FAIL. Restano obbligatori
  esito negativo, assenza di timeout e assenza di errori infrastrutturali.

Le formule e i sorgenti R non cambiano. La preparazione Windows e il
componente nativo mantengono la correzione introdotta nella 0.8.81.

## Installazione e verifiche

Scaricare il pacchetto dalla release: `NIPAT-Setup.exe` per Windows,
DEB per Ubuntu 24.04 oppure PKG per macOS Intel o Apple Silicon.
Le [guide di installazione](README.md#installare) descrivono requisiti
e aggiornamento; il [collaudo dei cinque moduli](COLLAUDO_INSTALLAZIONE.md)
verifica l'installazione e registra i tempi delle analisi.

Il record `desktop-acceptance.json` e i rapporti allegati alla release
identificano la build, i pacchetti e le verifiche eseguite. I collaudi su
computer fisici restano attribuiti alle versioni effettivamente provate;
le prove desktop rinviate e la validazione scientifica di dominio sono
dichiarate separatamente. La release costituisce una base per la GUI,
senza escludere successive correzioni del backend.
