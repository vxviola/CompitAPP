# Dashboard UniScuola

La nuova interfaccia usa gli stessi dati e le stesse opzioni del fork 2.1.1. Aggiornando l’app già installata, configurazione, credenziali e database restano nella sua cartella privata. Non occorre reinstallare o azzerare il registro.

## Cosa trovi nella home

- Il selettore dello studente rimane nella barra superiore.
- Il diario mostra per impostazione iniziale i compiti di domani; la scheda Oggi permette di cambiare giorno.
- All’orizzonte raccoglie le prossime consegne; i promemoria compaiono quando disponibili.
- Dalla scuola mostra gli ultimi tre avvisi e il numero di allegati. Un collegamento apre la bacheca già filtrata sui documenti.
- Medie e voti provengono dai dati disponibili del registro. L’orario di domani è ricostruito dalle lezioni archiviate, come nella versione originale, e non sostituisce il calendario ufficiale della scuola.

## Ricerca e documenti

Nella Bacheca puoi cercare parole del titolo, del messaggio, del mittente e dei nomi degli allegati. La ricerca ignora maiuscole e accenti. Puoi combinare il testo con Solo con allegati, un periodo recente o un intervallo di date. Azzera filtri ripristina l’elenco completo. I documenti continuano a usare il download autenticato introdotto nella 2.1.1.

## Tema e telefono

Il pulsante del tema passa tra Automatico, Chiaro e Scuro. La preferenza è salvata solo nel browser; Automatico segue le impostazioni del dispositivo. Sul telefono quattro sezioni principali sono nel menu in basso; Altro contiene anche Orario, Presenze, Lezioni, Prepara lo zaino, Ricerca e Impostazioni. I comandi funzionano anche da tastiera e il contenuto è consultabile senza richieste a CDN, librerie o servizi di font.

## Aggiornamento del registro

Aggiorna avvia un controllo in background. Un blocco condiviso con lo scheduler impedisce di eseguire due cicli nello stesso processo. Durante il controllo la pagina resta consultabile. Il browser interroga lo stato e aggiorna i messaggi; quando il controllo manuale termina con successo ricarica i dati.

L’ora indicata è quella dell’ultimo ciclo completato senza errori segnalati dalle funzioni di sincronizzazione, non la data dell’ultimo compito inserito. In caso di errore l’ultimo successo rimane visibile e il controllo risulta incompleto. Questa informazione non certifica che Argo abbia pubblicato tutti i dati attesi: se il registro restituisce un elenco legittimamente vuoto, viene mostrato come tale.

La prima esecuzione dopo l’aggiornamento salva il nuovo stato. I dettagli sono conservati in chiavi `sync_ui:<studente>` nella tabella `meta` già esistente.

## Verifica

La suite locale copre le pagine con e senza dati, la separazione tra studenti, gli URL diretti e Ingress, le risorse statiche, l’escape del testo della scuola e gli esiti della sincronizzazione. La verifica nel browser usa dati dimostrativi e controlla ricerca, filtri combinati, download, cambio studente, schede dei compiti e navigazione mobile. I test non accedono a un registro reale.

## Funzioni personali dalla 2.4.0

Compiti completati, zaino, letture dei documenti, preferiti, promemoria e notifiche HA sono descritti nella [guida alla versione 2.4](funzioni-2.4.md). Le preferenze sono separate per figlio e salvate nel database locale.
