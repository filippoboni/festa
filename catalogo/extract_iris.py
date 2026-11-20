"""Estrazione Iris Ceramica -> output/iris/<nome>.csv nello schema normalizzato.

Uso:
  python extract_iris.py armonie      # pilota su una collezione
  python extract_iris.py --all        # tutte le collezioni
Client generato da reverse-api-engineer, run_id d0a92de5cbe0 (clients/iris/).
Fonte: solo HTML (nessuna API JSON), parsing con BeautifulSoup.
"""
from __future__ import annotations

import csv
import datetime
import json
import re
import sys
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from common import ROOT, cached_call

sys.path.insert(0, str(ROOT / "clients" / "iris"))
import api_client as ic  # noqa: E402

SITE = "iris"
BASE = ic.BASE_URL
FIELDS = ["brand", "collezione", "codice_articolo", "colore", "effetto", "formato_cm", "spessore_mm",
          "finitura", "rettificato", "destinazione", "uso", "resistenza_scivolamento",
          "variazione_cromatica", "url_prodotto", "url_immagine", "url_scheda_tecnica",
          "url_catalogo_pdf", "data_estrazione", "attributi_extra"]



def _get(path: str, params: dict | None = None) -> BeautifulSoup:
    url = urljoin(BASE, path) + ("?" + urlencode(params) if params else "")

    def fetch():
        r = ic.SESSION.get(url, timeout=30)
        r.raise_for_status()
        return r.text

    return BeautifulSoup(cached_call(SITE, url.replace(BASE, ""), url, fetch, "html"), "html.parser")


ic._get = _get


# NB: effetto e ambienti (indoor/outdoor) NON sono ricavabili: /list-products.php carica i
# risultati via JS da /soluzioni?..., vietato da robots.txt. I link presenti nella pagina sono
# solo quelli del menu. Campi lasciati vuoti.


def mm(v: str) -> str:
    m = re.search(r"[\d.,]+", v or "")
    return m.group(0).replace(",", ".") if m else ""


def cm(v: str) -> str:
    return re.sub(r"\s*cm\s*$", "", (v or "").strip(), flags=re.I).lower().replace(" ", "")


def raw_codes(slug: str, art_slug: str) -> dict[str, str]:
    """codice -> nota a piè di tabella (es. '* Available at Cersaie 2025')."""
    soup = _get(f"/prodotti/{slug}/{art_slug}")
    notes = {}
    box = soup.find(id="item-1")
    if not box:
        return notes
    foot = " ".join(t.get_text(" ", strip=True) for t in box.find_all("table")[1:])
    for td in box.select("table td strong"):
        code = td.parent.get_text("", strip=True)
        code = re.sub(r"\s*[*†‡§#]+.*$", "", code).strip()
        mark = td.get_text(strip=True)
        m = re.search(re.escape(mark) + r"\s*([^*]+)", foot) if mark else None
        notes[code] = (mark + " " + m.group(1).strip()) if m else mark
    return notes


def collection_rows(slug: str, today: str) -> list[dict]:
    coll = ic.get_collection_articles(slug)
    rows = []
    for art in coll["articles"]:
        d = ic.get_article_detail(slug, art["slug"])
        tipo = (d.get("type") or art.get("type") or "").lower()
        destin = "pavimento" if "paviment" in tipo else "rivestimento" if "rivestiment" in tipo else ""
        notes = raw_codes(slug, art["slug"])
        for f in d["formats"]:
            fin = f.get("finitura", "")
            extra = {k: v for k, v in f.items() if k not in ("formato", "codice", "spessore", "finitura", "rettificato")}
            extra.update({"tipo_pagina": d.get("type", ""), "nota_codice": notes.get(f.get("codice", ""), ""),
                          "immagini": d["images"][1:6], "certificazioni": d["certifications"],
                          "n_pezzi_speciali": len(d["special_pieces"]),
                          "fonte": "html"})
            rows.append({
                "brand": "Iris Ceramica", "collezione": coll["name"].title() if coll["name"].isupper() else coll["name"],
                "codice_articolo": f.get("codice", ""), "colore": d["name"],
                "effetto": "", "formato_cm": cm(f.get("formato", "")),
                "spessore_mm": mm(f.get("spessore", "")), "finitura": fin,
                # cella vuota sul sito = dato non dichiarato, non "no"
                "rettificato": "si" if f.get("rettificato") else "",
                "destinazione": destin, "uso": "",
                "resistenza_scivolamento": "", "variazione_cromatica": "",
                "url_prodotto": d["url"], "url_immagine": d["images"][0] if d["images"] else art.get("thumbnail_url", ""),
                "url_scheda_tecnica": "", "url_catalogo_pdf": d.get("catalog_pdf") or coll.get("catalog_pdf", ""),
                "data_estrazione": today, "attributi_extra": json.dumps(extra, ensure_ascii=False),
            })
    return rows


def main(argv: list[str]) -> None:
    today = datetime.date.today().isoformat()
    if argv and argv[0] == "--all":
        slugs = [c["slug"] for c in ic.list_collections()]
        name = "catalogo"
    else:
        slugs = argv or ["armonie"]
        name = "pilota_" + "_".join(slugs)
    rows: list[dict] = []
    for s in slugs:
        try:
            r = collection_rows(s, today)
            print(f"{s}: {len(r)} righe", flush=True)
            rows += r
        except Exception as e:  # noqa: BLE001
            print(f"{s}: ERRORE {e}", flush=True)
    out = ROOT / "output" / SITE / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} righe -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
