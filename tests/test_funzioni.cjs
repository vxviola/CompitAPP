const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../compitapp/static/funzioni.js'), 'utf8');

function apertura(percorso, esterno=false) {
    const redirects=[], history=[];
    const parent={location:{href:'https://casa.example/app/addon?altro=1&uniscuola='+encodeURIComponent(percorso)},
        history:{state:{router:'preservato'},replaceState:(...args)=>history.push(args)}};
    if(esterno) Object.defineProperty(parent,'location',{get(){throw new Error('cross origin');}});
    const location={origin:'https://casa.example',pathname:'/api/hassio_ingress/token/',search:'',hash:'',replace:v=>redirects.push(v)};
    const document={querySelector:()=>null,querySelectorAll:()=>[],getElementById:()=>null};
    const window={COMPITAPP:{base:'/api/hassio_ingress/token',studente:'Emma'},parent};
    vm.runInNewContext(source,{window,document,location,URL});
    return {redirects,history};
}

test('notifica apre avviso e figlio dentro Ingress preservando lo stato HA',()=>{
    const {redirects,history}=apertura('/bacheca?studente=Anna%20%26%20Leo#msg-42');
    assert.deepEqual(redirects,['/api/hassio_ingress/token/bacheca?studente=Anna%20%26%20Leo#msg-42']);
    assert.deepEqual(history[0][0],{router:'preservato'});
    const url=new URL(history[0][2]);
    assert.equal(url.searchParams.get('altro'),'1');
    assert.equal(url.searchParams.has('uniscuola'),false);
});

test('notifica rifiuta destinazioni esterne, eseguibili e API',()=>{
    for(const path of ['https://altro.example/bacheca','//altro.example/bacheca','javascript:alert(1)','/api/reset-db']) {
        const result=apertura(path);
        assert.equal(result.redirects.length,0);
        assert.equal(result.history.length,0);
    }
});

test('il normale caricamento continua quando il contenitore non è accessibile',()=>{
    assert.equal(apertura('/bacheca',true).redirects.length,0);
});

function notificheUI() {
    function element() {
        return {children: [], append(...items) {this.children.push(...items);}, appendChild(item) {this.children.push(item);},
            replaceChildren(...items) {this.children = items;},
            querySelectorAll() {return this.children.flatMap(c => c.children || []).filter(c => c.name === 'ha-service' && c.checked);}};
    }
    const devices = element(), old = element();
    old.append({name:'ha-service',value:'notify.mobile_app_vecchio',checked:true}); devices.append(old);
    const submit = {}, form = {querySelector:()=>submit,querySelectorAll:()=>[{value:'voti'}]};
    const nodes = {'ha-notify-form':form,'ha-notify-services':devices,'ha-notify-status':{},'ha-notify-load':{},'ha-notify-test':{},'ha-notify-enabled':{checked:true}};
    const calls = [], replies = [];
    const document = {querySelector:()=>null,querySelectorAll:()=>[],getElementById:id=>nodes[id]||null,createElement:element};
    vm.runInNewContext(source, {window:{COMPITAPP:{base:'/app/demo',studente:'Emma'}},document,location:{origin:'https://casa.example'},URL,
        fetch:async (url,options)=>{calls.push({url:String(url),options});const data=replies.shift();return {ok:!data.falliti,json:async()=>data};}});
    return {nodes,devices,calls,replies};
}

test('scelta multipla conserva destinatari scomparsi e non seleziona nuovi dispositivi', async()=>{
    const ui=notificheUI();
    ui.replies.push({servizi:[{id:'notify.mobile_app_nuovo',nome:'Nuovo'}]});
    await ui.nodes['ha-notify-load'].onclick();
    const inputs=ui.devices.children.flatMap(c=>c.children||[]).filter(c=>c.name==='ha-service');
    assert.equal(inputs.length,2);
    assert.equal(inputs[0].checked,true); assert.equal(inputs[1].checked,false);
    inputs[1].checked=true;
    ui.replies.push({ok:true});
    await ui.nodes['ha-notify-form'].onsubmit({preventDefault(){}});
    const data=JSON.parse(ui.calls[1].options.body);
    assert.deepEqual(data.servizi,['notify.mobile_app_vecchio','notify.mobile_app_nuovo']);
    assert.match(ui.calls[1].url,/studente=Emma/);
});

test('prova mostra errore parziale senza dichiarare successo totale',async()=>{
    const ui=notificheUI();ui.replies.push({totale:2,inviati:1,falliti:1});
    await ui.nodes['ha-notify-test'].onclick();
    assert.match(ui.nodes['ha-notify-status'].textContent,/1 invii riusciti su 2/);
    assert.match(ui.nodes['ha-notify-status'].textContent,/non hanno accettato/);
});
