/* I download restano nella pagina: WKWebView non deve navigare verso byte binari. */
(function () {
    'use strict';
    document.querySelectorAll('[data-attachment]').forEach(function (link) {
        link.addEventListener('click', function (ev) {
            if (ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
            if (!window.HTMLDialogElement || !window.fetch) return;
            ev.preventDefault();
            prepara(link);
        });
    });

    async function prepara(link) {
        const dialog = document.createElement('dialog');
        dialog.className = 'file-dialog';
        dialog.setAttribute('aria-labelledby', 'file-title');
        dialog.innerHTML = '<div class="file-dialog-head"><div><div class="eyebrow">DOCUMENTO DELLA BACHECA</div><h2 id="file-title"></h2></div><button class="icon-btn" type="button" aria-label="Chiudi documento">×</button></div><p class="file-status" role="status">Preparazione del file…</p><div class="file-actions" hidden><button class="file-save" type="button"></button><button class="file-download" type="button" hidden>Scarica il file</button><button class="file-preview-btn" type="button" hidden>Anteprima PDF</button></div><p class="file-hint" hidden></p><div class="file-preview" hidden></div>';
        const status = dialog.querySelector('.file-status');
        const actions = dialog.querySelector('.file-actions');
        const save = dialog.querySelector('.file-save');
        const preview = dialog.querySelector('.file-preview');
        const hint = dialog.querySelector('.file-hint');
        let objectUrl, abort = new AbortController(), downloading = false;
        const filename = (link.dataset.filename || 'Allegato').replace(/.*[\\/]/, '').replace(/[\x00-\x1f\x7f]/g, '') || 'Allegato';
        dialog.querySelector('h2').textContent = filename;
        dialog.querySelector('.icon-btn').onclick = function () { dialog.close(); };
        dialog.addEventListener('click', function (ev) { if (ev.target === dialog) dialog.close(); });
        dialog.addEventListener('close', function () {
            abort.abort();
            // I gestori dei download possono leggere il blob dopo il click.
            if (objectUrl) setTimeout(function () { URL.revokeObjectURL(objectUrl); }, downloading ? 60000 : 0);
            dialog.remove();
            link.focus();
        }, {once: true});
        document.body.appendChild(dialog);
        dialog.showModal();
        try {
            const response = await fetch(link.href, {credentials: 'same-origin', cache: 'no-store', signal: abort.signal});
            if (!response.ok) throw new Error('download');
            const bytes = await response.arrayBuffer();
            if (!dialog.open) return;
            // Riconosci anche i PDF serviti da proxy con un Content-Type generico.
            const signature = new Uint8Array(bytes, 0, Math.min(bytes.byteLength, 5));
            const isPdf = String.fromCharCode.apply(null, signature) === '%PDF-';
            let mime = isPdf ? 'application/pdf' : (response.headers.get('Content-Type') || 'application/octet-stream').split(';')[0];
            if (/^(text\/html|application\/xhtml\+xml|image\/svg\+xml)$/i.test(mime)) mime = 'application/octet-stream';
            const file = new File([bytes], filename, {type: mime});
            objectUrl = URL.createObjectURL(file);
            let canShare = false;
            try { canShare = !!(navigator.share && navigator.canShare && navigator.canShare({files: [file]})); } catch (_) {}
            status.textContent = 'File pronto · ' + (file.size < 1048576 ? Math.max(1, Math.round(file.size / 1024)) + ' KB' : (file.size / 1048576).toFixed(1) + ' MB');
            save.textContent = canShare ? 'Salva o condividi' : 'Scarica il file';
            hint.textContent = canShare ? 'Su iPhone scegli “Salva su File” nel menu di condivisione.' : 'Se il browser non salva il documento, apri UniScuola da Safari o dal browser del dispositivo e riprova.';
            hint.hidden = false;
            actions.hidden = false;
            function download() {
                const a = document.createElement('a');
                a.href = objectUrl;
                a.download = filename;
                dialog.appendChild(a);
                downloading = true;
                a.click();
                a.remove();
            }
            const downloadButton = dialog.querySelector('.file-download');
            downloadButton.hidden = !canShare;
            downloadButton.onclick = download;
            save.onclick = async function () {
                // Un secondo tap conserva l’attivazione utente anche con download Argo lenti.
                if (canShare) {
                    try { await navigator.share({files: [file], title: filename}); }
                    catch (error) {
                        if (error.name !== 'AbortError') status.textContent = 'Condivisione non disponibile. Apri Home Assistant in Safari per salvare il file.';
                    }
                } else {
                    download();
                }
            };
            if (isPdf) {
                const button = dialog.querySelector('.file-preview-btn');
                button.hidden = false;
                button.onclick = function () {
                    if (!preview.firstChild) {
                        const frame = document.createElement('iframe');
                        frame.title = 'Anteprima ' + filename;
                        frame.src = objectUrl;
                        preview.appendChild(frame);
                    }
                    preview.hidden = !preview.hidden;
                    button.textContent = preview.hidden ? 'Anteprima PDF' : 'Chiudi anteprima';
                };
            }
        } catch (error) {
            if (error.name !== 'AbortError') status.textContent = 'Download non riuscito. Chiudi e riprova; se necessario sincronizza il registro.';
        }
    }
}());
