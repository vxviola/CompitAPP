# CompitAPP — fork di elbarto8383

**Questo repository è un fork di [elbarto8383/CompitAPP](https://github.com/elbarto8383/CompitAPP), il progetto originale creato da [elbarto8383](https://github.com/elbarto8383).**

**Grazie a elbarto8383 per aver ideato, sviluppato e condiviso CompitAPP:** il collegamento con Argo, l’app per Home Assistant, le notifiche Telegram e le funzioni del registro presenti in questo fork derivano dal suo lavoro. Questo fork, mantenuto da [vxviola](https://github.com/vxviola), aggiunge il download degli allegati della bacheca.

CompitAPP permette di consultare compiti, voti e comunicazioni del registro DiDUP/Argo ScuolaNext da Home Assistant e di ricevere notifiche su Telegram.

[![Aggiungi questo fork a Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fvxviola%2FCompitAPP)

> Progetto della comunità, non ufficiale e non affiliato ad Argo Software. Per le comunicazioni ufficiali della scuola continua a fare riferimento a DiDUP.

## Progetto originale e contributo di questo fork

| Provenienza | Funzioni |
| --- | --- |
| **Progetto originale di elbarto8383** | Integrazione Argo, pagina web, compiti, calendario, voti, assenze, lezioni, orario, gestione di più studenti, bot Telegram, sensori e card Home Assistant, accesso SPID/CIE sperimentale |
| **Aggiunte del fork vxviola — versione 2.1.1** | Pulsante **Scarica** per gli allegati della bacheca, gestione dei file della bacheca personale, aggiornamento dei metadati degli allegati, migrazione del database e test dedicati |

Le modifiche sono descritte nel [changelog](compitapp/CHANGELOG.md). Il codice originale e i relativi crediti restano disponibili nella cronologia Git e nella [licenza MIT](LICENSE).

## Scaricare i file dalla bacheca

1. Apri CompitAPP da Home Assistant.
2. Vai in **Bacheca** e, se hai più figli, scegli lo studente.
3. Sotto ogni comunicazione trovi gli allegati, con nome del file ed eventuale descrizione.
4. Premi **Scarica** per salvare il file sul dispositivo che stai usando.

Il download usa la sessione Argo dello studente selezionato e richiede un nuovo link temporaneo a ogni click. Funziona attraverso l’Ingress di Home Assistant e supporta file fino a **50 MB**.

Al primo avvio la sincronizzazione rilegge l’anno scolastico per recuperare gli allegati delle comunicazioni già presenti. Il database viene aggiornato automaticamente: **non serve azzerarlo**. Per avviare subito il recupero premi **Sync**.

Il download non conferma automaticamente la presa visione o l’adesione alle comunicazioni. I file vengono scaricati su richiesta, senza archiviazione automatica.

Se il file non è disponibile, compare un messaggio di errore. Riprova dalla bacheca e controlla che il file sia ancora accessibile nell’app DiDUP.

## Installare questo fork

Serve un’installazione di Home Assistant con lo store delle app/add-on, come Home Assistant OS o Supervised.

1. Apri **Impostazioni → App/Add-on → Store**.
2. Dal menu **⋮ → Repository**, aggiungi:
   `https://github.com/vxviola/CompitAPP`
3. Ricarica lo store e apri **CompitAPP** dal repository di **vxviola**.
4. Installa l’app, compila la configurazione, salva e avvia.
5. Apri l’interfaccia web e premi **Sync**.

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

All’avvio l’app copia la card in `/config/www/compitapp/`. Aggiungi alle risorse della dashboard `/local/compitapp/compitapp-card.js` come **modulo JavaScript**, poi crea una card manuale:

```yaml
type: custom:compitapp-card
student: Luca
```

Il nome deve corrispondere allo studente configurato in CompitAPP. Per ulteriori esempi sulle funzioni originali consulta il [repository di elbarto8383](https://github.com/elbarto8383/CompitAPP).

## Dati, accesso e limiti

I dati del registro restano nel database locale dell’app. Le richieste vengono inviate ad Argo; se abiliti Telegram, le notifiche passano anche dai server Telegram. L’autore originale e il manutentore del fork non ricevono i tuoi dati tramite servizi propri.

Username, password e token devono restare privati. Proteggi la configurazione e i backup di Home Assistant. Usa l’Ingress di Home Assistant per accedere alla pagina e non esporre la porta 5002 su Internet.

Argo non offre per queste funzioni un’API pubblica documentata: eventuali cambiamenti possono interrompere l’accesso o il download. Il fork usa librerie della comunità e non sostituisce l’app ufficiale.

I download della versione 2.1.1 sono stati verificati con test automatici e risposte Argo simulate; la verifica con un account scolastico reale deve essere effettuata nella propria installazione.

## Sviluppo e verifiche

Il codice dell’app si trova in `compitapp/`. Con Python 3.11 o successivo:

```sh
python -m venv .venv
# Windows
.venv/Scripts/python -m pip install -r compitapp/requirements.txt
.venv/Scripts/python -X utf8 -m unittest discover -s tests -v
# Linux/macOS: sostituisci .venv/Scripts/python con .venv/bin/python
```

I test non richiedono credenziali e non contattano Argo o Telegram. Coprono migrazione del database, allegati, separazione tra studenti, download e prefissi Ingress. I dettagli sono in [docs/download-bacheca.md](docs/download-bacheca.md).

## Segnalazioni, ringraziamenti e licenza

Per problemi introdotti dalle modifiche di questo fork, apri una segnalazione su [vxviola/CompitAPP](https://github.com/vxviola/CompitAPP). Rimuovi sempre dati scolastici, username, password, token e Chat ID prima di condividere log o schermate.

**Un ringraziamento speciale a [elbarto8383](https://github.com/elbarto8383): senza il suo lavoro e la scelta di renderlo disponibile, questo fork non esisterebbe.** Grazie anche ai contributori del progetto originale, tra cui [CGCM2025](https://github.com/CGCM2025) per il contributo al calcolo delle medie Argo.

Se vuoi sostenere l’autore originale, il suo link è [Offri un caffè a elbarto8383](https://paypal.me/elbarto83).

Distribuito con [licenza MIT](LICENSE), conservando l’attribuzione del progetto originale.
