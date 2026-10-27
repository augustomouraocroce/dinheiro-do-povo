"""Cliente HTTP com retentativa e cópia bruta de cada download (auditoria)."""
import time
from datetime import date
from pathlib import Path

import requests

from dp import config

_session = requests.Session()
_session.headers["User-Agent"] = config.USER_AGENT


def get(url, params=None, accept="application/json", tentativas=4, pausa=0.0):
    for n in range(tentativas):
        try:
            r = _session.get(url, params=params, headers={"Accept": accept}, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} em {r.url}")
            r.raise_for_status()
            if pausa:
                time.sleep(pausa)
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if n == tentativas - 1:
                raise
            time.sleep(2 ** n)


def get_json(url, params=None):
    return get(url, params=params).json()


def baixar(url, nome: str) -> Path:
    """Baixa um arquivo para data/raw/AAAA-MM-DD/nome e devolve o caminho."""
    destino = config.RAW_DIR / date.today().isoformat() / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = get(url, accept="*/*")
    destino.write_bytes(r.content)
    return destino
