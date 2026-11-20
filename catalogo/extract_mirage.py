"""Estrazione Mirage -> output/mirage/<nome>.csv nello schema normalizzato.

Uso:
  python extract_mirage.py clay            # pilota su una collezione
  python extract_mirage.py --all           # tutte le collezioni
Client generato da reverse-api-engineer, run_id 52e4de75ad0e (clients/mirage/).
Fonte: API JSON /api/filters + JSON Nuxt incorporato nelle pagine SSR.
"""
from __future__ import annotations

import csv
import datetime
import json
import re
import sys
from pathlib import Path

from common import ROOT, cached_call

sys.path.insert(0, str(ROOT / "clients" / "mirage"))
import api_client as m  # noqa: E402

SITE = "mirage"
BASE = "https://mirage.it"

FIELDS = ["brand", "collezione", "codice_articolo", "colore", "effetto", "formato_cm", "spessore_mm",
          "finitura", "rettificato", "destinazione", "uso", "resistenza_scivolamento",
          "variazione_cromatica", "url_prodotto", "url_immagine", "url_scheda_tecnica",
          "url_catalogo_pdf", "data_estrazione", "attributi_extra"]

_orig_html = m._fetch_html
_orig_json = m._fetch_json


def _html(path: str) -> str:
    return cached_call(SITE, path, BASE + path, lambda: _orig_html(path), "html")


def _json(path: str, params: dict) -> dict:
    key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return cached_call(SITE, key, BASE + path, lambda: _orig_json(path, params), "json")


m._fetch_html = _html
m._fetch_json = _json


def active(facets: list, name: str) -> list[dict]:
    fc = next((f for f in facets if f["value"] == name), {"items": []})
    return [i for i in fc["items"] if str(i.get("count", "")) not in ("0", "")]


def collection_rows(slug: str, coll_ids: dict[str, str], today: str) -> list[dict]:
    items = m.get_collection_items(slug)
    details = [m.get_product_detail(i["slug"]) for i in items]
    if not details:
        return []
    coll_name = re.sub(r"^Collezione\s+", "", details[0].get("collection", "")).strip() or slug

    # attributi da API filtri (livello collezione) + famiglia colore per prodotto
    fid = coll_ids.get(coll_name.lower()) or coll_ids.get(slug.replace("-", " ").lower())
    effetto = destin = superf = ""
    fam: dict[str, list[str]] = {}
    roomvo: dict[str, dict] = {}
    if fid:
        res = m.search_products(filters={"pa_collezioni": fid}, items_per_page=100)
        effetto = ", ".join(i["label"] for i in active(res["facets"], "pa_effetto-materiale"))
        destin = "/".join(i["label"].lower() for i in active(res["facets"], "pa_applicazioni")
                          if i["label"] in ("Pavimento", "Rivestimento"))
        superf = ", ".join(i["label"] for i in active(res["facets"], "pa_superficie-group"))
        roomvo = {p["slug"]: p.get("roomvo") for p in res["results"]}
        for col in active(res["facets"], "pa_colore"):
            r = m.search_products(filters={"pa_collezioni": fid, "pa_colore": col["value"]}, items_per_page=100)
            for p in r["results"]:
                fam.setdefault(p["slug"], []).append(col["label"])

    rows = []
    for d in details:
        mt = re.match(rf"{re.escape(coll_name)}\s+(\S+)\s*(.*)$", d.get("title", ""), re.I)
        code, colore = (mt.group(1), mt.group(2)) if mt else ("", d.get("title", ""))
        dl = {x["title"].lower(): x.get("url", "") for x in d.get("downloads", [])}
        specs = [s["label"] for s in d.get("specs", [])]
        slip = ", ".join(s for s in specs if re.match(r"^(R\d|A\+?B)", s))
        vcr = ", ".join(s for s in specs if re.match(r"^V\d", s))
        uso = "/".join(k for k, b in (("indoor", d.get("indoor")), ("outdoor", d.get("outdoor"))) if b)
        for fin in d.get("finishes", []):
            for fmt in fin.get("formats", []):
                rows.append({
                    "brand": "Mirage", "collezione": coll_name, "codice_articolo": code, "colore": colore,
                    "effetto": effetto, "formato_cm": fmt["cm"], "spessore_mm": "/".join(fmt["thickness_mm"]),
                    "finitura": fin["name"], "rettificato": "", "destinazione": destin, "uso": uso,
                    "resistenza_scivolamento": slip, "variazione_cromatica": vcr,
                    "url_prodotto": f"{BASE}/it/products/{d['slug']}",
                    "url_immagine": d.get("images", {}).get("minimal", {}).get("url", ""),
                    "url_scheda_tecnica": dl.get("scheda tecnica", ""),
                    "url_catalogo_pdf": next((v for k, v in dl.items() if k.startswith("catalogo")), ""),
                    "data_estrazione": today,
                    "attributi_extra": json.dumps({
                        "formato_in": fmt.get("in", ""), "famiglia_colore": fam.get(d["slug"], []),
                        "superficie_filtro": superf, "roomvo": roomvo.get(d["slug"]),
                        "url_capitolato": dl.get("capitolato", ""),
                        "url_sistema_posa": dl.get("sistema di posa", ""),
                        "url_immagine_ambiente": d.get("images", {}).get("ambient", {}).get("url", ""),
                        "altre_specifiche": [s for s in specs if not re.match(r"^(R\d|V\d|A\+?B)", s)],
                        "fonte": "api /api/filters + nuxt ssr"}, ensure_ascii=False),
                })
    return rows


def main(argv: list[str]) -> None:
    today = datetime.date.today().isoformat()
    allf = m.get_filters()
    coll_ids = {i["label"].lower(): i["value"] for i in active(allf["facets"], "pa_collezioni")}
    if argv and argv[0] == "--all":
        slugs = [c["slug"] for c in m.list_collections()]
        name = "catalogo"
    else:
        slugs = argv or ["clay"]
        name = "pilota_" + "_".join(slugs)
    rows: list[dict] = []
    for s in slugs:
        try:
            r = collection_rows(s, coll_ids, today)
            print(f"{s}: {len(r)} righe", flush=True)
            rows += r
        except Exception as e:  # noqa: BLE001
            print(f"{s}: ERRORE {e}", flush=True)
    out = ROOT / "output" / SITE / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} righe -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
