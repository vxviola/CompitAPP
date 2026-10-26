const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const {File} = require('node:buffer');
const source = readFileSync(join(__dirname, '../compitapp/static/allegati.js'), 'utf8');

function scenario({share = true, failed = false, pending = false, cancelled = false} = {}) {
  const calls = {share: [], revoked: [], fetch: [], downloads: 0, focus: 0};
  class Element {
    constructor() {this.events = {}; this.nodes = {}; this.hidden = true; this.dataset = {}; this.textContent = ''; this.children = [];}
    addEventListener(name, fn) {this.events[name] = fn;}
    querySelector(key) {return this.nodes[key] ||= new Element();}
    appendChild(node) {this.children.push(node);}
    showModal() {this.open = true;}
    close() {this.open = false; this.events.close?.();}
    setAttribute() {}
    remove() {}
    click() {calls.downloads++;}
    focus() {calls.focus++;}
  }
  const link = new Element();
  link.href = 'https://ha.example/api/hassio_ingress/token/bacheca/1/allegati/0?studente=Anna';
  link.dataset.filename = 'Circolare è.pdf';
  let dialog, resolveFetch;
  const response = {ok: !failed, headers: {get: () => 'application/octet-stream'}, arrayBuffer: async () => Uint8Array.from(Buffer.from('%PDF-1.4 prova')).buffer};
  const context = vm.createContext({
    window: {HTMLDialogElement: true, fetch: true},
    document: {
      querySelectorAll: () => [link],
      createElement: tag => {const el = new Element(); if (tag === 'dialog') dialog = el; return el;},
      body: new Element()
    },
    navigator: {canShare: () => share, share: async data => {calls.share.push(data); if (cancelled) throw Object.assign(new Error(), {name:'AbortError'});}},
    fetch: async (url, options) => {calls.fetch.push({url, options}); return pending ? new Promise(resolve => {resolveFetch = resolve;}) : response;},
    File, Uint8Array, AbortController,
    URL: {createObjectURL: file => {calls.file = file; return 'blob:https://ha.example/local';}, revokeObjectURL: url => calls.revoked.push(url)},
    setTimeout: fn => {fn();}
  });
  vm.runInContext(source, context);
  let prevented = false;
  link.events.click({button: 0, preventDefault() {prevented = true;}});
  return {calls, link, get dialog() {return dialog;}, get prevented() {return prevented;}, finish() {resolveFetch(response);}};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('il download prepara un File PDF e aspetta il secondo tap prima della condivisione', async () => {
  const s = scenario();
  await settle();
  assert.ok(s.prevented);
  assert.equal(s.calls.fetch[0].options.credentials, 'same-origin');
  assert.equal(s.calls.fetch[0].options.cache, 'no-store');
  assert.equal(s.calls.file.type, 'application/pdf');
  assert.equal(s.calls.file.name, 'Circolare è.pdf');
  assert.equal(s.calls.share.length, 0);
  assert.equal(s.dialog.querySelector('.file-actions').hidden, false);
  await s.dialog.querySelector('.file-save').onclick();
  assert.equal(s.calls.share.length, 1);
  assert.equal(s.calls.share[0].files[0], s.calls.file);
  s.dialog.close();
  assert.equal(s.calls.revoked.length, 1);
  assert.equal(s.calls.focus, 1);
});
test('condivisione annullata non produce un errore', async () => {
  const s = scenario({cancelled: true});
  await settle();
  const before = s.dialog.querySelector('.file-status').textContent;
  await s.dialog.querySelector('.file-save').onclick();
  assert.equal(s.dialog.querySelector('.file-status').textContent, before);
});
test('anche con Web Share disponibile resta possibile scaricare normalmente sul desktop', async () => {
  const s = scenario();
  await settle();
  const button = s.dialog.querySelector('.file-download');
  assert.equal(button.hidden, false);
  button.onclick();
  assert.equal(s.calls.downloads, 1);
  assert.equal(s.calls.share.length, 0);
});
test('browser senza Web Share scarica il blob con il nome originale', async () => {
  const s = scenario({share: false});
  await settle();
  await s.dialog.querySelector('.file-save').onclick();
  assert.equal(s.calls.downloads, 1);
  assert.equal(s.calls.share.length, 0);
  const anchor = s.dialog.children.at(-1);
  assert.equal(anchor.href, 'blob:https://ha.example/local');
  assert.equal(anchor.download, 'Circolare è.pdf');
});
test('errore HTTP non espone byte o URL firmati e non abilita il salvataggio', async () => {
  const s = scenario({failed: true});
  await settle();
  assert.match(s.dialog.querySelector('.file-status').textContent, /Download non riuscito/);
  assert.equal(s.dialog.querySelector('.file-actions').hidden, true);
  assert.equal(s.calls.share.length, 0);
});
test('chiudere durante il caricamento annulla la richiesta e non crea blob', async () => {
  const s = scenario({pending: true});
  s.dialog.close();
  assert.ok(s.calls.fetch[0].options.signal.aborted);
  s.finish();
  await settle();
  assert.equal(s.calls.file, undefined);
});
