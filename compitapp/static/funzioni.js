(function () {
    'use strict';
    const ui = window.COMPITAPP || {base: '', studente: ''};
    const toast = function (message, error) { window.showToast(message, error ? 7000 : 3500, !!error); };
    const endpoint = function (path) {
        const url = new URL(ui.base + path, location.origin);
        url.searchParams.set('studente', ui.studente);
        return url;
    };
    async function salva(path, data, method) {
        const r = await fetch(endpoint(path), {method: method || 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
        const result = await r.json();
        if (!r.ok) throw new Error(result.errore || 'Non riesco a salvare. Riprova.');
        return result;
    }

    // Il link della notifica apre il pannello HA; l'iframe riceve solo un percorso locale ammesso.
    try {
        if (window.parent !== window) {
            const parentUrl = new URL(window.parent.location.href);
            const deep = parentUrl.searchParams.get('uniscuola');
            if (deep) {
                const target = new URL(deep, location.origin);
                if (target.origin === location.origin && ['/', '/bacheca', '/calendario', '/zaino', '/ricerca'].includes(target.pathname)) {
                    parentUrl.searchParams.delete('uniscuola');
                    window.parent.history.replaceState(window.parent.history.state, '', parentUrl);
                    const destination = ui.base + target.pathname + target.search + target.hash;
                    if (location.pathname + location.search + location.hash !== destination) { location.replace(destination); return; }
                }
            }
        }
    } catch (_) {}

    function progresso() {
        const all = Array.from(document.querySelectorAll('[data-task-done]'));
        const panel = document.querySelector('[data-task-panel]:not([hidden])');
        const current = panel ? Array.from(panel.querySelectorAll('[data-task-done]')) : all;
        document.querySelectorAll('[data-task-progress]').forEach(function (e) { const n=current.filter(c => c.checked).length; e.textContent = n + (n===1?' completato su ':' completati su ') + current.length; });
        const tomorrow = Array.from(document.querySelectorAll('#tasks-domani [data-task-done]'));
        const remaining = tomorrow.filter(c => !c.checked).length;
        const summary = document.querySelector('[data-tomorrow-summary]');
        if(summary && tomorrow.length) summary.textContent = remaining ? ('Per domani ' + (remaining===1?'resta un’attività da completare.':'restano '+remaining+' attività da completare.')) : 'Hai completato tutti i compiti di domani.';
        const filter = document.getElementById('tasks-only-open');
        all.forEach(function (c) {
            const row = c.closest('[data-task-row]');
            row.classList.toggle('is-complete', c.checked);
            row.hidden = !!(filter && filter.checked && c.checked);
            row.querySelector('.task-status').textContent = c.checked ? 'Completato' : 'Da fare';
        });
    }
    document.querySelectorAll('[data-task-done]').forEach(function (c) {
        c.addEventListener('change', async function () {
            c.disabled = true;
            try { await salva('/api/compiti/' + c.dataset.taskDone, {completato: c.checked}); }
            catch (e) { c.checked = !c.checked; toast(e.message, true); }
            finally { c.disabled = false; progresso(); }
        });
    });
    const taskFilter = document.getElementById('tasks-only-open');
    if (taskFilter) taskFilter.addEventListener('change', progresso);
    document.querySelectorAll('[data-task-tab]').forEach(function (b) { b.addEventListener('click', progresso); });
    progresso();

    document.querySelectorAll('[data-message-read], [data-file-read]').forEach(function (c) {
        c.addEventListener('change', async function () {
            c.disabled = true;
            try {
                if (c.dataset.messageRead) {
                    await salva('/api/bacheca/' + c.dataset.messageRead, {letta: c.checked});
                    
                } else {
                    const ids = c.dataset.fileRead.split('/');
                    await salva('/api/bacheca/' + ids[0] + '/allegati/' + ids[1] + '/letto', {letto: c.checked});
                }
                const card = c.closest('[data-board-card]');
                card.dataset.unread = (!card.querySelector('[data-message-read]').checked || Array.from(card.querySelectorAll('[data-file-read]')).some(x => !x.checked)) ? '1' : '0';
                document.dispatchEvent(new Event('document-preference'));
            } catch (e) { c.checked = !c.checked; toast(e.message, true); }
            finally { c.disabled = false; }
        });
    });
    document.querySelectorAll('[data-document-star]').forEach(function (b) {
        b.addEventListener('click', async function () {
            const selected = b.getAttribute('aria-pressed') !== 'true';
            b.disabled = true;
            try {
                await salva('/api/bacheca/' + b.dataset.documentStar, {preferito: selected});
                b.setAttribute('aria-pressed', String(selected));
                b.closest('[data-board-card]').dataset.starred = selected ? '1' : '0';
                document.dispatchEvent(new Event('document-preference'));
            } catch (e) { toast(e.message, true); }
            finally { b.disabled = false; }
        });
    });
    document.querySelectorAll('[data-document-reminder]').forEach(function (c) {
        let previous = c.value;
        c.addEventListener('change', async function () {
            c.disabled = true;
            try { await salva('/api/bacheca/' + c.dataset.documentReminder, {promemoria_locale: c.value}); previous = c.value; toast(c.value ? 'Promemoria salvato. Attiva le notifiche documenti nelle impostazioni per riceverlo su Home Assistant.' : 'Promemoria rimosso.'); }
            catch (e) { c.value = previous; toast(e.message, true); }
            finally { c.disabled = false; }
        });
    });

    function contaZaino() {
        const checks = Array.from(document.querySelectorAll('[data-bag-check]'));
        const count = document.getElementById('bag-count');
        if (count) count.textContent = checks.filter(c => c.checked).length + ' / ' + checks.length;
    }
    document.querySelectorAll('[data-bag-check]').forEach(function (c) {
        c.addEventListener('change', async function () {
            c.disabled = true;
            try { await salva('/api/zaino/' + c.dataset.bagCheck, {data: c.dataset.day, fatto: c.checked}); }
            catch (e) { c.checked = !c.checked; toast(e.message, true); }
            finally { c.disabled = false; c.closest('.bag-row').classList.toggle('is-complete', c.checked); contaZaino(); }
        });
    });
    const add = document.getElementById('bag-add');
    if (add) add.addEventListener('submit', async function (e) {
        e.preventDefault();
        const button = add.querySelector('button'); button.disabled = true;
        try { await salva('/api/zaino', Object.fromEntries(new FormData(add))); location.reload(); }
        catch (error) { toast(error.message, true); button.disabled = false; }
    });
    document.querySelectorAll('[data-bag-delete]').forEach(function (b) {
        b.addEventListener('click', async function () {
            b.disabled = true;
            try { await salva('/api/zaino/' + b.dataset.bagDelete, undefined, 'DELETE'); location.reload(); }
            catch (e) { b.disabled = false; toast(e.message, true); }
        });
    });

    const form = document.getElementById('ha-notify-form');
    if (form) {
        const devices = document.getElementById('ha-notify-services');
        const selectedDevices = () => Array.from(devices.querySelectorAll('[name=ha-service]:checked')).map(c => c.value);
        const status = document.getElementById('ha-notify-status');
        const load = document.getElementById('ha-notify-load');
        load.onclick = async function () {
            load.disabled = true; status.textContent = 'Leggo i dispositivi di Home Assistant…';
            try {
                const r = await fetch(endpoint('/api/ha/servizi'), {cache: 'no-store'});
                const data = await r.json();
                if (!r.ok) throw new Error(data.errore);
                const selected = new Set(selectedDevices());
                const available = new Map(data.servizi.map(s => [s.id, s.nome]));
                const legend = document.createElement('legend'); legend.textContent = 'Dispositivi destinatari';
                devices.replaceChildren(legend);
                new Set([...selected, ...available.keys()]).forEach(function (id) {
                    const label = document.createElement('label'); label.className = 'filter-check';
                    const input = document.createElement('input'); input.type = 'checkbox';
                    input.name = 'ha-service'; input.value = id; input.checked = selected.has(id);
                    const text = document.createElement('span');
                    text.textContent = available.has(id) ? available.get(id) + ' · ' + id : id + ' (non disponibile)';
                    label.append(input, text); devices.appendChild(label);
                });
                status.textContent = data.servizi.length ? 'Seleziona uno o più dispositivi e salva. Rimuovi eventuali dispositivi non disponibili.' : 'Nessun dispositivo disponibile. Collega l’app Companion al tuo Home Assistant.';
            } catch (e) { status.textContent = e.message || 'Home Assistant non raggiungibile.'; }
            finally { load.disabled = false; }
        };
        form.onsubmit = async function (e) {
            e.preventDefault();
            const submit = form.querySelector('[type=submit]'); submit.disabled = true;
            try {
                await salva('/api/ha/notifiche', {attive: document.getElementById('ha-notify-enabled').checked,
                    servizi: selectedDevices(), eventi: Array.from(form.querySelectorAll('[name=ha-event]:checked')).map(c => c.value)});
                status.textContent = 'Preferenze salvate per ' + ui.studente + '.';
            } catch (error) { status.textContent = error.message; }
            finally { submit.disabled = false; }
        };
        document.getElementById('ha-notify-test').onclick = async function () {
            const b = this; b.disabled = true;
            try {
                const r = await fetch(endpoint('/api/ha/test'), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
                const data = await r.json();
                status.textContent = data.totale ? 'Prova: ' + data.inviati + ' invii riusciti su ' + data.totale + (data.falliti ? '. Alcuni dispositivi non hanno accettato la notifica.' : '.') : 'Salva prima almeno un dispositivo attivo e una categoria.';
            } catch (_) { status.textContent = 'Prova non riuscita: verifica il collegamento e riprova.'; }
            finally { b.disabled = false; }
        };
    }
}());
