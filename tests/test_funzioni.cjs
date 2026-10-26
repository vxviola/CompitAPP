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
