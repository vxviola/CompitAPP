# Download degli allegati — fork vxviola

Repository del fork: https://github.com/vxviola/CompitAPP.

La versione 2.1.1 aggiunge un pulsante **Scarica** nella pagina Bacheca. I file vengono scaricati sul dispositivo dell’utente su richiesta, senza archivio automatico e senza confermare presa visione o adesione.

## Installazione

Aggiungi `https://github.com/vxviola/CompitAPP` ai repository dello store di Home Assistant e installa la versione di questo fork. Home Assistant considera i repository diversi come app distinte: la configurazione e i dati dell’app originale non vengono trasferiti automaticamente al fork. Copia la tua configurazione nella nuova app e, se usi SPID/CIE, collega il profilo dalla sua pagina Configurazione. Il primo Sync rilegge l’anno scolastico.

## Formato Argo

- `bacheca[].listaAllegati[]`: `pk`, `nomeFile`, `descrizioneFile`. Il link viene risolto con `POST downloadallegatobacheca`, payload `{"uid": "..."}`.
- `bachecaAlunno[]`: `pk`, `nomeFile`. Il profilo selezionato viene letto con `GET profilo`; segue `POST downloadallegatobachecaalunno` con `uid` e `pkScheda`.

Riferimenti verificati nel codice delle librerie: [argofamiglia 0.1.2](https://github.com/salvatore-abello/argofamiglia/blob/main/argofamiglia/argofamiglia.py), [tipi della dashboard didupy](https://github.com/Vinchethescript/didupy/blob/main/didupy/endpoints/types.py) e [portaleargo-api](https://github.com/DTrombett/portaleargo-api/blob/main/src/BaseClient.ts).

Gli endpoint Argo non sono un’API pubblica documentata e possono cambiare. I test usano risposte simulate; il primo download da un account scolastico reale resta da verificare nell’installazione Home Assistant.

## Conservazione e download

Nel database vengono salvati solo identificativo, nome, descrizione e tipo dell’allegato. La migrazione conserva le righe esistenti e sostituisce il vincolo globale su `uid` con `(studente, uid)`, permettendo lo stesso avviso per più figli. Una nuova chiave di storico attiva la rilettura iniziale senza notifiche; i successivi controlli aggiornano anche gli allegati delle righe già presenti.

L’URL di download accetta soltanto un ID locale di comunicazione e un indice di allegato, entrambi verificati sullo studente configurato. I token Argo vengono inviati solo al servizio API. Il successivo download HTTPS non include credenziali e accetta soltanto domini Argo (`portaleargo.it`, `argosoft.it`, `argosoft.cloud`) o Amazon S3 (`amazonaws.com`), verificando anche ogni redirect.

Il file è temporaneo, viene tenuto in memoria fino a 2 MB e su disco oltre tale soglia; il limite complessivo è 50 MB. Viene inviato come allegato con cache disabilitata e poi chiuso. In caso di file ritirato, sessione scaduta o errore di rete compare una pagina di errore senza URL firmati o token. I metadati di un allegato ritirato vengono rimossi alla successiva sincronizzazione.

## Verifica locale

Con Python 3.11 o successivo, dalla cartella del repository:

```sh
python -m venv .venv
# Windows:
.venv/Scripts/python -m pip install -r compitapp/requirements.txt
.venv/Scripts/python -X utf8 -m unittest discover -s tests -v
# Linux/macOS: usa .venv/bin/python
```

La suite verifica migrazione, aggiornamento degli avvisi, separazione tra studenti, bacheca personale, rinnovo della sessione, prefissi Ingress, download binario, errori e limite dimensionale. Non richiede credenziali e non contatta Argo o Telegram.

## UniScuola 2.3.0 e iOS

Il fork ora si chiama UniScuola; il repository e lo slug HA restano invariati. Il pulsante Scarica usa `fetch` con credenziali della stessa origine e cache disabilitata, senza lasciare la bacheca. Prepara un `File` con nome e MIME corretti; i PDF sono riconosciuti anche dalla firma `%PDF-`. Un secondo tap apre Web Share con il file, se `navigator.canShare({files})` lo permette: su iPhone si può scegliere Salva su File. Il download tramite blob è il fallback. L’URL temporaneo resta locale alla pagina e viene revocato alla chiusura; non contiene l’URL firmato Argo. L’anteprima è disponibile solo per PDF riconosciuti dalla firma. HTML e SVG non vengono aperti come documenti attivi.

Test automatici simulano il menu di condivisione e gli errori; non sostituiscono la verifica con l’app Companion su un iPhone reale. Il comportamento di navigazione e Ingress si basa sul [router Home Assistant](https://github.com/home-assistant/frontend/blob/dev/src/common/navigate.ts) e sul [pannello app](https://github.com/home-assistant/frontend/blob/dev/src/panels/app/ha-panel-app.ts).
