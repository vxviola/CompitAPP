/* CompitAPP: navigazione, tema, ricerca e stato del registro. Nessuna dipendenza esterna. */
(function () {
    'use strict';
    const ui = window.COMPITAPP || {base: '', studente: ''};
    const $ = function (id) { return document.getElementById(id); };
    const api = function (path) {
        const url = new URL(ui.base + path, location.origin);
        if (ui.studente) url.searchParams.set('studente', ui.studente);
        return url;
    };
    let toastTimer, syncTimer, waiting = false, lastSeen = null;
    window.navTo = function (page) { location.href = api(page); return false; };
    window.showToast = function (text, ms, error) {
        const el = $('toast');
        clearTimeout(toastTimer);
        el.textContent = text;
        el.classList.toggle('error', !!error);
        el.hidden = false;
        toastTimer = setTimeout(function () { el.hidden = true; }, ms || 4500);
    };
    const themes = ['system', 'light', 'dark'];
    const names = {system: 'Automatico', light: 'Chiaro', dark: 'Scuro'};
    let theme = 'system';
    try { theme = localStorage.getItem('compitapp-theme') || 'system'; } catch (_) {}
    if (!themes.includes(theme)) theme = 'system';
    const media = matchMedia('(prefers-color-scheme: dark)');
    function paintTheme() {
        document.documentElement.dataset.theme = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme;
        const button = $('theme-toggle');
        if (button) {
            button.setAttribute('aria-label', 'Tema: ' + names[theme] + '. Cambia tema');
            button.title = 'Tema: ' + names[theme];
        }
    }
    paintTheme();
    if (media.addEventListener) media.addEventListener('change', paintTheme);
    if ($('theme-toggle')) $('theme-toggle').addEventListener('click', function () {
        theme = themes[(themes.indexOf(theme) + 1) % themes.length];
        try { localStorage.setItem('compitapp-theme', theme); } catch (_) {}
        paintTheme();
        showToast('Tema ' + names[theme].toLowerCase());
    });
    const menu = $('more-menu'), more = $('more-toggle');
    function closeMenu() {
        if (!menu || !more) return;
        menu.hidden = true; more.setAttribute('aria-expanded', 'false');
    }
    if (more) more.addEventListener('click', function () {
        menu.hidden = !menu.hidden; more.setAttribute('aria-expanded', String(!menu.hidden));
        if (!menu.hidden) $('more-close').focus();
    });
    if ($('more-close')) $('more-close').addEventListener('click', function () { closeMenu(); more.focus(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu && !menu.hidden) { closeMenu(); more.focus(); } });
    document.addEventListener('click', function (e) { if (menu && !menu.hidden && !menu.contains(e.target) && !more.contains(e.target)) closeMenu(); });
    document.querySelectorAll('[data-task-tab]').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('[data-task-tab]').forEach(function (t) {
                const active = t === tab; t.classList.toggle('active', active); t.setAttribute('aria-selected', String(active)); t.tabIndex = active ? 0 : -1;
            });
            document.querySelectorAll('[data-task-panel]').forEach(function (p) { p.hidden = p.id !== tab.dataset.taskTab; });
        });
        tab.addEventListener('keydown', function (e) {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            e.preventDefault();
            const tabs = Array.from(document.querySelectorAll('[data-task-tab]'));
            const next = tabs[(tabs.indexOf(tab) + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
            next.click(); next.focus();
        });
    });
    function statusText(state) {
        if (state.in_corso) return 'Sincronizzazione in corso…';
        if (state.esito === 'errore') return 'Ultimo controllo incompleto';
        return state.ultimo_successo ? 'Ultimo aggiornamento' : 'In attesa del primo controllo';
    }
    function timeText(value) {
        if (!value) return 'I dati compariranno dopo il primo aggiornamento';
        const dt = new Date(value);
        if (isNaN(dt.getTime())) return '';
        return dt.toLocaleString('it-IT', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'});
    }
    function renderSync(state) {
        document.querySelectorAll('[data-sync-button]').forEach(function (button) {
            button.disabled = !!state.in_corso;
            const icon = button.querySelector('.icon');
            if (icon) icon.classList.toggle('spin', !!state.in_corso);
        });
        const info = $('sync-info');
        if (info) {
            info.classList.toggle('is-error', state.esito === 'errore' && !state.in_corso);
            $('sync-label').textContent = statusText(state);
            $('sync-time').textContent = timeText(state.ultimo_successo);
        }
        if ($('dashboard-sync')) $('dashboard-sync').textContent = statusText(state) + (state.ultimo_successo ? ' · ' + timeText(state.ultimo_successo) : '');
    }
    async function pollSync() {
        clearTimeout(syncTimer);
        try {
            const response = await fetch(api('/api/sync-status'), {cache:'no-store'});
            if (!response.ok) throw new Error('status');
            const state = await response.json();
            renderSync(state);
            if (waiting && !state.in_corso) {
                waiting = false;
                if (state.esito === 'errore') showToast('Aggiornamento incompleto. Riprova o controlla il collegamento Argo in Impostazioni.', 9000, true);
                else { showToast('Registro aggiornato.'); setTimeout(function () { location.reload(); }, 800); }
            }
            if (!waiting && lastSeen && state.ultimo_successo && state.ultimo_successo !== lastSeen) {
                showToast('Sono disponibili dati aggiornati. Ricarica la pagina per visualizzarli.', 6500);
            }
            lastSeen = state.ultimo_successo || lastSeen;
            syncTimer = setTimeout(pollSync, state.in_corso ? 2000 : 30000);
        } catch (_) {
            if (waiting) showToast('Connessione interrotta. Il controllo può continuare in background; riprovo a verificarlo.', 6000, true);
            if ($('sync-label')) $('sync-label').textContent = 'Stato non raggiungibile';
            syncTimer = setTimeout(pollSync, 15000);
        }
    }
    window.syncNow = async function () {
        if (waiting) return;
        waiting = true;
        document.querySelectorAll('[data-sync-button]').forEach(function (b) { b.disabled = true; });
        showToast('Aggiorno il registro. Puoi continuare a consultare la pagina.');
        try {
            const response = await fetch(api('/api/sync'), {method:'POST'});
            const data = await response.json();
            if (response.status !== 409 && !response.ok) throw new Error(data.errore || 'Aggiornamento non disponibile.');
            await pollSync();
        } catch (e) {
            waiting = false;
            document.querySelectorAll('[data-sync-button]').forEach(function (b) { b.disabled = false; });
            showToast(e.message || 'Connessione non disponibile. Riprova tra poco.', 7000, true);
        }
    };
    if (ui.studente) pollSync();
    const search = $('board-search'), onlyFiles = $('board-files'), period = $('board-period');
    const from = $('board-from'), to = $('board-to');
    if (search && onlyFiles && period) {
        const cards = Array.from(document.querySelectorAll('[data-board-card]'));
        const fold = function (value) { return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('it'); };
        const texts = new Map(cards.map(function (card) { return [card, fold(card.textContent)]; }));
        const params = new URLSearchParams(location.search);
        search.value = params.get('q') || '';
        onlyFiles.checked = params.get('allegati') === '1';
        if (['all','7','30','90'].includes(params.get('periodo'))) period.value = params.get('periodo');
        function filterBoard() {
            const words = fold(search.value.trim()).split(/\s+/).filter(Boolean);
            const minDate = new Date(); minDate.setHours(0,0,0,0);
            if (period.value !== 'all') minDate.setDate(minDate.getDate() - Number(period.value));
            let visible = 0;
            cards.forEach(function (card) {
                const date = card.dataset.date || '';
                const dt = new Date(date + 'T12:00:00');
                const textOk = words.every(function (word) { return texts.get(card).includes(word); });
                const periodOk = period.value === 'all' || (!isNaN(dt.getTime()) && dt >= minDate);
                const rangeOk = (!from.value || date >= from.value) && (!to.value || date <= to.value);
                const show = textOk && periodOk && rangeOk && (!onlyFiles.checked || Number(card.dataset.files) > 0);
                card.hidden = !show; if (show) visible++;
            });
            $('board-count').textContent = visible + (visible === 1 ? ' comunicazione' : ' comunicazioni') + ' su ' + cards.length;
            $('board-no-results').hidden = visible > 0 || cards.length === 0;
            const url = new URL(location.href);
            [['q',search.value.trim()],['allegati',onlyFiles.checked?'1':''],['periodo',period.value==='all'?'':period.value]].forEach(function (entry) { if (entry[1]) url.searchParams.set(entry[0], entry[1]); else url.searchParams.delete(entry[0]); });
            history.replaceState(null, '', url);
        }
        [search, onlyFiles, period, from, to].forEach(function (el) { el.addEventListener('input', filterBoard); });
        document.querySelectorAll('[data-reset-filters]').forEach(function (button) {
            button.addEventListener('click', function () { search.value=''; onlyFiles.checked=false; period.value='all'; from.value=''; to.value=''; filterBoard(); search.focus(); });
        });
        filterBoard();
    }
})();
