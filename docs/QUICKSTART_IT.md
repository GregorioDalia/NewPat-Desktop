# Il primo esperimento con NewPat

La demo guidata della 0.9.10 esegue DNP e SNP su tre campioni simulati. Puoi provare l’intero percorso, dall’avvio alla lettura dei risultati, usando solo i file inclusi.

## Apri la demo

Se nella tua copia della 0.9.10 vedi soltanto **Salva dati di esempio**, scegli una cartella come Documenti e apri il file `synthetic-trio/README.md` che NewPat vi copia. Ti indica quali file selezionare. Nelle build con **Apri demo**, segui questi tre passaggi.

1. Avvia NewPat. Su Windows, se hai installato lo ZIP completo, apri il collegamento `NewPat.lnk` nella cartella `NIPAT` creata dall’installazione. Con il setup EXE usa **NewPat** nel menu Start. Su macOS apri **NewPat** da Applicazioni. Puoi scegliere l’italiano dalla bandiera nella barra superiore.
2. Apri **Ambiente e guida → Dati di esempio → Apri demo**. Se avevi già modificato una bozza, NewPat ti chiede conferma prima di sostituirla. Nel **Riepilogo** trovi `mother`, `father` e `child`, il riferimento sintetico e i pannelli DNP e SNP già selezionati. Puoi espandere **Risultati attesi della demo** prima di iniziare.
3. Premi **Avvia esperimento** e segui l’esecuzione in **Attività**. Quando compare **Completato**, apri **Esperimenti e risultati → Demo DNP e SNP → Risultati**.

### Verifica i conteggi

Apri la scheda **DNP**, scegli il campione e controlla le tre righe della tabella. Ripeti nella scheda **SNP**. I valori attesi valgono per **ciascun sito** di ciascuna scheda.

| Campione | Righe per scheda | Letture REF | Letture ALT | Altre letture | Totale per sito |
| --- | ---: | ---: | ---: | ---: | ---: |
| `mother` | 3 | 96 | 4 | 0 | 100 |
| `father` | 3 | 50 | 50 | 0 | 100 |
| `child` | 3 | 50 | 50 | 0 | 100 |

DNP e SNP assegnano un genotipo ai siti di ogni campione. Le stime di parentela provengono dalle analisi CPI, che selezioni separatamente. Nel glossario **Risultato non disponibile (`NA`)** indica che il programma non ha potuto determinare il valore. Uno zero nella colonna delle altre letture è invece un conteggio misurato.

## Quale cartella scegliere

| Cosa vuoi fare | Cosa selezionare |
| --- | --- |
| Eseguire la demo | Basta **Apri demo**. NewPat ha già il riferimento e gli altri file necessari. |
| Salvare i dati di prova per riutilizzarli | Scegli **Ambiente e guida → Salva dati di esempio**, poi una cartella scrivibile, per esempio Documenti. NewPat vi crea `synthetic-trio`. Se esiste già, scegli un’altra cartella. |
| Analizzare dati tuoi | In **Nuovo esperimento**, aggiungi i singoli BAM dalla cartella in cui li conservi. Seleziona il file FASTA usato per allinearli e il pannello corrispondente a ciascun tipo di marcatore. Lascia gli indici accanto ai file. |
| Indicare l’installazione Windows ZIP a uno strumento di collaudo | Se viene richiesta la cartella con `current.json`, scegli la cartella `NIPAT` che contiene quel file e `NewPat.lnk`. Per la distinta richiesta dei dati indica la cartella in cui hai conservato i campioni. |
| Ritrovare i risultati sul disco | Apri l’esperimento e scegli **Apri cartella esperimento**. Con lo ZIP Windows, per impostazione predefinita i risultati sono in `NIPAT\runs`. |

Nella cartella `synthetic-trio`, il `README.md` spiega come provare anche **Contaminazione**, **CPI prenatale** e **CPI postnatale** e confrontare i risultati con quelli attesi. Per confrontare i tempi fra due computer usa i file della sottocartella `timing` e le ripetizioni indicate nel README. Se usi la 0.9.9, estrai lo [ZIP di esempio](../examples/newpat-synthetic-trio.zip) e segui il README per inserire i file a mano.

## Per gli esperimenti successivi

Per esportare i risultati, apri l’esperimento e scegli **Esporta report PDF**. Spunta le analisi da includere e controlla campione o famiglia, marcatori e pannello. Con **Report sintetico** ogni risultato ha una pagina propria. Con **Report dettagliato** ogni risultato inizia su una nuova pagina, con lo spazio necessario per grafici e tabelle. **Sintesi e dettagli** inserisce ogni sintesi subito prima dei relativi dettagli. Premi **Salva PDF** una volta. Ad esempio, selezionando DNP, contaminazione e CPI prenatale ottieni un unico PDF con tre sintesi consecutive.

- **Riferimento.** Per BAM allineati a un genoma umano puoi registrare il FASTA locale con **Aggiungi FASTA locale**. Il download facoltativo da UCSC richiede Internet al primo utilizzo e fornisce hg19 o hg38. Controlla che sequenze e nomi dei cromosomi corrispondano al riferimento dei tuoi BAM. [Scelta del riferimento](GUI.md#choose-a-reference-genome)
- **Stessi parametri su nuovi campioni.** In **Parametri → Salva come profilo**, assegna un nome alle impostazioni. In **Preferenze** puoi sceglierle come valori predefiniti per i nuovi esperimenti. Per riutilizzare anche i file di un esperimento usa **Ripeti**.
- **Più esperimenti.** Puoi avviare altri esperimenti mentre il primo è in corso. In **Attività** ogni esperimento ha il proprio stato. Uno può rimanere **In attesa** finché si liberano CPU e memoria. Più esperimenti contemporanei possono impiegare più tempo sullo stesso computer.
- **Esperimento interrotto.** Attendi che lo stato diventi **Interrotto**, poi scegli **Rimuovi dalla lista**. I file restano sul disco. Puoi riaprire la cartella con **Esperimenti e risultati → Apri risultati esistenti**.

[Guida completa al desktop](GUI.md) · [Installazione Windows](WINDOWS_INSTALLER.md) · [Installazione macOS](MACOS_INSTALLER.md) · [Installazione Ubuntu](LINUX_INSTALLER.md)
