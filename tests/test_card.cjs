/* Regredisce l’apertura HA senza chiamare Argo o un Home Assistant reale. */
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
let Card;
const registered = new Map();
const events = [], navigations = [];
const context = vm.createContext({
  HTMLElement: class {attachShadow() {this.shadowRoot = {querySelector: () => ({hidden: true, textContent: ''})};}},
  customElements: {get: name => registered.get(name), define: (name, Class) => {registered.set(name, Class); if (name === 'uniscuola-card') Card = Class;}},
  window: {dispatchEvent: (event) => events.push(event)},
  location: {origin: 'https://ha.example', pathname: '/lovelace/scuola', search: '?view=1'},
  history: {state: {root: true}, pushState: (...args) => navigations.push(args)},
  CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
  console: {info() {}}, URL
});
vm.runInContext(readFileSync(join(__dirname, '../compitapp/card/compitapp-card.js'), 'utf8'), context);
function card(config = {}, panels = {}) {
  const c = new Card();
  c._config = {students: [{name: 'Anna'}], ...config};
  c._hass = {panels, states: {}};
  return c;
}
test('il pannello rilevato apre direttamente UniScuola, anche col vecchio esempio', () => {
  const c = card({open_url: '/hassio/ingress/compitapp'}, {
    ee1c5e4d_compitapp: {url_path: 'ee1c5e4d_compitapp', config: {addon: 'ee1c5e4d_compitapp'}}
  });
  assert.equal(c._openPath(), '/ee1c5e4d_compitapp');
});
test('originale e fork richiedono una scelta esplicita e rispettano addon_slug', () => {
  const panels = {old_compitapp: {config: {addon: 'old_compitapp'}}, fork_compitapp: {config: {addon: 'fork_compitapp'}}};
  assert.throws(() => card({}, panels)._openPath(), /più UniScuola/);
  assert.equal(card({addon_slug: 'fork_compitapp'}, panels)._openPath(), '/fork_compitapp');
});
test('senza barra laterale usa il pannello Ingress disponibile nella versione HA', () => {
  assert.equal(card({addon_slug: 'fork_compitapp'})._openPath(), '/hassio/ingress/fork_compitapp');
  assert.equal(card({addon_slug: 'fork_compitapp'}, {app: {}})._openPath(), '/app/fork_compitapp');
  assert.throws(() => card()._openPath(), /barra laterale/);
});
test('apertura interna conserva lo stato HA e notifica il router', () => {
  let prevented = false;
  card({addon_slug: 'fork_compitapp'})._apriApp({preventDefault() {prevented = true;}});
  assert.ok(prevented);
  assert.equal(navigations.at(-1)[2], '/hassio/ingress/fork_compitapp');
  assert.equal(navigations.at(-1)[0].root, true);
  assert.equal(events.at(-1).type, 'location-changed');
});
test('blocca schemi eseguibili e percorsi esterni e mantiene gli URL personalizzati locali', () => {
  for (const open_url of ['javascript:alert(1)', '//evil.example', 'https://evil.example/app']) {
    assert.throws(() => card({open_url})._openPath(), /questo Home Assistant/);
  }
  assert.throws(() => card({addon_slug: '../evil'})._openPath(), /non valido/);
  assert.equal(card({open_url: '/app/fork_compitapp?test=1'})._openPath(), '/app/fork_compitapp?test=1');
});
test('i dati scolastici dei popup non diventano HTML eseguibile', () => {
  const c = card();
  c._popup = 'media_voti';
  c._hass.states.sensor = {};
  c._hass.states.sensor_compitapp = {};
  c._hass.states['sensor.compitapp_anna_media_voti'] = {state: '8', attributes: {medie: [{media:'<img src=x>', materia:'<script>test</script>', n:'<b>1</b>'}]}};
  const html = c._popupHtml();
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img src=x>'));
});
test('nuovo nome e vecchio tipo card sono entrambi registrati senza duplicazioni', () => {
  assert.ok(registered.has('uniscuola-card'));
  assert.ok(registered.has('compitapp-card'));
  const size = registered.size;
  vm.runInContext(readFileSync(join(__dirname, '../compitapp/card/compitapp-card.js'), 'utf8'), context);
  assert.equal(registered.size, size);
});
test('palette del figlio segue i sensori e può essere personalizzata nella card', () => {
  const c = card();
  c._hass.states['sensor.compitapp_anna_compiti_oggi'] = {attributes: {palette: 'rosa'}};
  assert.equal(c._palette(), 'rosa');
  c._config.palette = 'azzurro';
  assert.equal(c._palette(), 'azzurro');
  c._config.students[0].palette = 'salvia';
  assert.equal(c._palette(), 'salvia');
  c._config.students[0].palette = '<script>';
  assert.equal(c._palette(), 'salvia');
});
