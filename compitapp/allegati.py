"""Download temporaneo degli allegati: nessun token Argo passa al browser o al CDN."""
import json
from tempfile import SpooledTemporaryFile
from urllib.parse import urljoin, urlsplit

import requests

MAX_BYTES = 50 * 1024 * 1024
DOMINI_DOWNLOAD = ('portaleargo.it', 'argosoft.it', 'argosoft.cloud', 'amazonaws.com')


def leggi_allegati(valore):
    try:
        allegati = json.loads(valore or '[]')
    except (TypeError, ValueError):
        return []
    if not isinstance(allegati, list):
        return []
    return [a for a in allegati if isinstance(a, dict) and a.get('uid')]


def nome_download(nome):
    nome = str(nome or 'Allegato').replace('\\', '/').rsplit('/', 1)[-1]
    nome = ''.join(c for c in nome if ord(c) >= 32 and ord(c) != 127).strip()
    return nome if nome not in ('', '.', '..') else 'Allegato'


def tipo_file(file, nome):
    """Tipi deterministici, anche su sistemi senza database MIME installato."""
    posizione = file.tell()
    firma = file.read(16)
    file.seek(posizione)
    for prefisso, tipo in ((b'%PDF-', 'application/pdf'),
                           (b'\x89PNG\r\n\x1a\n', 'image/png'),
                           (b'\xff\xd8\xff', 'image/jpeg'),
                           (b'GIF87a', 'image/gif'), (b'GIF89a', 'image/gif')):
        if firma.startswith(prefisso):
            return tipo
    estensione = nome_download(nome).rsplit('.', 1)[-1].lower()
    return {'pdf': 'application/pdf', 'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'zip': 'application/zip', 'png': 'image/png', 'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg'}.get(estensione, 'application/octet-stream')


def _verifica_url(url):
    parti = urlsplit(url)
    host = (parti.hostname or '').lower()
    if (parti.scheme != 'https' or parti.username or parti.password
            or parti.port not in (None, 443)
            or not any(host == d or host.endswith('.' + d) for d in DOMINI_DOWNLOAD)):
        raise ValueError('Destinazione download non valida')


def scarica_file(url):
    """Segue solo redirect HTTPS verso Argo/S3; limita spazio e tempo del download."""
    file = SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode='w+b')
    try:
        for _ in range(4):
            _verifica_url(url)
            # Non inoltrare Authorization, x-auth-token o cookie della sessione Argo.
            with requests.get(url, stream=True, timeout=(10, 60), allow_redirects=False) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers['Location'])
                    continue
                r.raise_for_status()
                if int(r.headers.get('Content-Length') or 0) > MAX_BYTES:
                    raise ValueError('Allegato troppo grande (massimo 50 MB)')
                totale = 0
                for blocco in r.iter_content(chunk_size=64 * 1024):
                    totale += len(blocco)
                    if totale > MAX_BYTES:
                        raise ValueError('Allegato troppo grande (massimo 50 MB)')
                    file.write(blocco)
                file.seek(0)
                return file
        raise ValueError('Troppi reindirizzamenti durante il download')
    except Exception:
        file.close()
        raise
