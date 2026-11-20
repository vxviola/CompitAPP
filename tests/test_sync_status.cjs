const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../compitapp/static/dashboard.js'), 'utf8');

test('errore resta rosso durante retry, verde solo al successo, rosso se stato irraggiungibile', async () => {
    const nodes = {};
    for (const id of ['sync-info', 'sync-label', 'sync-short', 'connection-status']) {
        const classes = new Set();
        nodes[id] = {textContent:'', className:'', classes,
            classList:{toggle:(c,on)=>on ? classes.add(c) : classes.delete(c)}};
    }
    const states = [
        {esito:'errore', motivo:'accesso', in_corso:false},
        {esito:'errore', motivo:'accesso', in_corso:true},
        {esito:'ok', in_corso:false, ultimo_successo:'2026-10-29T15:00:00+01:00'},
        null,
    ];
    const timers = [];
    const window = {COMPITAPP:{base:'/addon',studente:'Test'}};
    vm.runInNewContext(source, {window, URL, location:{origin:'https://casa.example'},
        document:{documentElement:{dataset:{}},getElementById:id=>nodes[id]||null,
            querySelectorAll:()=>[],addEventListener:()=>{}},
        localStorage:{getItem:()=>null},matchMedia:()=>({matches:false}),
        setTimeout:fn=>timers.push(fn),clearTimeout:()=>{},
        fetch:async()=>{const s=states.shift(); if(s===null) throw Error('offline'); return {ok:true,json:async()=>s};},
    });
    const flush = () => new Promise(resolve=>setImmediate(resolve));
    await flush();
    assert(nodes['sync-info'].classes.has('is-error'));
    assert.equal(nodes['sync-short'].textContent, 'Errore registro');
    assert.match(nodes['sync-label'].textContent,/Errore di accesso/);
    await timers.shift()();
    assert(nodes['sync-info'].classes.has('is-error'));
    assert(!nodes['sync-info'].classes.has('is-ok'));
    assert.match(nodes['connection-status'].textContent,/nuovo tentativo/);
    await timers.shift()();
    assert(nodes['sync-info'].classes.has('is-ok'));
    assert(!nodes['sync-info'].classes.has('is-error'));
    await timers.shift()();
    assert(nodes['sync-info'].classes.has('is-error'));
    assert(!nodes['sync-info'].classes.has('is-ok'));
    assert.match(nodes['sync-label'].textContent,/non raggiungibile/);
    assert.equal(nodes['sync-short'].textContent, 'Errore registro');
});

test('il pannello si richiude con Escape restituendo il focus e con un clic esterno', async () => {
    const events = {};
    const inside = {};
    const details = {open: true, contains: (target) => target === inside};
    let focused = false;
    const summary = {focus: () => { focused = true; }, classList: {toggle() {}}};
    const nodes = {'registro-status': details, 'sync-info': summary, 'sync-label': {}, 'sync-short': {}};
    vm.runInNewContext(source, {window: {COMPITAPP: {base:'/addon',studente:'Test'}}, URL, location: {origin:'https://casa.example'},
        document: {documentElement: {dataset:{}}, getElementById: id=>nodes[id]||null, querySelectorAll:()=>[],
            addEventListener: (name, fn) => (events[name] ||= []).push(fn)},
        localStorage: {getItem:()=>null}, matchMedia:()=>({matches:false}),
        setTimeout:()=>1, clearTimeout(){}, fetch:async()=>({ok:true,json:async()=>({esito:'ok'})})});
    const fire = (name, event) => events[name].forEach(fn=>fn(event));
    fire('click', {target: inside});
    assert.equal(details.open, true);
    fire('keydown', {key:'Escape'});
    assert.equal(details.open, false);
    assert.equal(focused, true);
    details.open = true;
    fire('click', {target: {}});
    assert.equal(details.open, false);
});
