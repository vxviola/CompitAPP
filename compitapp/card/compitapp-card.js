(function () {
'use strict';
if (customElements.get('uniscuola-card')) return;
/*
 * UniScuola Card — card Lovelace per Home Assistant (nessuna dipendenza esterna)
 * Mostra le tessere (compiti oggi/domani, ultimo voto, media, assenze, bacheca) e,
 * toccandole, apre un popup con il dettaglio. Si installa da sola con UniScuola.
 *
 * Esempio:
 *   type: custom:uniscuola-card
 *   students:
 *     - name: Giorgia          # uguale al nome scritto nella configurazione di UniScuola
 *       photo: /local/giorgia.jpg   # facoltativo
 *     - name: Claudia
 *   addon_slug: ee1c5e4d_compitapp  # facoltativo se c’è una sola UniScuola nella barra laterale
 *   theme: auto                   # auto, light, dark
 */
const UNISCUOLA_CARD_VERSION = '2.4.0';

const _slug = (n) => String(n || '').toLowerCase().replace(/ /g, '_');
const _esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const _data = (d) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || '');
  return m ? `${m[3]}/${m[2]}/${m[1]}` : _esc(d || '');
};
const _tipo = { A: 'Assenza', R: 'Ritardo', U: 'Uscita anticipata' };

const TILES = [
  { key: 'compiti_oggi', icon: 'book-open-outline', label: 'Compiti oggi', title: 'Compiti per oggi' },
  { key: 'compiti_domani', icon: 'calendar-blank-outline', label: 'Compiti domani', title: 'Compiti per domani' },
  { key: 'ultimo_voto', icon: 'star-outline', label: 'Ultimo voto', title: 'Ultimi voti' },
  { key: 'media_voti', icon: 'chart-line', label: 'Media voti', title: 'Media per materia' },
  { key: 'assenze', icon: 'account-check-outline', label: 'Assenze', title: 'Assenze, ritardi e uscite' },
  { key: 'bacheca', icon: 'bulletin-board', label: 'In bacheca', title: 'Bacheca' },
];

class CompitappCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._sel = 0;
    this._popup = null;
  }

  setConfig(config) {
    let students = config.students;
    if (!students && config.student) students = [{ name: config.student, photo: config.photo }];
    if (!students || !students.length) throw new Error('Indica "students" (lista) oppure "student" (nome dello studente)');
    this._config = { ...config, students: students.map((s) => (typeof s === 'string' ? { name: s } : s)) };
    if (this._config.students.some((s) => !s || !String(s.name || '').trim())) throw new Error('Ogni studente deve avere un nome');
    this._sel = Math.min(this._sel, students.length - 1);
    this._chiudiPopup();
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // ridisegna solo se i sensori dello studente sono cambiati
    const st = this._stud();
    const firma = (st ? TILES.map((t) => { const e = hass.states[this._eid(st, t.key)]; return e ? e.last_updated : '-'; }).join('|') : '') + '|' + !!hass.themes?.darkMode + '|' + JSON.stringify(hass.panels || {});
    if (firma !== this._firma) { this._firma = firma; this._render(); }
  }

  getCardSize() { return 5; }

  static getStubConfig() { return { students: [{ name: 'Nome studente' }] }; }

  _stud() { return this._config && this._config.students[this._sel]; }
  _slugDi(st) {
    // 1) campo esplicito "entity_slug"; 2) nome identico; 3) unico sensore il cui nome inizia con quello scritto
    if (st.entity_slug) return _slug(st.entity_slug);
    const voluto = _slug(st.name);
    if (!this._hass) return voluto;
    const trovati = Object.keys(this._hass.states)
      .map((k) => /^sensor\.compitapp_(.+)_compiti_oggi$/.exec(k)).filter(Boolean).map((m) => m[1]);
    if (trovati.includes(voluto)) return voluto;
    const simili = trovati.filter((x) => x.startsWith(voluto + '_') || voluto.startsWith(x + '_'));
    return simili.length === 1 ? simili[0] : voluto;
  }
  _eid(st, key) { return `sensor.compitapp_${this._slugDi(st)}_${key}`; }
  _ent(key) { const st = this._stud(); return st && this._hass ? this._hass.states[this._eid(st, key)] : undefined; }

  _palette() {
    const palette = this._stud()?.palette || this._config.palette || this._ent('compiti_oggi')?.attributes?.palette || 'salvia';
    return ['salvia', 'rosa', 'azzurro'].includes(palette) ? palette : 'salvia';
  }

  _openPath() {
    const panels = Object.entries(this._hass?.panels || {});
    const route = (slug) => {
      const panel = panels.find(([key, p]) => (p.config?.addon || key) === slug);
      if (panel) return '/' + (panel[1].url_path || panel[0]);
      return (this._hass?.panels?.app ? '/app/' : '/hassio/ingress/') + encodeURIComponent(slug);
    };
    if (this._config.addon_slug) {
      const slug = String(this._config.addon_slug);
      if (!/^[a-zA-Z0-9_-]+$/.test(slug)) throw new Error('addon_slug non valido. Usa l’identificativo dell’app installata.');
      return route(slug);
    }
    const explicit = this._config.open_url;
    // Il vecchio esempio non conteneva il prefisso del repository e non è un URL valido.
    if (explicit && explicit !== '/hassio/ingress/compitapp' && explicit !== '/app/compitapp') {
      const url = new URL(explicit, location.origin);
      if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) throw new Error('open_url deve essere un percorso di questo Home Assistant.');
      return url.pathname + url.search + url.hash;
    }
    const candidates = panels.filter(([key, p]) => /(^|_)compitapp$/.test(p.config?.addon || key));
    if (candidates.length === 1) return '/' + (candidates[0][1].url_path || candidates[0][0]);
    throw new Error(candidates.length > 1
      ? 'Sono presenti più UniScuola. Imposta addon_slug nella card con l’identificativo del fork.'
      : 'Abilita “Mostra nella barra laterale” per UniScuola oppure imposta addon_slug nella card.');
  }

  _apriApp(ev) {
    if (ev && (ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey)) return;
    if (ev) ev.preventDefault();
    try {
      const path = this._openPath();
      this._chiudiPopup();
      // Navigazione interna HA: il pannello crea e mantiene la sessione Ingress.
      history.pushState({...history.state, from: location.pathname + location.search}, '', path);
      window.dispatchEvent(new CustomEvent('location-changed', {detail: {replace: false}}));
    } catch (error) {
      const message = this.shadowRoot.querySelector('.open-error');
      message.textContent = error.message;
      message.hidden = false;
    }
  }

  _render() {
    if (!this._config) return;
    this.setAttribute('data-theme', this._config.theme === 'dark' || (this._config.theme !== 'light' && this._hass?.themes?.darkMode) ? 'dark' : 'light');
    this.setAttribute('data-palette', this._palette());
    const st = this._stud();
    const aggiornato = (() => {
      const e = this._ent('compiti_oggi');
      if (!e) return '';
      const d = new Date(e.last_updated);
      if (isNaN(d.getTime())) return '';
      return `Sensori aggiornati ${d.toLocaleDateString('it-IT', {day:'2-digit',month:'2-digit'})} alle ${d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}`;
    })();
    const chips = this._config.students.length > 1
      ? `<div class="chips" aria-label="Studente">${this._config.students.map((s, i) => `<button type="button" class="chip ${i === this._sel ? 'on' : ''}" aria-pressed="${i === this._sel}" data-i="${i}">${_esc(s.name)}</button>`).join('')}</div>` : '';
    let openPath = '#';
    try { openPath = this._openPath(); } catch (_) {}
    const apri = `<a class="apri" href="${_esc(openPath)}"><span>Apri UniScuola</span><ha-icon icon="mdi:arrow-top-right"></ha-icon></a>`;
    const tiles = TILES.map((t) => {
      const e = this._ent(t.key);
      const val = e && !['unknown', 'unavailable'].includes(e.state) ? e.state : '–';
      const num = !isNaN(parseFloat(val));
      return `<button type="button" class="tile" data-k="${t.key}" aria-haspopup="dialog"><div class="tile-top"><ha-icon icon="mdi:${t.icon}"></ha-icon><span class="tile-arrow">↗</span></div><div class="val ${num ? '' : 'nd'}">${_esc(val)}</div><div class="lb">${t.label}</div></button>`;
    }).join('');
    const foto = st.photo ? `<img class="foto" src="${_esc(st.photo)}" alt="">` : `<div class="foto ph">${_esc((st.name || '?')[0].toUpperCase())}</div>`;
    this.shadowRoot.innerHTML = `
      <style>${STILE}</style>
      <ha-card>
        <div class="top"><div class="brand"><ha-icon icon="mdi:book-open-page-variant-outline"></ha-icon>UniScuola</div><span class="kicker">IL REGISTRO DI FAMIGLIA</span></div>
        ${chips}
        <div class="head">${foto}<div><div class="sub">LA SCUOLA, CON PIÙ CALMA</div><div class="nome">${_esc(st.name)}</div></div></div>
        <div class="grid">${tiles}</div>
        <div class="card-foot"><span class="updated">${_esc(aggiornato || 'In attesa dei sensori')}</span>${apri}</div>
        <p class="open-error" role="alert" hidden></p>
      </ha-card>`;
    this._mostraPopup();
    this.shadowRoot.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => { this._sel = +b.dataset.i; this._chiudiPopup(); this._firma = null; this._render(); }));
    this.shadowRoot.querySelectorAll('.tile').forEach((b) => b.addEventListener('click', () => { this._popup = b.dataset.k; this._mostraPopup(); }));
    this.shadowRoot.querySelector('.apri').addEventListener('click', (ev) => this._apriApp(ev));
  }

  _chiudiPopup() {
    this._popup = null;
    if (this._host) { this._host.remove(); this._host = null; }
    if (this._onKey) { document.removeEventListener('keydown', this._onKey); this._onKey = null; }
  }

  // Il popup vive nel body della pagina (non dentro la card): così non viene tagliato
  // dai temi con effetti "vetro" o trasformazioni.
  _mostraPopup() {
    if (this._host) { this._host.remove(); this._host = null; }
    if (this._onKey) { document.removeEventListener('keydown', this._onKey); this._onKey = null; }
    if (!this._popup) return;
    const host = document.createElement('div');
    host.setAttribute('data-theme', this.getAttribute('data-theme'));
    host.setAttribute('data-palette', this.getAttribute('data-palette'));
    const cs = getComputedStyle(this);
    const vars = ['--primary-color', '--text-primary-color', '--primary-text-color', '--secondary-text-color',
      '--card-background-color', '--secondary-background-color', '--divider-color']
      .map((v) => `${v}:${cs.getPropertyValue(v)}`).join(';');
    host.attachShadow({ mode: 'open' }).innerHTML = `<style>:host{${vars};font-family:var(--paper-font-body1_-_font-family,inherit)}${STILE}</style>${this._popupHtml()}`;
    document.body.appendChild(host);
    this._host = host;
    const ov = host.shadowRoot.querySelector('.overlay');
    ov.addEventListener('click', (ev) => { if (ev.target === ov) this._chiudiPopup(); });
    const close = host.shadowRoot.querySelector('.close');
    close.addEventListener('click', () => { const key = this._popup; this._chiudiPopup(); this.shadowRoot.querySelector(`[data-k="${key}"]`)?.focus(); });
    close.focus();
    this._onKey = (ev) => {
      if (ev.key === 'Escape') { ev.preventDefault(); close.click(); }
      if (ev.key === 'Tab') {
        ev.preventDefault();
        const body = host.shadowRoot.querySelector('.db');
        (host.shadowRoot.activeElement === close ? body : close).focus();
      }
    };
    document.addEventListener('keydown', this._onKey);
  }

  disconnectedCallback() { this._chiudiPopup(); }

  _popupHtml() {
    const t = TILES.find((x) => x.key === this._popup);
    const e = this._ent(t.key);
    const nome = _esc(this._stud().name);
    let corpo = '';
    const vuoto = (m) => `<div class="vuoto">${m}</div>`;
    const a = (e && e.attributes) || {};
    if (!e) corpo = vuoto('Sensore non trovato. Controlla il nome dello studente nella card.');
    else if (t.key === 'compiti_oggi' || t.key === 'compiti_domani') {
      const l = a.elenco || [];
      corpo = l.length ? l.map((c) => `<div class="riga"><div class="mat">${_esc(c.materia)}${c.completato ? ' · Completato' : ''}</div><div class="txt">${_esc(c.testo)}</div></div>`).join('')
        : vuoto(t.key === 'compiti_oggi' ? 'Nessun compito per oggi 🎉' : 'Nessun compito per domani 🎉');
    } else if (t.key === 'ultimo_voto') {
      const l = a.elenco || [];
      corpo = l.length ? l.map((v) => {
        const n = parseFloat(String(v.voto).replace(',', '.'));
        const cl = isNaN(n) ? '' : (n < 6 ? 'bad' : n < 7 ? 'mid' : 'ok');
        return `<div class="riga voto"><div class="badge ${cl}">${_esc(v.voto)}</div><div><div class="mat">${_esc(v.materia)} <span class="dt">${_data(v.data)}</span></div>${v.descrizione ? `<div class="txt">${_esc(v.descrizione)}</div>` : ''}</div></div>`;
      }).join('') : vuoto('Ancora nessun voto.');
    } else if (t.key === 'media_voti') {
      const l = a.medie || [];
      corpo = (l.length ? `<div class="riga"><div class="mat">Media generale</div><div class="txt"><b>${_esc(e.state)}</b></div></div>` + l.map((m) => {
        const cl = m.media < 6 ? 'bad' : m.media < 7 ? 'mid' : 'ok';
        return `<div class="riga voto"><div class="badge ${cl}">${_esc(m.media)}</div><div><div class="mat">${_esc(m.materia)}</div><div class="txt">${_esc(m.n)} ${m.n === 1 ? 'voto' : 'voti'}</div></div></div>`;
      }).join('') : vuoto('Ancora nessun voto.'));
    } else if (t.key === 'assenze') {
      const l = a.elenco || [];
      corpo = l.length ? l.map((x) => `<div class="riga"><div class="mat">${_esc(_tipo[x.tipo] || x.tipo)} <span class="dt">${_data(x.data)}</span></div><div class="txt">${x.giustificata ? '✅ giustificata' : '⚠️ da giustificare'}${x.descrizione ? ' · ' + _esc(x.descrizione) : ''}</div></div>`).join('')
        : vuoto('Nessuna assenza registrata.');
    } else if (t.key === 'bacheca') {
      const l = a.elenco || [];
      corpo = l.length ? l.map((m) => `<div class="riga"><div class="mat">${_esc(m.titolo)} <span class="dt">${_data(m.data)}</span></div>${m.mittente ? `<div class="dt">${_esc(m.mittente)}</div>` : ''}<div class="txt">${_esc(m.testo)}</div></div>`).join('')
        : vuoto('Nessuna comunicazione.');
    }
    return `<div class="overlay"><div class="dialog" role="dialog" aria-modal="true" aria-label="${_esc(t.title)}: ${nome}"><div class="dh"><div><div class="dt2">${nome}</div><div class="dt1">${t.title}</div></div><button class="close" aria-label="Chiudi">✕</button></div><div class="db" tabindex="0">${corpo}</div></div></div>`;
  }
}

const STILE = `
:host{display:block;--ca-bg:#f7f7f2;--ca-card:#fff;--ca-soft:#edf3ec;--ca-text:#29382e;--ca-muted:#778276;--ca-line:#e5e9df;--ca-green:#436b4a;font-family:"Segoe UI",system-ui,sans-serif;color:var(--ca-text);color-scheme:light}
:host([data-theme=dark]){--ca-bg:#19231e;--ca-card:#202d25;--ca-soft:#293e2e;--ca-text:#e5ede2;--ca-muted:#a2b19f;--ca-line:#354337;--ca-green:#add0a6;color-scheme:dark}
:host([data-palette=rosa]){--ca-bg:#fcf5f7;--ca-card:#fffafb;--ca-soft:#f8e8ee;--ca-text:#422e39;--ca-muted:#856c79;--ca-line:#ecdee5;--ca-green:#9b4166}
:host([data-palette=azzurro]){--ca-bg:#f2f7fc;--ca-card:#fcfdff;--ca-soft:#e3effa;--ca-text:#233b50;--ca-muted:#647b90;--ca-line:#dce6f0;--ca-green:#266c9a}
:host([data-palette=rosa][data-theme=dark]){--ca-bg:#291c25;--ca-card:#352530;--ca-soft:#492d3d;--ca-text:#f4e5ed;--ca-muted:#c9a8ba;--ca-line:#55394a;--ca-green:#f0acc9}
:host([data-palette=azzurro][data-theme=dark]){--ca-bg:#182634;--ca-card:#1e3143;--ca-soft:#294259;--ca-text:#e1edf8;--ca-muted:#a4bed5;--ca-line:#355069;--ca-green:#9dccf3}
*{box-sizing:border-box}button,a{-webkit-tap-highlight-color:transparent}button{font:inherit;cursor:pointer}ha-icon{--mdc-icon-size:22px}button:focus-visible,a:focus-visible,.db:focus-visible{outline:2px solid var(--ca-green);outline-offset:4px}[hidden]{display:none!important}
ha-card{display:block;padding:24px;background:var(--ca-bg);color:var(--ca-text);border:1px solid var(--ca-line);border-radius:22px;box-shadow:none}
.top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:22px}.brand{display:flex;align-items:center;gap:8px;font-size:20px;font-weight:750;letter-spacing:-.7px}.brand ha-icon{color:var(--ca-green)}.kicker{font-size:8px;letter-spacing:1.5px;color:var(--ca-muted)}
.chips{display:flex;gap:4px;background:var(--ca-card);border:1px solid var(--ca-line);padding:4px;border-radius:12px;margin-bottom:22px;overflow-x:auto}.chip{flex:1;white-space:nowrap;border:0;background:transparent;color:var(--ca-muted);padding:9px 12px;min-height:40px;border-radius:9px;font-size:12px}.chip.on{background:var(--ca-soft);color:var(--ca-green);font-weight:650}
.head{display:flex;gap:13px;align-items:center;margin:0 0 22px}.foto{width:52px;height:52px;border-radius:17px;object-fit:cover;border:1px solid var(--ca-line);flex-shrink:0}.foto.ph{display:flex;align-items:center;justify-content:center;background:var(--ca-soft);color:var(--ca-green);font:normal 27px Georgia,serif}.nome{font:normal 29px/1.25 Georgia,serif;letter-spacing:-.5px;overflow-wrap:anywhere}.sub{font-size:8px;letter-spacing:1.2px;color:var(--ca-muted);margin-bottom:4px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.tile{border:1px solid var(--ca-line);background:var(--ca-card);border-radius:15px;padding:14px;text-align:left;min-width:0;color:var(--ca-text);transition:transform .15s,border-color .15s}.tile:hover{border-color:var(--ca-green);transform:translateY(-2px)}.tile:active{transform:scale(.98)}.tile-top{display:flex;align-items:center;justify-content:space-between;color:var(--ca-green);margin-bottom:14px}.tile-arrow{color:var(--ca-muted);font-size:12px}.val{font-size:29px;font-weight:650;letter-spacing:-1px;line-height:1.15;color:var(--ca-green);overflow-wrap:anywhere}.val.nd{font-size:23px}.lb{font-size:10px;color:var(--ca-muted);margin-top:7px;line-height:1.4}.card-foot{display:flex;gap:14px;justify-content:space-between;align-items:center;margin-top:20px;flex-wrap:wrap}.updated{font-size:9px;color:var(--ca-muted);line-height:1.5}.apri{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:10px 13px;background:var(--ca-soft);color:var(--ca-green);border:1px solid var(--ca-line);border-radius:11px;font-size:11px;font-weight:650;text-decoration:none}.apri ha-icon{--mdc-icon-size:16px}.open-error{color:var(--ca-text);font-size:12px;line-height:1.6;padding:12px;margin:15px 0 0;background:var(--ca-soft);border-radius:10px}
.overlay{position:fixed;inset:0;background:#12251980;z-index:1000;display:flex;align-items:center;justify-content:center;padding:18px}.dialog{background:var(--ca-bg);color:var(--ca-text);border:1px solid var(--ca-line);border-radius:22px;max-width:540px;width:100%;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 20px 70px #0003}.dh{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;padding:24px 24px 18px;border-bottom:1px solid var(--ca-line)}.dt1{font:normal 26px/1.3 Georgia,serif}.dt2{font-size:10px;color:var(--ca-muted);margin-bottom:6px}.close{border:1px solid var(--ca-line);background:var(--ca-card);color:var(--ca-text);width:44px;height:44px;border-radius:13px;cursor:pointer;font-size:18px;flex-shrink:0}.db{padding:6px 24px 24px;overflow:auto;overscroll-behavior:contain}.riga{padding:16px 0;border-bottom:1px solid var(--ca-line);overflow-wrap:anywhere}.riga:last-child{border-bottom:0}.riga.voto{display:flex;gap:14px;align-items:center}.mat{font-size:13px;font-weight:650;line-height:1.5}.txt{margin-top:4px;white-space:pre-wrap;color:var(--ca-text);font-size:12px;line-height:1.7}.dt{font-size:10px;font-weight:400;color:var(--ca-muted)}.badge{min-width:48px;text-align:center;padding:11px 7px;border-radius:13px;font-weight:650;font-size:20px;background:var(--ca-soft)}.badge.ok{background:#62825824;color:var(--ca-green)}.badge.mid{background:#c69a3924;color:#a27a21}.badge.bad{background:#c0705d24;color:#c0705d}.vuoto{padding:34px 0;text-align:center;font-size:13px;line-height:1.7;color:var(--ca-muted)}
@container (max-width:380px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.kicker{display:none}ha-card{padding:20px}.nome{font-size:27px}}
:host{container-type:inline-size}
@media(prefers-reduced-motion:reduce){.tile{transition:none}}
`;

customElements.define('uniscuola-card', CompitappCard);
// Le dashboard esistenti continuano a usare lo stesso tipo.
if (!customElements.get('compitapp-card')) customElements.define('compitapp-card', class extends CompitappCard {});
window.customCards = window.customCards || [];
window.customCards.push({ type: 'uniscuola-card', name: 'UniScuola', description: 'Compiti, voti, assenze e bacheca con popup di dettaglio', preview: false });
console.info(`%c UNISCUOLA-CARD %c v${UNISCUOLA_CARD_VERSION} `, 'background:#436b4a;color:#fff', 'background:#222;color:#fff');

}());
