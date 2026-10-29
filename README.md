# UniScuola — fork di CompitAPP di elbarto8383

**UniScuola è un fork di [elbarto8383/CompitAPP](https://github.com/elbarto8383/CompitAPP), il progetto originale creato da [elbarto8383](https://github.com/elbarto8383).**

**Grazie a elbarto8383 per aver ideato, sviluppato e condiviso CompitAPP:** il collegamento con Argo, l’app per Home Assistant, le notifiche Telegram e le funzioni del registro presenti in questo fork derivano dal suo lavoro. Questo fork, mantenuto da [vxviola](https://github.com/vxviola), aggiunge una nuova dashboard famiglia, la scheda Lovelace coordinata e il download degli allegati della bacheca.

UniScuola permette di consultare compiti, voti e comunicazioni del registro DiDUP/Argo ScuolaNext da Home Assistant e di ricevere notifiche su Telegram e nell’app Home Assistant.

[![Aggiungi questo fork a Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fvxviola%2FCompitAPP)

[☕ Offrimi un caffè su PayPal](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=vxviola%40gmail.com&item_name=Supporto%20a%20UniScuola&currency_code=EUR)

Se vuoi sostenere lo sviluppo di questo fork, puoi offrirmi un caffè tramite PayPal all’indirizzo **vxviola@gmail.com**.

> Progetto della comunità, non ufficiale e non affiliato ad Argo Software. Per le comunicazioni ufficiali della scuola continua a fare riferimento a DiDUP.

![Dashboard UniScuola in tema Rosa, con dati dimostrativi](https://raw.githubusercontent.com/vxviola/CompitAPP/main/docs/screenshots/uniscuola-dashboard-rosa.jpg)

## Progetto originale e contributo di questo fork

| Provenienza | Funzioni |
| --- | --- |
| **Progetto originale di elbarto8383** | Integrazione Argo, pagina web, compiti, calendario, voti, assenze, lezioni, orario, gestione di più studenti, bot Telegram, sensori e card Home Assistant, accesso SPID/CIE sperimentale |
| **Aggiunte del fork vxviola — versione 2.4.0** | Nuova dashboard, card Lovelace coordinata, temi Rosa/Azzurro/Salvia per figlio, modalità chiara/scura, download e condivisione file, filtri in bacheca, compiti completati, checklist zaino, documenti da leggere, ricerca globale e notifiche HA |

Le modifiche sono descritte nel [changelog](compitapp/CHANGELOG.md). Il codice originale e i relativi crediti restano disponibili nella cronologia Git e nella [licenza MIT](LICENSE).

## Una nuova dashboard per la famiglia

La versione **2.4.0** mette in primo piano i compiti di domani, le prossime consegne e le comunicazioni della scuola. Il selettore dei figli rimane sempre disponibile. Sul telefono le sezioni principali sono nel menu in basso; su desktop trovi una barra laterale.

La bacheca permette di cercare nei messaggi e nei nomi dei file, filtrare per allegati e scegliere un periodo o un intervallo di date. Il tema può seguire il dispositivo oppure essere impostato su chiaro o scuro. Il pulsante **Aggiorna** lavora in background e mostra l’ora dell’ultimo controllo riuscito o un messaggio se il controllo è incompleto.

Se usi già questo fork, aggiorna l’app dallo store di Home Assistant: **impostazioni e database restano conservati**. Non occorre reinstallare. Dopo l’aggiornamento ricarica la pagina per caricare il nuovo aspetto. [Guida alla dashboard](docs/dashboard.md).

## Novità della versione 2.4.0

- **Compiti completati:** spunta le attività dalla home o dal calendario; puoi mostrare solo quelle da fare. Lo stato resta salvato per ciascun figlio.
- **Prepara lo zaino:** crea materiali da portare ogni giorno o per una materia. La checklist segue l’orario ricostruito; le spunte sono separate per giorno e per figlio.
- **Notifiche Home Assistant:** in **Impostazioni → Notifiche nell’app Home Assistant**, premi **Carica dispositivi**, scegli il telefono del genitore, seleziona le categorie, attiva e salva. Poi usa **Invia una prova**. Le notifiche sono disattivate finché non le configuri, separatamente per ogni figlio; Telegram resta disponibile.
- **Documenti da leggere:** segna comunicazioni e singoli allegati come letti, salva i preferiti e scegli una data in **Ricordamelo il**. Il promemoria viene inviato via HA al primo controllo utile da quella data, se abiliti la categoria documenti e ci sono elementi ancora da leggere. Le spunte sono locali: non inviano la presa visione ad Argo.
- **Ricerca globale:** cerca nel registro del figlio selezionato tra compiti, voti, lezioni, promemoria, comunicazioni e nomi degli allegati, ignorando accenti e maiuscole.

La sincronizzazione ora riconosce correzioni e cancellazioni tramite gli identificativi Argo e salva un punto di ripartenza per categoria. Un’interruzione prolungata riparte dall’ultimo controllo riuscito con una sovrapposizione di sette giorni. Una risposta incompleta o non valida non fa avanzare la categoria interessata.

Al primo avvio viene creata una copia coerente del database esistente in `/data/compitapp.db.prima-eventi.sqlite`, poi l’anno scolastico viene riletto senza notificare lo storico. Non reinstallare e non azzerare il database. I vecchi record senza ID vengono associati solo quando il confronto è univoco; i casi ambigui sono conservati e potrebbero richiedere una verifica manuale. [Guida alle nuove funzioni](https://github.com/vxviola/CompitAPP/blob/main/docs/funzioni-2.4.md).

![Checklist zaino di UniScuola con dati dimostrativi](https://raw.githubusercontent.com/vxviola/CompitAPP/main/docs/screenshots/uniscuola-zaino.jpg)

## Qualche schermata

Le immagini usano esclusivamente **dati dimostrativi**. I colori si possono scegliere separatamente per ciascun figlio.

| Dashboard in tema Azzurro | Scheda Lovelace coordinata |
| --- | --- |
| ![Dashboard UniScuola in tema Azzurro](https://raw.githubusercontent.com/vxviola/CompitAPP/main/docs/screenshots/uniscuola-dashboard-azzurro.jpg) | ![Card UniScuola con palette Rosa e Azzurro](https://raw.githubusercontent.com/vxviola/CompitAPP/main/docs/screenshots/uniscuola-card-lovelace.jpg) |

Sul telefono, il selettore dei figli e le sezioni principali restano a portata di mano:

<p align="center"><img src="https://raw.githubusercontent.com/vxviola/CompitAPP/main/docs/screenshots/uniscuola-mobile-rosa.jpg" alt="UniScuola su telefono: tema Rosa e navigazione in basso" width="290"></p>

## Scaricare i file dalla bacheca

1. Apri UniScuola da Home Assistant.
2. Vai in **Bacheca** e, se hai più figli, scegli lo studente.
3. Sotto ogni comunicazione trovi gli allegati, con nome del file ed eventuale descrizione.
4. Premi **Scarica**, attendi la preparazione e poi **Salva o condividi** (su iPhone: **Salva su File**) oppure **Scarica il file** negli altri browser.

Il download usa la sessione Argo dello studente selezionato e richiede un nuovo link temporaneo a ogni click. Funziona attraverso l’Ingress di Home Assistant e supporta file fino a **50 MB**.

Al primo avvio la sincronizzazione rilegge l’anno scolastico per recuperare gli allegati delle comunicazioni già presenti. Il database viene aggiornato automaticamente: **non serve azzerarlo**. Per avviare subito il recupero premi **Aggiorna**.

Il download non conferma automaticamente la presa visione o l’adesione alle comunicazioni. I file vengono scaricati su richiesta, senza archiviazione automatica.

Se il file non è disponibile, compare un messaggio di errore. Riprova dalla bacheca e controlla che il file sia ancora accessibile nell’app DiDUP.

## Installare questo fork

**Accesso della famiglia:** dalla versione **2.4.1**, UniScuola è disponibile nella barra laterale anche agli utenti Home Assistant non amministratori. L’amministratore deve attivare **Mostra nella barra laterale** nella pagina dell’app; dopo l’aggiornamento, ricarica le sessioni dei familiari. Se necessario, riattiva quell’interruttore. Non occorre promuovere gli account ad amministratori. L’app è uno spazio condiviso: tutti gli utenti HA che la aprono accedono agli studenti configurati e alle impostazioni interne; non ci sono profili o permessi separati per utente.

Serve un’installazione di Home Assistant con lo store delle app/add-on, come Home Assistant OS o Supervised.

1. Apri **Impostazioni → App/Add-on → Store**.
2. Dal menu **⋮ → Repository**, aggiungi:
   `https://github.com/vxviola/CompitAPP`
3. Ricarica lo store e apri **UniScuola** dal repository di **vxviola**.
4. Installa l’app, compila la configurazione, salva e avvia.
5. Apri l’interfaccia web e premi **Aggiorna**.

Puoi anche usare il pulsante “Aggiungi questo fork a Home Assistant” all’inizio del README.

### Se usi già la versione originale

Home Assistant identifica le app dei due repository come installazioni distinte. **Configurazione, database e collegamento SPID non vengono trasferiti automaticamente** dal progetto originale al fork.

Conserva una copia della configurazione originale, riportala nell’app del fork e, se usi SPID/CIE, collega il profilo dalla nuova installazione. Il primo Sync rilegge lo storico dell’anno scolastico. Evita di tenere attivi contemporaneamente i due bot Telegram con lo stesso token.

Per aggiornare un’installazione già proveniente da questo fork, verifica gli aggiornamenti nello store e aggiorna l’app. Le migrazioni del database vengono applicate all’avvio.

## Configurazione

Esempio con uno studente e accesso tramite username e password:

```yaml
telegram_token: ""
genitore1_nome: "Genitore 1"
genitore1_chat_id: ""
genitore2_nome: "Genitore 2"
genitore2_chat_id: ""
studente_nome: "Studente"
studente_chat_id: ""
soglia_voto_alert: 7
orario_reminder_sera: "20:00"
polling_intervallo_minuti: 30
reminder_modalita: "auto"
reminder_mostra_orario: false
studenti:
  - nome: "Luca"
    codice_scuola: "SC12345"
    username: "utente_didup"
    password: "password_didup"
```

Per usare solo la pagina web puoi lasciare vuoti i campi Telegram. Il codice scuola si trova nel profilo DiDUP o si richiede alla segreteria. Per ottenere il Chat ID di Telegram, avvia il tuo bot e inviagli `/start`.

### Più figli con lo stesso account

Aggiungi una voce per ogni figlio e indica il campo `alunno`, seguendo l’ordine della schermata “Scelta profilo” di DiDUP:

```yaml
studenti:
  - nome: "Anna"
    codice_scuola: "SC12345"
    username: "account_famiglia"
    password: "password_didup"
    alunno: 1
  - nome: "Luca"
    codice_scuola: "SC12345"
    username: "account_famiglia"
    password: "password_didup"
    alunno: 2
```

Il campo facoltativo `chat_id` dentro ciascuno studente imposta le notifiche Telegram per quel figlio. Il vecchio `studente_chat_id` è adatto a un solo studente.

### Accesso SPID/CIE — sperimentale

Se la scuola richiede SPID o CIE, configura lo studente con:

```yaml
studenti:
  - nome: "Luca"
    codice_scuola: "SC12345"
    accesso: spid
```

Apri **Configurazione → Collega con SPID** e segui le istruzioni della pagina. L’app rinnova l’accesso e conserva i token nello spazio privato dell’add-on. Se Argo rifiuta il rinnovo, occorre ripetere il collegamento.

Questa funzione proviene dal progetto originale ed è sperimentale: la durata del collegamento dipende anche da Argo.

## Funzioni ereditate da CompitAPP

- **Pagina web:** compiti di oggi e domani, calendario, voti, bacheca, assenze, lezioni e configurazione.
- **Orario:** ricostruito dalle lezioni effettivamente presenti nel registro.
- **Telegram:** notifiche per nuovi compiti, voti, assenze, note, comunicazioni e promemoria, con riepilogo serale.
- **Più studenti:** configurazione e consultazione per ciascun figlio.
- **Home Assistant:** sensori per compiti, ultimo voto, medie, assenze e bacheca, con card dedicata.

I destinatari studente ricevono compiti, riepilogo, bacheca e promemoria; voti, assenze e note sono riservati ai destinatari genitore.

Comandi del bot: `/start`, `/chatid`, `/resoconto`, `/orario`, `/voti` e `/help`.

### Card Home Assistant

La scheda Lovelace riprende lo stile di UniScuola: verde salvia, superfici chiare, titoli serif, tema scuro e tessere con i dettagli del registro. Il pulsante **Apri UniScuola** usa il pannello di Home Assistant, che gestisce la sessione Ingress.

All’avvio l’app copia la nuova risorsa in `/config/www/uniscuola/`. Aggiungi **una sola** risorsa come **modulo JavaScript**:

```text
/local/uniscuola/uniscuola-card.js?v=240
```

Poi crea una card manuale:

```yaml
type: custom:uniscuola-card
students:
  - name: Luca
  - name: Anna
addon_slug: ee1c5e4d_compitapp
theme: auto
```

I nomi devono corrispondere agli studenti configurati nell’app. Per scegliere **Salvia**, **Rosa** o **Azzurro** usa il selettore accanto al pulsante del tema nella barra dell’app: la scelta viene salvata per ciascun figlio nel database e condivisa con tutti i dispositivi. La card la riceve nei sensori al prossimo aggiornamento del registro (puoi premere **Aggiorna** per anticiparlo). Nella card puoi anche forzare `palette: rosa` oppure `palette: azzurro` per un singolo elemento di `students` o per tutta la scheda. `theme` accetta `auto`, `light` o `dark`; `auto` segue il tema di Home Assistant.

`addon_slug` è l’identificativo dell’app installata: lo trovi nell’indirizzo aperto da **Apri interfaccia web** o nella pagina dell’app. Per questo fork è normalmente `ee1c5e4d_compitapp`: mantienilo anche dopo il cambio di nome. Se hai abilitato **Mostra nella barra laterale** e c’è una sola CompitAPP/UniScuola, il collegamento viene rilevato anche senza questo campo. Con originale e fork presenti, specifica il fork per evitare ambiguità. Puoi usare anche `open_url` con il percorso locale del pannello, ad esempio `/ee1c5e4d_compitapp`.

**Se usi già la card precedente:** continua a funzionare con `type: custom:compitapp-card` e `/local/compitapp/compitapp-card.js`. Dopo l’aggiornamento cambia l’URL della risorsa esistente in `/local/compitapp/compitapp-card.js?v=240` e ricarica la dashboard; evita di aggiungere una seconda risorsa. Non serve ricreare le card. Il vecchio esempio `open_url: /hassio/ingress/compitapp` viene sostituito dal rilevamento del pannello; se mantieni anche l’app originale, imposta `addon_slug` come sopra.

### Aggiornare a UniScuola e salvare i documenti su iPhone

UniScuola 2.4.0 aggiorna la stessa app del fork: gli identificativi interni, il database, le impostazioni e le entità `sensor.compitapp_*` restano invariati. Anche l’indirizzo del repository resta `https://github.com/vxviola/CompitAPP`. Non disinstallare il fork e non rimuovere l’originale conservato per sicurezza.

In Home Assistant vai allo **store delle app/add-on → menu ⋮ → Controlla aggiornamenti**, poi apri il fork e installa la versione 2.4.0. Se non compare, ricarica lo store. Dopo l’avvio il nome visualizzato sarà **UniScuola**. Ricarica anche l’app Companion per aggiornare i file dell’interfaccia.

In bacheca tocca **Scarica**, attendi che il file sia pronto e poi **Salva o condividi**. Su iPhone scegli **Salva su File** nel menu di condivisione. Il secondo tocco serve a consentire l’apertura del menu anche quando Argo impiega tempo a preparare il documento. Per i PDF è disponibile anche **Anteprima PDF**. Se la condivisione non è supportata dal browser, compare il download normale con un suggerimento per usare Safari.

La correzione è verificata con risposte simulate, tipi MIME, flussi di condivisione e browser desktop; la conferma sul dispositivo iOS reale resta da effettuare.

## Errori di accesso e sincronizzazione

Dalla versione **2.4.4**, un controllo fallito produce un avviso persistente nelle notifiche di Home Assistant. Non occorre configurare Telegram o un telefono. L’avviso è unico per installazione e viene rimosso automaticamente dopo una sincronizzazione completa riuscita per tutti i profili; se Home Assistant non è raggiungibile, l’invio viene ritentato al ciclo successivo.

Dentro UniScuola il rosso resta visibile anche durante un nuovo tentativo, fino al successo. L’attesa è gialla; il verde indica l’ultimo controllo completato con successo. L’ora dell’ultimo aggiornamento valido resta disponibile. La dicitura **In esecuzione** nella pagina app/add-on di Home Assistant indica soltanto che il processo è avviato: l’avviso segnala separatamente i problemi del registro.

## Dati, accesso e limiti

I dati del registro restano nel database locale dell’app. Le richieste vengono inviate ad Argo; se abiliti Telegram, le notifiche passano anche dai server Telegram. L’autore originale e il manutentore del fork non ricevono i tuoi dati tramite servizi propri.

Username, password e token devono restare privati. Proteggi la configurazione e i backup di Home Assistant. Usa l’Ingress di Home Assistant per accedere alla pagina e non esporre la porta 5002 su Internet.

Argo non offre per queste funzioni un’API pubblica documentata: eventuali cambiamenti possono interrompere l’accesso o il download. Il fork usa librerie della comunità e non sostituisce l’app ufficiale.

I download sono coperti da test automatici con risposte Argo simulate. La compatibilità con ogni versione dell’app Companion va verificata sul dispositivo utilizzato.

## Sviluppo e verifiche

Il codice dell’app si trova in `compitapp/`. Con Python 3.11 o successivo:

```sh
python -m venv .venv
# Windows
.venv/Scripts/python -m pip install -r compitapp/requirements.txt
.venv/Scripts/python -X utf8 -m unittest discover -s tests -v
node --test tests/test_card.cjs tests/test_allegati.cjs tests/test_funzioni.cjs
# Linux/macOS: sostituisci .venv/Scripts/python con .venv/bin/python
```

I test non richiedono credenziali e non contattano Argo, Telegram o un Home Assistant reale. Coprono migrazione e backup, correzioni/cancellazioni, cursori, transazioni, funzioni personali, notifiche simulate, allegati, separazione tra studenti e prefissi Ingress. I dettagli sono in [docs/download-bacheca.md](docs/download-bacheca.md).

## Segnalazioni, ringraziamenti e licenza

Per problemi introdotti dalle modifiche di questo fork, apri una segnalazione su [vxviola/CompitAPP](https://github.com/vxviola/CompitAPP). Rimuovi sempre dati scolastici, username, password, token e Chat ID prima di condividere log o schermate.

**Un ringraziamento speciale a [elbarto8383](https://github.com/elbarto8383): senza il suo lavoro e la scelta di renderlo disponibile, questo fork non esisterebbe.** Grazie anche ai contributori del progetto originale, tra cui [CGCM2025](https://github.com/CGCM2025) per il contributo al calcolo delle medie Argo.

Se vuoi sostenere l’autore originale, il suo link è [Offri un caffè a elbarto8383](https://paypal.me/elbarto83).

Distribuito con [licenza MIT](LICENSE), conservando l’attribuzione del progetto originale.
