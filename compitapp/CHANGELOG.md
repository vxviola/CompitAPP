# Changelog

## 2.4.4 — errori Argo visibili e avviso Home Assistant

- Avviso persistente in Home Assistant quando il ciclo di sincronizzazione fallisce, con indicazione dell’errore di accesso quando rilevato. Un solo avviso per installazione, senza nomi, credenziali o token; rimozione automatica dopo un ciclo riuscito per tutti i profili. Indipendente dalle notifiche scolastiche configurate per telefono o Telegram.
- Indicatore rosso mantenuto durante i nuovi tentativi dopo un errore; verde solo dopo un controllo completato con successo. Attesa/primo controllo in giallo; errore anche se lo stato non è raggiungibile. Ultimo aggiornamento valido conservato.
- Impostazioni: account configurato distinto da sincronizzazione riuscita. Test connessione sul profilo selezionato, con accesso reale e nessun falso successo dovuto a una lista compiti vuota.
- Lo stato «In esecuzione» dell’app nella pagina di Home Assistant continua a indicare il processo avviato. L’app resta consultabile anche quando Argo non è raggiungibile.
- Verifiche automatiche con risposte Home Assistant e Argo simulate; verifica dell’avviso sull’installazione reale dopo l’aggiornamento.

## 2.4.3 — completamento del nuovo login Argo

- Supportata la pagina HTML «Accesso completato» introdotta nel flusso nativo Argo: viene seguito il link `data-auth-app-redirect` verso l’ultimo passaggio OAuth, anche senza intestazione HTTP Location.
- Il link viene accettato soltanto dalla pagina HTTPS di consenso Argo e soltanto verso l’endpoint OAuth atteso. Nessuna esecuzione di JavaScript, nessun link generico o destinazione esterna.
- Conservati il flusso precedente a reindirizzamenti HTTP, la diagnostica senza segreti e i dati locali in caso di errore.
- Verificati 80 test Python, inclusi nuovo flusso e controlli sui link. Confermato anche un login reale fino all’ottenimento del profilo Argo; recupero dei dati da verificare dopo l’aggiornamento dell’app.

## 2.4.2 — diagnostica accesso Argo

- Login password: gestite risposte senza Location, errori HTTP, timeout, callback e risposte token/profili non valide. Limite di dieci reindirizzamenti.
- Il log ARGO-AUTH riporta fase, passo, codice HTTP, presenza di Location e motivo controllato; non registra URL, credenziali, cookie, token o corpo delle risposte.
- Nessun cambiamento alla configurazione richiesta, al database o al login SPID. Un errore di login conserva dati e cursori.
- Dopo l’aggiornamento, riavviare e condividere soltanto il dettaglio da ARGO-AUTH in poi, senza il nome dello studente. Questa diagnostica non garantisce la risoluzione del login: permette di identificare il passaggio che fallisce.

## 2.4.1 — accesso dalla barra laterale per la famiglia

- Impostato `panel_admin: false`: il pannello Ingress è disponibile anche agli utenti Home Assistant non amministratori. Il valore predefinito di HA lo limitava agli amministratori, anche quando la card era visibile agli altri utenti.
- Accesso tramite login di Home Assistant; non occorre rendere amministratori i familiari. UniScuola mantiene lo spazio condiviso esistente, comprese le impostazioni interne: non introduce profili o permessi separati per utente.
- Dopo l’aggiornamento, mantenere attivo **Mostra nella barra laterale** nella pagina dell’app e ricaricare le sessioni dei familiari.

## 2.4.0 — compiti, zaino, documenti e notifiche Home Assistant

- Compiti completati persistenti per figlio, filtro delle attività da fare e indicazione nella card.
- Checklist zaino: materiali generici o per materia, selezionati dall’orario ricostruito; spunte distinte per giorno e studente.
- Notifiche HA configurabili per figlio, dispositivo e categoria, disattivate inizialmente; prova esplicita e collegamento al pannello dell’app. Telegram resta disponibile.
- Lettura locale di comunicazioni e allegati, preferiti, filtri e promemoria documenti via HA con deduplicazione. Nessuna presa visione inviata ad Argo.
- Ricerca globale in compiti, voti, lezioni, promemoria, comunicazioni e nomi dei file.
- Identificativi Argo per correzioni e cancellazioni; gruppi dei compiti aggiornati senza trasferire spunte tra attività riordinate. Nessuna cancellazione per semplice assenza nel delta.
- Cursori persistenti per categoria, richieste dalla data necessaria dopo intervalli offline, commit atomico di dati e cursore; risposte mancanti, parziali o malformate non completano la categoria.
- Backup SQLite prima della migrazione degli archivi esistenti e prima rilettura silenziosa dell’anno. Record legacy ambigui conservati.
- Azzeramento del registro protetto dal blocco di sincronizzazione. Guide aggiornate. Verifiche con servizi simulati; collaudo finale su Argo e notifiche iOS reali da effettuare.

## 2.3.0 — UniScuola, card Lovelace e documenti su iOS

- Il fork prende il nome **UniScuola**, con riconoscimento esplicito di CompitAPP e ringraziamento a elbarto8383. Nome aggiornato nell’app, nella barra laterale, nelle notifiche Telegram e nei nomi visualizzati dei sensori; identificativi, impostazioni e database mantenuti.
- Palette **Rosa**, **Azzurro** e **Salvia** per ciascun figlio, salvate nel database e riprese dalla scheda tramite gli attributi dei sensori; selettore in alto nell’app, compatibilità con tema chiaro e scuro.
- Nuova scheda Lovelace coordinata con la dashboard: verde salvia, titoli serif, icone, tema chiaro/scuro e layout adattivo. Disponibile come `custom:uniscuola-card`; le card precedenti continuano a funzionare.
- **Apri UniScuola** rileva il pannello reale e naviga all’interno di Home Assistant. `addon_slug` permette di scegliere il fork anche con l’originale installato o senza voce nella barra laterale; errore esplicito quando il collegamento è ambiguo.
- Allegati: tipi MIME corretti e download preparato dentro la bacheca, senza navigazione diretta verso i byte del documento. Menu **Salva o condividi** sui dispositivi compatibili, secondo tap per mantenere l’attivazione utente su iOS, anteprima PDF e download normale negli altri browser.
- Test per MIME, prefissi Ingress, navigazione della card, coesistenza originale/fork e gestione del download/condivisione. Nessuna verifica su un iPhone fisico eseguita nello sviluppo.

## 2.2.0 — una nuova dashboard

- Interfaccia ridisegnata: barra laterale su desktop, menu in basso sul telefono, selettore dei figli sempre disponibile, icone vettoriali e date leggibili.
- Nuova home con compiti di oggi/domani, prossime consegne, ultimi avvisi con conteggio degli allegati, promemoria, voti e lezioni previste per domani dall’orario ricostruito.
- Bacheca con ricerca nel testo e nei nomi dei documenti, filtro per allegati, periodo e intervallo di date, conteggio dei risultati e pulsanti di download accessibili.
- Tema automatico, chiaro e scuro, salvato nel browser. Nessun font o libreria caricato da servizi esterni.
- Calendario, voti, presenze, lezioni e orario aggiornati al nuovo stile, con stati vuoti e navigazione da tastiera.
- Sincronizzazione manuale in background: la pagina resta utilizzabile, un secondo ciclo non parte mentre il primo è attivo. Stato e ora dell’ultimo ciclo riuscito vengono conservati per studente; in caso di errori si segnala il controllo incompleto.
- Link e risorse statiche compatibili con i prefissi Ingress di Home Assistant. Nessun trasferimento di impostazioni o database richiesto per aggiornare il fork dalla versione 2.1.1.

## 2.1.1 — fork vxviola

- Pulsante **Scarica** per ogni allegato della bacheca e per i file della bacheca personale dell’alunno, anche attraverso Ingress di Home Assistant.
- Gli identificativi dei file vengono salvati nel database; il link temporaneo viene richiesto ad Argo al momento del download con la sessione del figlio corretto. Nessuna conferma automatica di presa visione o adesione.
- Aggiornamento automatico del database e rilettura iniziale dell’anno scolastico per recuperare gli allegati degli avvisi esistenti, senza duplicare notifiche. Le comunicazioni condivise tra più figli vengono conservate per ciascuno.
- Download fino a 50 MB, senza inoltrare token Argo al browser o all’archivio file. Gli avvisi ritirati da Argo vengono rimossi alla sincronizzazione.

## 2.1.0

- **Accesso con SPID/CIE (sperimentale).** Per le scuole che hanno tolto l'accesso con utente e password. Nella configurazione dello studente scegli `accesso: spid` (username e password non servono), poi apri la pagina **Configurazione → Collega con SPID**: l'app genera un link, tu accedi con SPID da un computer, copi l'indirizzo finale e lo incolli. Da lì in poi l'app rinnova da sola l'accesso e salva ogni nuovo token di rinnovo subito, in uno spazio privato dell'add-on. Se Argo rifiuta il rinnovo, lo studente risulta «da ricollegare» e i genitori ricevono un solo avviso su Telegram. Non ancora provato a lungo su un account reale: per ora è sperimentale e non si sa quanto duri la catena di rinnovi oltre i 4 giorni circa verificati.

## 2.0.5

- Più figli con lo stesso accesso: pulizia una tantum dei dati del secondo figlio (e successivi). Chi aveva già usato una versione precedente con `alunno` 2 poteva avere nel database compiti, voti e lezioni del primo figlio mescolati a quelli giusti (compiti doppi, orario sbagliato) e nessuna versione li ripuliva. Al primo avvio con questa versione i dati vengono cancellati e riletti da capo; i compiti non ancora scaduti possono arrivare di nuovo una volta su Telegram.

## 2.0.4

- Più figli con lo stesso accesso: se per un figlio (alunno 2, 3…) l'app aveva già salvato dati prima di conoscere il profilo giusto, quei dati erano del primo figlio e restavano a video anche dopo aver impostato `alunno`. Al primo avvio con questa versione vengono cancellati e riletti da capo, senza notifiche.

## 2.0.3

- **Media dei voti uguale a quella di DiDUP.** L'app ora usa le medie calcolate da Argo (generale e per materia), che escludono i voti «non fa media», invece di calcolarle da sola. Se Argo non le manda, si usa il calcolo di prima. Le medie mostrano due decimali (es. 8,15). Contributo di [@CGCM2025](https://github.com/CGCM2025), grazie!
- Cambiando il campo `alunno` di uno studente, i dati salvati del profilo precedente vengono cancellati e l'anno scolastico viene riletto da capo senza notifiche (prima restavano i dati dell'altro bambino).
- Il pulsante di azzeramento del database ora azzera anche i segni di «storico già caricato», quindi dopo lo svuotamento viene riletto tutto l'anno e non solo gli ultimi 7 giorni.
- Nei registri, una volta per studente, compaiono i campi di un voto come arrivano da Argo: aiuta a capire come vengono segnati i voti «non fa media».

## 2.0.2

- Più figli con lo stesso accesso DiDUP (quello in cui, dopo il login, compare la schermata «Scelta profilo»): il campo `alunno` ora sceglie davvero il profilo. Prima l'app usava sempre il primo profilo, quindi entrambi i figli mostravano gli stessi dati. Nei registri, all'avvio, compare l'elenco dei profili trovati (`profilo 1: …`, `profilo 2: …`) e quale viene usato.

## 2.0.1

- Card: il popup ora si apre al centro dello schermo anche con i temi «a vetro» (prima restava tagliato dentro la card). Si chiude toccando fuori, con la X o con Esc.
- Card: il nome dello studente può essere anche solo il primo (es. `Luigi` per `Luigi di Grazia`) se è l'unico a cominciare così; in alternativa si può indicare il nome esatto del sensore con `entity_slug`.

## 2.0.0

- **Nuova card per la dashboard di Home Assistant** (`custom:compitapp-card`), inclusa nell'app e senza dipendenze da HACS: tessere per compiti di oggi e domani, ultimo voto, media, assenze e bacheca. **Toccando una tessera si apre un popup** con il dettaglio: compiti materia per materia, voti con commento, media per materia, assenze da giustificare, comunicazioni. Con più figli ci sono i pulsanti per passare dall'uno all'altro.
- All'avvio l'app copia la card in `/config/www/compitapp/`. Una sola volta devi aggiungerla come risorsa (`/local/compitapp/compitapp-card.js`, tipo «Modulo JavaScript»): istruzioni complete nel README.
- I sensori ora hanno gli elenchi come attributi (`elenco`, `medie`): utili anche per automazioni, notifiche e card tue.
- README riscritto: panoramica, installazione della card, più figli con lo stesso account, esempi di automazioni, FAQ.

## 1.0.14

- Più figli con lo stesso account DiDUP: nuovo campo facoltativo `alunno` dentro ogni studente (1 = primo figlio, 2 = secondo, come nell'app DiDUP). Prima i dati dei figli si mescolavano e su Telegram arrivavano gli stessi compiti. Nei registri l'app avvisa se l'account contiene più alunni e il campo non è compilato.
- I registri non stampano più le password degli studenti all'avvio.

## 1.0.13

- Corretto il problema per cui voti, assenze e media risultavano sempre a zero / N/D: l'app leggeva i nomi dei campi di una vecchia versione di Argo. Ora legge `voti` e `appello` (assenze, ritardi, uscite) e, per sicurezza, anche i vecchi nomi.
- Le annotazioni dei docenti senza voto (valore 0) non vengono più contate come voti: non abbassano più la media e non fanno scattare avvisi di voto basso. Quelle già salvate vengono ripulite in automatico.
- Le comunicazioni in bacheca senza titolo non vengono più scartate (come titolo si usa la categoria).
- Grazie a chi ha segnalato il problema e passato i nomi dei campi reali.

## 1.0.12

- Nei registri dell'app compare sempre quanti voti, assenze e comunicazioni arrivano da Argo e per quanti giorni (es. "Voti Nome: 5 ricevuti da Argo (ultimi 7 giorni)"), così si capisce subito se i dati arrivano o no.

## 1.0.11

- **Voti, assenze e comunicazioni di bacheca ora si caricano anche se precedenti all'installazione**: la richiesta ad Argo restituiva solo le novità di "oggi", quindi un voto o un'assenza compariva soltanto se inserito dopo l'avvio dell'app. Per questo molti vedevano sempre "N/D" e "0" nei sensori. Ora al primo avvio viene letto tutto l'anno scolastico e poi gli ultimi 7 giorni.
- **Nessuna notifica per lo storico**: il primo caricamento è silenzioso, quindi Telegram non viene riempito di voti e assenze vecchi. Le notifiche partono solo per le novità successive.
- **Sensori di Home Assistant aggiornati a fine sincronizzazione** (prima venivano aggiornati solo dopo i compiti, e non se quel giorno non c'erano compiti): ultimo voto, media, assenze e bacheca ora riflettono i dati più recenti.
- Il sensore "avvisi in bacheca" conta le comunicazioni degli ultimi 30 giorni.
- Letture da Argo più leggere: i dati ricevuti vengono riutilizzati per qualche secondo durante lo stesso ciclo.
- Nuova tabella `meta` nel database, creata in automatico (nessuna azione richiesta).

## 1.0.10

- Il recupero dello storico del registro parte subito (al primo controllo dopo l'avvio) invece di attendere fino a un'ora, e si ripete a ogni controllo finché l'archivio delle lezioni non ha almeno 10 giorni.
- Nei registri dell'app compare quanti giorni di lezioni restituisce Argo quando si chiede lo storico.

## 1.0.9

- **Orario completo fin dal primo avvio (tentativo)**: la lettura del registro chiedeva ad Argo solo le novità di oggi, quindi arrivava un solo giorno alla volta. Ora CompitAPP chiede anche i giorni passati (fino a 60 giorni, la prima volta) e ricostruisce subito l'orario completo. Se Argo non risponde in questo modo, usa il metodo precedente, che accumula un giorno alla volta.
- Dopo il primo recupero basta controllare gli ultimi giorni, così le richieste restano leggere.
- Nei registri dell'app compare quanti giorni di lezioni ha ricevuto da Argo.

## 1.0.8

- **Orario che si completa giorno dopo giorno**: Argo restituisce soltanto le lezioni degli ultimi giorni, quindi prima l'orario poteva mostrare un solo giorno e, aggiornandosi, perdere i precedenti. Ora CompitAPP conserva le lezioni viste e ricostruisce l'orario da tutto lo storico: ogni giorno di scuola ne aggiunge uno, e dopo circa una settimana è completo.
- Aggiornamento dell'orario più frequente (ogni ora invece che ogni 6) per non perdere le lezioni del giorno.
- Nei registri dell'app compare un riepilogo per capire cosa restituisce Argo (quante lezioni e di quali giorni).
- Nuova tabella `lezioni_registro` nel database, creata in automatico all'avvio (nessuna azione richiesta).

## 1.0.7

- **Descrizioni chiare nella configurazione**: ogni campo ora ha un nome comprensibile e una spiegazione con esempi (in particolare le frasi personalizzate del riepilogo serale, `reminder_testo_vuoto` e `reminder_testo_chiusura`).
- **Corretta l'opzione `reminder_mostra_orario`** (e `reminder_modalita`): tornava spenta dopo il riavvio perché era dichiarata facoltativa pur avendo un valore predefinito. Ora il valore scelto viene salvato. Se l'avevi attivata prima dell'aggiornamento, controllala e riattivala.
- Allineato lo stesso difetto anche al `chat_id` dello studente.

## 1.0.6

- **Chat ID Telegram per ogni studente**: nella lista `studenti` ogni figlio ha ora il campo facoltativo `chat_id`. Ogni ragazzo riceve solo le proprie notifiche (compiti, riepilogo serale, bacheca, promemoria), mai voti, assenze o note.
- **Corretto l'invio allo studente**: prima il chat ID dello studente veniva mostrato in configurazione ma i messaggi partivano solo verso i genitori. Ora arrivano anche allo studente, come descritto nel README.
- Il vecchio campo `studente_chat_id` continua a funzionare, ma solo se è configurato **un solo** studente.
- La pagina Configurazione mostra nome e chat ID dello studente selezionato.

## 1.0.5

- **Voti con la virgola** (es. 7,5): ora il colore (verde/giallo/rosso) viene calcolato correttamente, prima venivano sempre segnati come insufficienti.
- **Pagina Configurazione**: le "Statistiche database" ora mostrano i dati dello studente selezionato (prima erano sempre a zero).
- Aggiunti gli screenshot nel README.

## 1.0.4

- **Corretto il cambio tra più figli**: con due o più studenti configurati, toccare il nome del figlio faceva uscire dalla PWA e riapriva Home Assistant. Ora il cambio resta dentro CompitAPP e mantiene la pagina in cui ti trovi.
- I comandi Telegram `/resoconto` e `/voti` ora sono separati per studente (un messaggio per ciascun figlio, con il nome giusto).
- Rimosso un nome di studente scritto nel codice nel comando `/voti`.

## 1.0.3

- **Riepilogo serale intelligente**: in modalità `auto` (predefinita) il messaggio "Nessun compito per domani" non viene più inviato quando domani non è giorno di scuola. I giorni di scuola sono riconosciuti dalle lezioni del registro, quindi chi ha lezione il sabato continua a riceverlo; se ci sono compiti, il riepilogo parte sempre.
- **Riepilogo personalizzabile** dalla configurazione: `reminder_modalita` (auto / sempre / solo_con_compiti), `reminder_mostra_orario` (aggiunge l'orario di domani), `reminder_testo_vuoto` e `reminder_testo_chiusura` (frasi tue).
- **Sabato nell'orario**: se lo studente ha lezioni il sabato, compare nella pagina Orario e nel comando `/orario sab`.
- Le nuove opzioni sono facoltative: se non le tocchi, tutto funziona come prima (con il riepilogo `auto`).

## 1.0.2

- **Orario scolastico dinamico**: Argo non espone l'orario nella dashboard, quindi CompitAPP lo ricostruisce dalle lezioni del registro (ultime 3 settimane) e lo aggiorna da solo, anche a inizio anno scolastico.
- Pagina **Orario** e comando Telegram `/orario` leggono i dati dal database invece di un orario scritto nel codice.
- Anno scolastico e nome dello studente calcolati in automatico: niente più "2025/2026" e "Classe 3B" fissi.
- Gestione corretta di righe doppie, giornate corte (es. primi giorni di scuola) e supplenze isolate.
- Nuova tabella `orario` nel database (creata in automatico all'avvio, nessuna azione richiesta).
- Il campo `anno_scolastico` della configurazione non viene più usato.

## 1.0.1

- Versione precedente.
