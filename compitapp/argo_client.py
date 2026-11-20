import os
import json
import time
import threading
import requests
from argo_auth import ArgoPassword, ArgoLoginError, ArgoWebSession, get_profiles
from argo_backend import ENDPOINT, api_headers, dashboard_body
from allegati import collegamento_bacheca

def get_studenti():
    raw = os.environ.get('STUDENTI', '[]')
    try:
        studenti = json.loads(raw)
        return [s for s in studenti if s.get('codice_scuola') and (s.get('username') or s.get('accesso') == 'spid')]
    except Exception as e:
        print(f"[ARGO] Errore parsing STUDENTI: {e}")
        return []

_sessions = {}
_session_errors = {}


def _descrivi_profilo(p):
    """Testo breve per i registri (senza token)."""
    parti = []
    for k, v in p.items():
        if k == 'token' or v in (None, ''):
            continue
        if isinstance(v, (str, int)) and len(str(v)) < 60:
            parti.append(f"{k}={v}")
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, (str, int)) and len(str(v2)) < 60 and v2 not in (None, ''):
                    parti.append(f"{k}.{k2}={v2}")
    return ", ".join(parti[:12])


def _scegli_profilo(session, studente):
    """Un account Argo con più figli ha più "profili" (la schermata «Scelta profilo» dell'app DiDUP).
    La libreria usa sempre il primo: qui si sceglie quello indicato dal campo `alunno` (1, 2...)."""
    nome = studente.get('nome', 'default')
    try:
        indice = int(studente.get('alunno') or 0)
    except (TypeError, ValueError):
        indice = 0
    profili = session._argo_profiles
    if len(profili) > 1:
        print(f"[ARGO] {nome}: l'account Argo contiene {len(profili)} profili"
              + ("" if indice else " — compila il campo 'alunno' (1, 2...) per ogni figlio, altrimenti usa sempre il primo"))
        for i, p in enumerate(profili, 1):
            print(f"[ARGO]   profilo {i}: {_descrivi_profilo(p)}")
    _controlla_cambio_profilo(nome, indice if len(profili) > 1 else 0)
    if not indice or not profili:
        return
    if indice > len(profili):
        print(f"[ARGO] {nome}: alunno={indice} ma l'account ha {len(profili)} profili, uso l'ultimo")
        indice = len(profili)
    token = profili[indice - 1].get('token')
    if token:
        session._ArgoFamiglia__token = token
        session._ArgoFamiglia__headers["x-auth-token"] = token
        if profili[indice - 1].get('codMin'):
            session._ArgoFamiglia__headers['x-cod-min'] = profili[indice - 1]['codMin']
        print(f"[ARGO] {nome}: uso il profilo {indice} di {len(profili)}")

def _controlla_cambio_profilo(nome, indice):
    """Se il profilo scelto (campo `alunno`) è cambiato dall'ultima volta, i dati salvati
    appartengono a un altro alunno: si cancellano e lo storico viene ricaricato."""
    try:
        from models import get_db, svuota_studente
        conn = get_db()
        r = conn.execute('SELECT valore FROM meta WHERE chiave=?', (f"profilo:{nome}",)).fetchone()
        precedente = r['valore'] if r else None
        attuale = str(indice or 0)
        # Pulizia una tantum (2.0.5): chi ha usato versioni precedenti con un alunno 2, 3... può avere
        # nel database compiti, voti e lezioni del PRIMO figlio mescolati a quelli giusti, e nessuna
        # versione se ne accorgeva (il profilo risultava già "registrato" senza che i dati fossero puliti).
        chiave_pulizia = f"pulizia_profilo:{nome}"
        pulizia_fatta = conn.execute('SELECT 1 FROM meta WHERE chiave=?', (chiave_pulizia,)).fetchone() is not None
        pulizia_necessaria = (not pulizia_fatta) and attuale not in ('0', '1')
        if (precedente is not None and precedente != attuale) or pulizia_necessaria:
            svuota_studente(conn, nome)
            motivo = "cambio di profilo" if (precedente is not None and precedente != attuale) else "pulizia una tantum dei dati"
            print(f"[ARGO] {nome}: {motivo} (profilo {precedente or '?'} → {attuale}): "
                  "cancello i dati vecchi e ricarico l'anno scolastico")
        conn.execute("INSERT OR REPLACE INTO meta (chiave, valore) VALUES (?, '1')", (chiave_pulizia,))
        conn.execute("INSERT OR REPLACE INTO meta (chiave, valore) VALUES (?, ?)", (f"profilo:{nome}", attuale))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ARGO] {nome}: controllo cambio profilo non riuscito ({e})")


class ArgoSpid(ArgoWebSession):
    """Sessione Argo per chi accede con SPID/CIE: niente utente e password, il token di accesso
    si ottiene rinnovando quello salvato da spid_auth."""

    def __init__(self, school, nome):
        self._nome_spid = nome
        super().__init__(school, 'spid', '')

    def connect(self):
        import spid_auth
        dati = spid_auth.rinnova(self._nome_spid)
        school = self._ArgoFamiglia__school
        self._ArgoFamiglia__login_data = dati
        self._argo_profiles = get_profiles(dati)
        token = self._argo_profiles[0]['token']
        self._ArgoFamiglia__token = token
        self._ArgoFamiglia__headers = api_headers(dati['access_token'], school, token)
        return self


SPID_ETA_MAX = 45 * 60     # il token di accesso dura 1 ora dopo un rinnovo: si ricrea prima
_sessioni_creata = {}
_sessione_lock = threading.RLock()


def get_session(studente):
    nome = studente.get('nome', 'default')
    spid = studente.get('accesso') == 'spid'
    global _sessions
    with _sessione_lock:
        try:
            if spid and nome in _sessions and time.time() - _sessioni_creata.get(nome, 0) > SPID_ETA_MAX:
                _sessions.pop(nome, None)
            if nome not in _sessions:
                if spid:
                    _sessions[nome] = ArgoSpid(studente['codice_scuola'], nome)
                else:
                    _sessions[nome] = ArgoPassword(
                        studente['codice_scuola'],
                        studente['username'],
                        studente['password']
                    )
                _sessioni_creata[nome] = time.time()
                _scegli_profilo(_sessions[nome], studente)
                print(f"[ARGO] ✅ Sessione creata per {nome}")
            _session_errors.pop(nome, None)
            return _sessions[nome]
        except Exception as e:
            import sync_state
            motivo = e.categoria if isinstance(e, ArgoLoginError) else 'accesso'
            _session_errors[nome] = motivo
            sync_state.errore(nome, motivo)
            dettaglio = str(e) if isinstance(e, ArgoLoginError) else "errore_sessione_non_classificato"
            print(f"[ARGO] ❌ Errore sessione {nome}: {dettaglio}")
            _sessions.pop(nome, None)
            return None

def _reset_session(nome):
    with _sessione_lock:
        _sessions.pop(nome, None)
        _sessioni_creata.pop(nome, None)

_cache_dashboard = {}
CACHE_SECONDI = 90
_sezioni_loggate = set()


def _filtra_alunno(studente, data):
    """Un account Argo con più figli restituisce una sezione per alunno in data.dati.
    Con il campo `alunno` (1 = primo, 2 = secondo...) teniamo solo quella dello studente."""
    try:
        dati = data.get('data', {}).get('dati', [])
    except AttributeError:
        return data
    nome = studente.get('nome', 'default')
    if len(dati) <= 1:
        return data
    if nome not in _sezioni_loggate:
        _sezioni_loggate.add(nome)
        print(f"[ARGO] {nome}: l'account Argo contiene {len(dati)} alunni"
              + ("" if studente.get('alunno') else " — compila il campo 'alunno' (1, 2...) per ogni figlio, altrimenti i dati si mescolano"))
    try:
        indice = int(studente.get('alunno') or 0)
    except (TypeError, ValueError):
        indice = 0
    if indice and dati:
        if indice > len(dati):
            print(f"[ARGO] {nome}: alunno={indice} ma l'account ne ha {len(dati)}, uso l'ultimo")
            indice = len(dati)
        copia = dict(data)
        copia['data'] = dict(data['data'])
        copia['data']['dati'] = [dati[indice - 1]]
        return copia
    return data

def fetch_dashboard(studente, giorni=0):
    """Dashboard di Argo. Con `giorni` > 0 chiede le novità dalle ultime `giorni` giornate
    (la richiesta standard restituisce soltanto quelle di oggi); se non riesce usa la standard.
    Il risultato è riusato per qualche secondo: un ciclo di sincronizzazione fa molte letture."""
    nome = studente.get('nome', 'default')
    chiave = (nome, giorni)
    voce = _cache_dashboard.get(chiave)
    if voce and time.time() - voce[0] < CACHE_SECONDI:
        return voce[1]
    data = None
    if giorni:
        try:
            data = _dashboard_dal(studente, giorni)
            if not (isinstance(data, dict) and data.get('data')):
                print(f"[ARGO] Dashboard {nome}: risposta vuota con storico di {giorni} giorni, uso quella standard")
                data = None
        except Exception as e:
            print(f"[ARGO] Dashboard {nome}: storico non disponibile ({e}), uso quella standard")
            _reset_session(nome)
            data = None
    if data is None:
        data = _dashboard_standard(studente)
    if data is not None:
        data = _filtra_alunno(studente, data)
        _cache_dashboard[chiave] = (time.time(), data)
    return data

def _dashboard_standard(studente):
    """Dashboard standard (solo le novità di oggi) — con retry automatico"""
    nome = studente.get('nome', 'default')
    for tentativo in range(3):
        try:
            session = get_session(studente)
            if not session:
                return None
            data = session.dashboard(useExactDatetime=False)
            if data is None and tentativo < 2:
                print(f"[ARGO] Risposta vuota dashboard {nome} — retry {tentativo+1}/3")
                _reset_session(nome)
                continue
            return data
        except ValueError as e:
            print(f"[ARGO] Sessione scaduta {nome} — rinnovo dashboard (tentativo {tentativo+1}/3)")
            _reset_session(nome)
            if tentativo == 2:
                print(f"[ARGO] ❌ Impossibile recuperare dashboard {nome} dopo 3 tentativi")
                return None
        except Exception as e:
            print(f"[ARGO] Errore dashboard {nome}: {e}")
            _reset_session(nome)
            return None
    return None

def fetch_compiti(studente):
    nome = studente.get('nome', '')
    for tentativo in range(3):  # Fino a 3 tentativi
        try:
            session = get_session(studente)
            if not session:
                return {}
            risultato = session.getCompitiByDate()
            if risultato is None and tentativo < 2:
                print(f"[ARGO] Risposta vuota compiti {nome} — retry {tentativo+1}/3")
                _reset_session(nome)
                continue
            return risultato or {}
        except ValueError as e:
            # Risposta JSON vuota — sessione scaduta
            print(f"[ARGO] Sessione scaduta {nome} — rinnovo (tentativo {tentativo+1}/3)")
            _reset_session(nome)
            if tentativo == 2:
                print(f"[ARGO] ❌ Impossibile recuperare compiti {nome} dopo 3 tentativi")
                return {}
        except Exception as e:
            print(f"[ARGO] Errore compiti {nome}: {e}")
            _reset_session(nome)
            return {}
    return {}

def _pick(d, *chiavi, default=''):
    """Primo campo valorizzato tra i nomi candidati (Argo cambia nomi tra versioni)."""
    for k in chiavi:
        v = d.get(k)
        if v not in (None, ''):
            return v
    return default


def _voto_valido(valore, *, verifica_formato=False):
    """True se e' un vero voto. Scarta le annotazioni senza voto (valore 0 / vuoto)."""
    if valore is None:
        return False
    if not isinstance(valore, (str, int, float)) or isinstance(valore, bool):
        if verifica_formato:
            raise ArgoSyncError('Formato valutazione non valido')
        return False
    t = str(valore).strip().replace(',', '.')
    if not t:
        return False
    try:
        numero = float(t)
    except ValueError:
        return t.upper() not in ('N', '-', '--')   # voti a giudizio (es. "Ottimo")
    if not -float('inf') < numero < float('inf'):
        if verifica_formato:
            raise ArgoSyncError('Valutazione numerica non finita')
        return False
    return numero > 0


def fetch_voti(studente, giorni=0):
    """Estrae voti dalla dashboard (lista 'voti', o 'votiGiornalieri' nelle versioni vecchie)"""
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return []
    try:
        voti = []
        dati = dashboard.get('data', {}).get('dati', [])
        for sezione in dati:
            for v in sezione.get('voti', sezione.get('votiGiornalieri')) or []:
                valore = _pick(v, 'valore', 'decValore', 'decVoto', 'codVoto')
                if not _voto_valido(valore):
                    continue
                materia = _pick(v, 'desMateria', 'materia', 'descrizioneMateria')
                if isinstance(materia, dict):
                    materia = _pick(materia, 'descrizione', 'desMateria', 'nome')
                voti.append({
                    'data': _pick(v, 'datGiorno', 'data', 'dataVoto'),
                    'materia': materia or 'Materia',
                    'voto': str(valore),
                    'descrizione': _pick(v, 'desCommento', 'commento', 'descrizione', 'desProva')
                })
        return voti
    except Exception as e:
        print(f"[ARGO] Errore parsing voti: {e}")
        return []

def _bool_arg(v):
    return v is True or str(v).upper() in ('S', 'TRUE', '1')

def chiave_appello(sezione):
    return 'appello' if 'appello' in sezione else 'assenze'


def fetch_assenze(studente, giorni=0):
    """Estrae assenze/ritardi/uscite (lista 'appello', o 'assenze' nelle versioni vecchie)"""
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return []
    try:
        assenze = []
        dati = dashboard.get('data', {}).get('dati', [])
        for sezione in dati:
            for a in sezione.get(chiave_appello(sezione)) or []:
                assenze.append({
                    'data': _pick(a, 'data', 'datAssenza'),
                    'tipo': _pick(a, 'codEvento', default='A'),  # A=assenza, R=ritardo, U=uscita
                    'descrizione': _pick(a, 'descrizione', 'desAssenza'),
                    'giustificata': _bool_arg(_pick(a, 'giustificata', 'flgGiustificata', default='N'))
                })
        return assenze
    except Exception as e:
        print(f"[ARGO] Errore parsing assenze: {e}")
        return []

def fetch_note(studente, giorni=0):
    """Estrae note disciplinari dalla dashboard"""
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return []
    try:
        note = []
        dati = dashboard.get('data', {}).get('dati', [])
        for sezione in dati:
            for n in sezione.get('noteDisciplinari', []):
                note.append({
                    'data': n.get('datNota', ''),
                    'docente': n.get('docente', ''),
                    'testo': n.get('desNota', '')
                })
        return note
    except Exception as e:
        print(f"[ARGO] Errore parsing note: {e}")
        return []

def _msg_bacheca(msg, tipo='bacheca'):
    testo = _pick(msg, 'messaggio', 'desMessaggio')
    titolo = _pick(msg, 'desOggetto', 'titolo', 'oggetto', 'categoria')
    if not titolo:
        titolo = (str(testo).strip().splitlines() or [''])[0][:80] or 'Comunicazione'
    allegati = []
    for a in msg.get('listaAllegati') or []:
        if not isinstance(a, dict):
            continue
        pk = _pick(a, 'pk', 'uid')
        if pk:
            allegati.append({'uid': str(pk), 'nome': str(a.get('nomeFile') or 'Allegato'),
                             'descrizione': str(a.get('descrizioneFile') or ''), 'tipo': tipo})
    # La bacheca personale contiene direttamente il file, senza listaAllegati.
    if tipo == 'alunno' and msg.get('nomeFile') and _pick(msg, 'pk', 'uid'):
        allegati.append({'uid': str(_pick(msg, 'pk', 'uid')), 'nome': str(msg['nomeFile']),
                         'descrizione': '', 'tipo': tipo})
    return {
        'data': _pick(msg, 'data', 'datPubblicazione'),
        'titolo': titolo,
        'testo': testo,
        'mittente': _pick(msg, 'autore', 'desMittente'),
        'uid': str(_pick(msg, 'pk', 'uid')),
        'allegati': allegati,
        'url': collegamento_bacheca(msg.get('url')) if tipo == 'bacheca' else '',
        'eliminato': msg.get('operazione') == 'D',
    }

def fetch_bacheca(studente, giorni=0):
    """Estrae comunicazioni bacheca dalla dashboard"""
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return []
    try:
        bacheca = []
        dati = dashboard.get('data', {}).get('dati', [])
        for sezione in dati:
            for chiave in ('bacheca', 'bachecaAlunno'):
                for msg in sezione.get(chiave, []) or []:
                    bacheca.append(_msg_bacheca(msg, 'alunno' if chiave == 'bachecaAlunno' else 'bacheca'))
        return bacheca
    except Exception as e:
        print(f"[ARGO] Errore parsing bacheca: {e}")
        return []

def link_allegato_bacheca(studente, allegato):
    """Richiede ad Argo un link nuovo a ogni click, usando il profilo selezionato.

    Endpoint e payload sono quelli usati da argofamiglia.getDocumentUrl e
    portaleargo-api.getLinkAllegatoStudente. Non conferma la presa visione.
    """
    nome = studente.get('nome', 'default')
    for tentativo in range(2):
        session = get_session(studente)
        if session is None:
            raise RuntimeError('Sessione Argo non disponibile')
        headers = session._ArgoFamiglia__headers
        payload = {'uid': allegato['uid']}
        endpoint = 'famiglia/downloadallegatobacheca'
        try:
            profilo = requests.get(ENDPOINT + 'profilo', headers=headers, timeout=30, allow_redirects=False)
            profilo.raise_for_status()
            payload['pkScheda'] = profilo.json()['data']['scheda']['pk']
            if allegato.get('tipo') == 'alunno':
                endpoint = 'famiglia/downloadallegatobachecaalunno'
            risposta = requests.post(ENDPOINT + endpoint, headers=headers,
                                     json=payload, timeout=30, allow_redirects=False)
            risposta.raise_for_status()
            dati = risposta.json()
            if dati.get('success') is False or not dati.get('url'):
                raise ValueError('Link Argo non disponibile')
            return dati['url']
        except (requests.RequestException, ValueError, KeyError):
            _reset_session(nome)
            if tentativo:
                raise RuntimeError('Download Argo non disponibile') from None

def fetch_argomenti(studente, giorni=0):
    """Estrae argomenti lezione dalla dashboard"""
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return []
    try:
        argomenti = []
        dati = dashboard.get('data', {}).get('dati', [])
        for sezione in dati:
            materia = sezione.get('materia', '')
            for arg in sezione.get('argomentiLezione', []):
                argomenti.append({
                    'data': arg.get('datGiorno', ''),
                    'materia': materia,
                    'argomento': arg.get('desArgomento', ''),
                    'attivita': arg.get('desAttivita', '')
                })
        return argomenti
    except Exception as e:
        print(f"[ARGO] Errore parsing argomenti: {e}")
        return []

def _estrai_registro(dashboard):
    registro = []
    for sezione in (dashboard or {}).get('data', {}).get('dati', []):
        registro.extend(sezione.get('registro', []))
    return registro

def _dashboard_dal(studente, giorni):
    """Dashboard con "novità dal" spostato indietro di `giorni` giorni.
    La libreria chiede solo le novità di oggi (00:00), quindi il registro contiene
    soltanto le lezioni di oggi: con una data più vecchia Argo restituisce anche i giorni precedenti."""
    import datetime
    import requests
    session = get_session(studente)
    if not session:
        return None
    dal = datetime.datetime.now() - datetime.timedelta(days=giorni)
    risposta = requests.post(
        ENDPOINT + "dashboard/dashboard",
        headers=session._ArgoFamiglia__headers,
        json=dashboard_body(dal.strftime("%Y-%m-%d 00:00:00")),
        timeout=60, allow_redirects=False)
    risposta.raise_for_status()
    return risposta.json()


class ArgoSyncError(Exception):
    """Risposta non verificata: non avanzare il cursore e non cancellare dati locali."""

    def __init__(self, message, categoria='risposta'):
        super().__init__(message)
        self.categoria = categoria


def dashboard_sync(studente, dal):
    """Delta richiesto da una data precisa. Nessun ripiego sulla sola giornata corrente."""
    nome = studente.get('nome', 'default')
    for tentativo in range(2):
        session = get_session(studente)
        if session is None:
            raise ArgoSyncError('Sessione Argo non disponibile', _session_errors.get(nome, 'accesso'))
        try:
            risposta = requests.post(ENDPOINT + 'dashboard/dashboard',
                                     headers=session._ArgoFamiglia__headers,
                                     json=dashboard_body(dal.strftime('%Y-%m-%d %H:%M:%S')),
                                     timeout=(10, 60), allow_redirects=False)
        except requests.RequestException:
            raise ArgoSyncError('Argo non raggiungibile', 'rete') from None
        status = risposta.status_code
        # Only HTTP 401 proves failed authentication. 403 is not a login trigger.
        if status == 401:
            # Preserve the existing SPID refresh lifecycle; recovery here is password-only.
            if studente.get('accesso') == 'spid':
                raise ArgoSyncError('Accesso Argo rifiutato', 'accesso')
            with _sessione_lock:
                if _sessions.get(nome) is session:
                    _reset_session(nome)
            if tentativo == 0:
                print('[SYNC] HTTP=401 recupero_sessione tentativo=1/1')
                continue
            raise ArgoSyncError('Accesso Argo rifiutato', 'accesso')
        if status == 403:
            raise ArgoSyncError('Accesso ai dati non consentito', 'permessi')
        if status == 429:
            raise ArgoSyncError('Limite richieste Argo', 'limite')
        if status >= 500:
            raise ArgoSyncError('Servizio Argo non disponibile', 'servizio')
        try:
            risposta.raise_for_status()
            dati = risposta.json()
        except (requests.RequestException, ValueError):
            raise ArgoSyncError('Argo non ha restituito un aggiornamento verificabile') from None
        break
    if (not isinstance(dati, dict) or ('success' in dati and dati['success'] is not True)
            or not isinstance(dati.get('data'), dict)
            or not isinstance(dati['data'].get('dati'), list) or not dati['data']['dati']):
        raise ArgoSyncError('Risposta dashboard incompleta o rifiutata')
    if any(dati.get(k) is True or dati['data'].get(k) is True for k in ('hasMore', 'has_more', 'parziale')):
        raise ArgoSyncError('Risposta parziale: lo storico rimane da completare')
    sezioni = dati['data']['dati']
    if not all(isinstance(s, dict) for s in sezioni):
        raise ArgoSyncError('Formato dei profili non valido')
    if len(sezioni) > 1:
        try:
            indice = int(studente.get('alunno') or 0)
        except (TypeError, ValueError):
            indice = 0
        if not 1 <= indice <= len(sezioni):
            raise ArgoSyncError('Indicare un numero alunno valido per questo account')
        sezioni = [sezioni[indice - 1]]
    if sezioni[0].get('profiloDisabilitato'):
        raise ArgoSyncError('Profilo Argo disabilitato')
    if any(sezioni[0].get(k) is True for k in ('hasMore', 'has_more', 'parziale')):
        raise ArgoSyncError('Profilo con risposta parziale: storico da completare')
    return sezioni[0]

def fetch_registro(studente, giorni=0):
    """Lezioni del registro (lista di dict con datGiorno, ora, materia, docente).
    Con `giorni` > 0 prova a recuperare anche i giorni passati."""
    nome = studente.get('nome', 'default')
    try:
        registro = _estrai_registro(fetch_dashboard(studente, giorni))
        if registro and giorni:
            giorni_visti = len({str(r.get('datGiorno'))[:10] for r in registro})
            print(f"[ARGO] Registro {nome}: richiesta con storico di {giorni} giorni → {len(registro)} righe su {giorni_visti} giorni")
        if not registro and giorni:
            registro = _estrai_registro(fetch_dashboard(studente))
        return registro
    except Exception as e:
        print(f"[ARGO] Errore lettura registro: {e}")
        return []

def fetch_orario(studente):
    """Orario settimanale ricostruito dalle lezioni del registro (Argo non lo espone direttamente)"""
    from orario_utils import ricostruisci_orario
    return ricostruisci_orario(fetch_registro(studente))

def fetch_promemoria(studente, giorni=0):
    """Estrae promemoria dalla dashboard"""
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return []
    try:
        promemoria = []
        dati = dashboard.get('data', {}).get('dati', [])
        for sezione in dati:
            for p in sezione.get('promemoria', []):
                promemoria.append({
                    'data': p.get('datGiorno', ''),
                    'testo': p.get('desAnnotazioni', ''),
                    'docente': p.get('docente', '')
                })
        return promemoria
    except Exception as e:
        print(f"[ARGO] Errore parsing promemoria: {e}")
        return []


def medie_da_sezione(sezione):
    nomi = {str(m.get('pk')): (m.get('materia') or m.get('desMateria') or m.get('descrizione'))
            for m in sezione.get('listaMaterie') or [] if isinstance(m, dict)}
    mm = sezione.get('mediaMaterie') or {}
    righe = mm.items() if isinstance(mm, dict) else ((str(m.get('pk')), m) for m in mm if isinstance(m, dict))
    materie = {nomi.get(str(pk)) or str(pk): m['mediaMateria'] for pk, m in righe
               if isinstance(m, dict) and m.get('mediaMateria') not in (None, '', 0, '0')}
    generale = sezione.get('mediaGenerale')
    return {'generale': generale, 'materie': materie} if generale not in (None, '') or materie else None


def fetch_medie(studente, giorni=0):
    """Medie calcolate dal portale Argo (le stesse dell'app DiDUP, senza i voti «non fa media»):
    mediaGenerale e mediaMaterie, con listaMaterie per i nomi. None se Argo non le manda."""
    nome = studente.get('nome', 'default')
    dashboard = fetch_dashboard(studente, giorni)
    if not dashboard:
        return None
    try:
        for sezione in dashboard.get('data', {}).get('dati', []):
            return medie_da_sezione(sezione)
    except Exception as e:
        print(f"[ARGO] Errore lettura medie {nome}: {e}")
    return None
