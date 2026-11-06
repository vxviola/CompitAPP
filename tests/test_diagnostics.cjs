const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../compitapp/card/compitapp-card.js'),'utf8');
let Card;
const ticks=[];
const context={HTMLElement:class{attachShadow(){this.shadowRoot={querySelector:()=>null};}},
 customElements:{get:()=>false,define:(n,c)=>{if(n==='uniscuola-card')Card=c;}},
 window:{},console:{info(){}},setInterval:fn=>{ticks.push(fn);return 1;},clearInterval:()=>{}};
vm.runInNewContext(source,context);
function card(attrs, state='ok') {
 const c=new Card();c._config={students:[{name:'SYNTHETIC'}]};
 c._hass={states:attrs ? {'sensor.compitapp_synthetic_diagnostica':{state,attributes:attrs}} : {}};
 return c;
}
const fresh=()=>({esito:'ok',ultimo_successo:new Date().toISOString(),verificato_il:new Date().toISOString(),intervallo_minuti:30});

test('card: errore resta visibile durante tentativo e nessun nome/payload è mostrato',()=>{
 const c=card({...fresh(),esito:'errore',motivo:'rete',in_corso:true,nome:'SECRET',messaggio:'SECRET',token:'SECRET'});
 const html=c._diagnosticaHtml();
 assert.match(html,/diagnostica errore/);assert.match(html,/Argo non raggiungibile/);assert.match(html,/nuovo tentativo/);
 assert.doesNotMatch(html,/SECRET|SYNTHETIC/);
});
test('card: successo verde solo recente, dati obsoleti e sensore assente non sono verdi',()=>{
 assert.match(card(fresh())._diagnosticaHtml(),/diagnostica ok/);
 const old=new Date(Date.now()-3*3600000).toISOString();
 assert.match(card({...fresh(),ultimo_successo:old})._diagnosticaHtml(),/Dati non aggiornati di recente/);
 assert.doesNotMatch(card({...fresh(),ultimo_successo:old})._diagnosticaHtml(),/diagnostica ok/);
 assert.match(card(null)._diagnosticaHtml(),/Diagnostica non disponibile/);
 assert.doesNotMatch(card(fresh(),'unavailable')._diagnosticaHtml(),/diagnostica ok/);
});
test('card: diagnostica non recente non conferma prossimo controllo o successo',()=>{
 const a={...fresh(),verificato_il:new Date(Date.now()-11*60000).toISOString(),prossimo_tentativo:new Date(Date.now()+60000).toISOString()};
 assert.doesNotMatch(card(a)._diagnosticaHtml(),/Prossimo controllo:|diagnostica ok/);
 assert.match(card({...fresh(),prossimo_tentativo:a.prossimo_tentativo})._diagnosticaHtml(),/Prossimo controllo:/);
 assert.doesNotMatch(card({...fresh(),prossimo_tentativo:'2000-01-01T00:00:00Z'})._diagnosticaHtml(),/Prossimo controllo:/);
});
test('card: aggiornamento temporizzato cambia solo diagnostica senza ricreare popup o focus',()=>{
 const c=card(fresh());let html='';let renders=0;
 c._render=()=>renders++;
 c.shadowRoot.querySelector=selector=>{assert.equal(selector,'.diagnostica');return {set outerHTML(v){html=v;}};};
 c.connectedCallback();ticks.at(-1)();
 assert.equal(renders,0);assert.match(html,/role="status"/);assert.match(html,/aria-live="polite"/);
});
test('card: selezione profilo separa stato e timestamp',()=>{
 const c=card(fresh());c._config.students.push({name:'SECOND'});
 c._hass.states['sensor.compitapp_second_diagnostica']={state:'errore',attributes:{...fresh(),esito:'errore',motivo:'permessi'}};
 assert.match(c._diagnosticaHtml(),/Registro aggiornato/);
 c._sel=1;assert.match(c._diagnosticaHtml(),/Accesso ai dati non consentito/);
});
test('home: errore, recupero, obsolescenza e disconnessione aggiornano il riquadro',async()=>{
 const src=fs.readFileSync(path.join(__dirname,'../compitapp/static/dashboard.js'),'utf8');
 const ids=['sync-info','sync-label','sync-time','connection-status','dashboard-sync','sync-diagnostics','diagnostic-message','diagnostic-last','diagnostic-next','diagnostic-action'];
 const nodes=Object.fromEntries(ids.map(id=>[id,{textContent:'',className:'',classList:{toggle(){}}}]));
 const states=[{...fresh(),esito:'errore',motivo:'rete',in_corso:true,messaggio:'Argo non raggiungibile',azione:'Attendi il prossimo controllo.'},
 {...fresh(),messaggio:'Registro aggiornato'}, {...fresh(),dati_obsoleti:true,messaggio:'Dati non aggiornati di recente'},null];
 const timers=[];
 vm.runInNewContext(src,{window:{COMPITAPP:{base:'',studente:'SYNTHETIC'}},URL,location:{origin:'https://offline.invalid'},
 document:{documentElement:{dataset:{}},getElementById:id=>nodes[id]||null,querySelectorAll:()=>[],addEventListener:()=>{}},
 localStorage:{getItem:()=>null},matchMedia:()=>({matches:false}),setTimeout:fn=>timers.push(fn),clearTimeout:()=>{},
 fetch:async()=>{const s=states.shift();if(!s)throw Error('offline');return {ok:true,json:async()=>s};}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(nodes['sync-diagnostics'].className,/errore/);assert.match(nodes['diagnostic-message'].textContent,/Argo/);
 await timers.shift()();assert.match(nodes['sync-diagnostics'].className,/ok/);
 await timers.shift()();assert.match(nodes['sync-diagnostics'].className,/attesa/);
 await timers.shift()();assert.match(nodes['sync-diagnostics'].className,/errore/);
 assert.match(nodes['diagnostic-message'].textContent,/Stato non raggiungibile/);
 assert.match(nodes['diagnostic-next'].textContent,/Nessun prossimo/);
});

test('home: primo polling offline conserva ultimo successo renderizzato dal server',async()=>{
 const src=fs.readFileSync(path.join(__dirname,'../compitapp/static/dashboard.js'),'utf8');
 const last='2026-11-02T09:15:00Z';
 const ids=['sync-info','sync-label','sync-time','sync-diagnostics','diagnostic-message','diagnostic-last','diagnostic-next','diagnostic-action'];
 const nodes=Object.fromEntries(ids.map(id=>[id,{textContent:'',className:'',classList:{toggle(){}},getAttribute:()=>last}]));
 vm.runInNewContext(src,{window:{COMPITAPP:{base:'',studente:'SYNTHETIC'}},URL,location:{origin:'https://offline.invalid'},
 document:{documentElement:{dataset:{}},getElementById:id=>nodes[id]||null,querySelectorAll:()=>[],addEventListener:()=>{}},
 localStorage:{getItem:()=>null},matchMedia:()=>({matches:false}),setTimeout:()=>1,clearTimeout:()=>{},fetch:async()=>{throw Error('offline');}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(nodes['sync-diagnostics'].className,/errore/);
 assert.doesNotMatch(nodes['diagnostic-last'].textContent,/non disponibile/);
 assert.match(nodes['diagnostic-last'].textContent,/2 nov/);
});
