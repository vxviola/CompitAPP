# UniScuola 2.4: uso e aggiornamento

Aggiorna il fork già installato dallo store di Home Assistant, senza disinstallare o azzerare il database. Configurazione, entità `sensor.compitapp_*` e identificativo `compitapp` sono mantenuti. L’app originale può restare installata per sicurezza. Ricarica l’interfaccia dopo l’aggiornamento.

## Compiti completati e zaino

Spunta i compiti nella home o nel calendario. Il filtro **Solo da fare** nasconde quelli completati. Le spunte restano nel database e sono separate per figlio; non vengono inviate alla scuola. La card mostra il completamento nei dettagli dopo il successivo aggiornamento dei sensori. Se usi la card, aggiorna la risorsa esistente a `/local/uniscuola/uniscuola-card.js?v=240` oppure al vecchio percorso `/local/compitapp/compitapp-card.js?v=240`, senza aggiungere una seconda risorsa.

In **Prepara lo zaino** scegli il giorno e aggiungi i materiali. **Ogni giorno** li mostra sempre; una materia li mostra quando compare nell’orario ricostruito per quel giorno. Senza un orario disponibile vengono mostrati solo i materiali generici. Le spunte valgono per la data scelta e il figlio selezionato; i materiali restano disponibili nei giorni successivi. L’orario ricostruito può differire da quello ufficiale della scuola.

## Notifiche nell’app Home Assistant

1. Collega l’app Companion del telefono al tuo Home Assistant e abilita le sue notifiche.
2. Apri UniScuola, seleziona il figlio e vai in **Impostazioni**.
3. In **Notifiche nell’app Home Assistant**, premi **Carica dispositivi** e scegli il telefono del genitore. I servizi disponibili sono `notify.mobile_app_*`; è disponibile anche la notifica persistente di HA.
4. Seleziona le categorie, attiva le notifiche per il figlio e premi **Salva notifiche**.
5. Premi **Invia una prova** e verifica sul telefono. Ripeti per gli altri figli, scegliendo eventualmente un destinatario diverso.

Nessun telefono viene scelto automaticamente. Le notifiche sono inizialmente disattivate e non sostituiscono Telegram. Un singolo destinatario è configurabile per figlio. La prima importazione dello storico resta silenziosa. I messaggi successivi riguardano le nuove righe importate; una correzione di un voto esistente non genera una nuova notifica.

Il tocco di una notifica mobile apre il pannello di UniScuola e il figlio interessato, quando il router di Home Assistant e il contesto Ingress lo consentono. Per le comunicazioni si apre l’avviso specifico. Non vengono inclusi token Ingress nei messaggi. La consegna effettiva dipende dai servizi e dalle autorizzazioni del telefono; una risposta positiva del servizio HA non certifica che il dispositivo abbia mostrato il messaggio. Il collaudo su HA e iOS reali resta necessario.

## Letture, preferiti e promemoria

In bacheca puoi segnare **Comunicazione letta**, marcare ciascun allegato come **Letto**, salvare i preferiti e filtrare gli avvisi. **Da leggere** include anche una comunicazione già letta con almeno un allegato ancora da leggere.

**Ricordamelo il** salva una data locale. Abilitando la categoria **Documenti da leggere** nelle notifiche HA, al primo controllo del registro da quella data viene inviato un promemoria se l’avviso o qualche allegato è ancora da leggere. Viene inviato una sola volta per avviso e data; un invio fallito viene ritentato al controllo successivo. Cambiare la data permette un nuovo promemoria. Non è un avviso a un’ora precisa.

Queste spunte non inviano presa visione, adesione o conferme ad Argo. Continua a usare DiDUP per gli adempimenti richiesti dalla scuola.

## Ricerca globale

**Ricerca** consulta i dati locali del figlio selezionato: compiti, voti, lezioni, promemoria, comunicazioni e nomi degli allegati. Ignora accenti e maiuscole. Non legge il contenuto dei PDF e non effettua una nuova richiesta ad Argo. Mostra fino a 30 risultati per categoria; restringi il testo quando ne esistono altri.

## Correzioni, cancellazioni e recupero offline

La sincronizzazione usa gli identificativi originali quando disponibili. Corregge le righe corrispondenti e rimuove quelle con una cancellazione esplicita di Argo. Nei compiti, la lista esplicita di un singolo registro aggiorna solo quel gruppo; una risposta senza nuove righe non cancella il resto dell’archivio. Le cancellazioni vengono ricordate per non ripristinare eventi più vecchi.

Ogni categoria salva dati e cursore nella stessa transazione SQLite. Il punto di ripartenza è l’inizio della richiesta riuscita, con sette giorni di sovrapposizione alla rilettura successiva; un intervallo offline più lungo viene quindi richiesto dall’ultimo punto conservato. Categorie assenti, formati malformati e risposte dichiarate parziali mantengono il cursore precedente. L’ora dell’ultimo controllo completo non viene aggiornata se una categoria fallisce.

Al primo avvio, prima della migrazione di un database esistente, viene creata una copia SQLite coerente in `/data/compitapp.db.prima-eventi.sqlite` (o accanto al percorso DB personalizzato). È una copia una tantum prima della migrazione; non sostituisce i backup periodici di HA. L’anno scolastico corrente viene poi riletto senza notificare lo storico. Non occorre azzerare i dati.

I vecchi record privi di ID vengono associati solo quando il confronto è univoco. I casi ambigui sono conservati e possono apparire duplicati: senza gli identificativi originari non è possibile ricostruirne con certezza la storia. Per i compiti senza ID proprio, un riordino della lista conserva le spunte attraverso il confronto del contenuto; modifiche indistinguibili non possono essere risolte con certezza.

Le API usate dalla comunità non documentano una prova di completezza dello storico: la validazione rileva gli errori e i segnali di risposta parziale noti, ma non può identificare un taglio silenzioso lato Argo. La versione è verificata con risposte simulate e dati dimostrativi; confronta i risultati con DiDUP nel primo collaudo reale.
