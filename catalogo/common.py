"""Utility condivise: rate limit per dominio, retry con backoff, cache risposte grezze."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"

_last: dict[str, float] = {}
_lock = threading.Lock()
MIN_INTERVAL = 1.0  # secondi tra due richieste allo stesso dominio


def throttle(url: str) -> None:
    host = urlsplit(url).netloc or url
    with _lock:
        wait = _last.get(host, 0) + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.monotonic()


def cache_path(site: str, key: str, ext: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("_")[:120]
    if len(safe) < len(key) or not safe:
        safe = f"{safe[:80]}_{hashlib.sha1(key.encode()).hexdigest()[:10]}"
    p = RAW / site / f"{safe}.{ext}"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def cached_call(site: str, key: str, url: str, fetch: Callable[[], object], ext: str = "html",
                retries: int = 4):
    """Restituisce la risposta dalla cache raw/<site>/ o la scarica (rate limit + retry)."""
    p = cache_path(site, key, ext)
    if p.exists():
        txt = p.read_text(encoding="utf-8")
        return json.loads(txt) if ext == "json" else txt
    err = None
    for attempt in range(retries):
        throttle(url)
        try:
            data = fetch()
            p.write_text(json.dumps(data, ensure_ascii=False) if ext == "json" else data, encoding="utf-8")
            return data
        except Exception as e:  # noqa: BLE001
            err = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (400, 401, 403, 404):
                break
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"{url}: {err}")
