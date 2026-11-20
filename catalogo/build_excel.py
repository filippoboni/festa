"""Unisce le estrazioni normalizzate di tutti i produttori in un unico catalogo.

Input:  output/<sito>/*.csv  (una riga per colore x formato x finitura, schema comune)
Output: output/catalogo_completo.csv, output/catalogo_completo.xlsx,
        output/<sito>.json (uno per produttore)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

SCHEMA = [
    "produttore", "brand", "collezione", "codice_articolo", "colore", "effetto",
    "formato_cm", "spessore_mm", "finitura", "rettificato", "destinazione", "uso",
    "resistenza_scivolamento", "variazione_cromatica", "url_prodotto",
    "url_immagine", "url_scheda_tecnica", "url_catalogo_pdf", "data_estrazione",
    "attributi_extra",
]

# brand -> gruppo produttore (riga che indica il produttore)
PRODUTTORE = {
    "Mirage": "Mirage Granito Ceramico S.p.A.",
    "Iris Ceramica": "Iris Ceramica Group",
    "Florim": "Florim Ceramiche S.p.A.",
    "Atlas Concorde": "Atlas Concorde (Gruppo Concorde)",
}


NOTE = [
    {"brand": "Mirage", "sito": "https://mirage.it/it", "run_id": "52e4de75ad0e",
     "fonte_dati": "API JSON /api/filters + JSON Nuxt incorporato nelle pagine HTML",
     "robots_txt": "nessuna restrizione",
     "note": "codice_articolo = codice colore (es. CL01), Mirage non pubblica codici per formato; "
             "effetto/destinazione a livello collezione (filtri API); rettificato non pubblicato sul sito"},
    {"brand": "Iris Ceramica", "sito": "https://www.irisceramica.it", "run_id": "d0a92de5cbe0",
     "fonte_dati": "solo HTML (nessuna API), parsing BeautifulSoup",
     "robots_txt": "vietati /soluzioni?…, /html/, /old/, /vt/, cartelle asset",
     "note": "effetto e uso non ricavabili (ricerca filtrata servita da /soluzioni?…, vietato da robots); "
             "colonna Rettificato presente ma vuota sul sito; scivolosità/variazione cromatica solo nei PDF"},
]


def norm_formato(v: str) -> str:
    """'120X60 cm' / '60x120' -> '60x120' (lato corto x lato lungo, virgola decimale)."""
    parts = [p.strip() for p in str(v).lower().replace("cm", "").split("x")]
    try:
        nums = [float(p.replace(",", ".")) for p in parts]
    except ValueError:
        return str(v).strip()
    if len(nums) != 2:
        return str(v).strip()
    fmt = lambda n: (str(int(n)) if n == int(n) else str(n).replace(".", ","))  # noqa: E731
    return "x".join(fmt(n) for n in sorted(nums))


def load_all() -> pd.DataFrame:
    frames = []
    for site_dir in sorted(p for p in OUT.iterdir() if p.is_dir()):
        for csv in sorted(site_dir.glob("*.csv")):
            df = pd.read_csv(csv, dtype=str, keep_default_na=False)
            df["_sito"] = site_dir.name
            frames.append(df)
    if not frames:
        raise SystemExit("Nessun CSV in output/<sito>/")
    df = pd.concat(frames, ignore_index=True)
    df["produttore"] = df["brand"].map(PRODUTTORE).fillna(df["brand"])
    df["formato_cm"] = df["formato_cm"].map(norm_formato)
    for col in SCHEMA:
        if col not in df.columns:
            df[col] = ""
    return df


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for brand, g in df.groupby("brand"):
        r = {"brand": brand, "righe": len(g),
             "collezioni": g["collezione"].nunique(),
             "colori": g[["collezione", "colore"]].drop_duplicates().shape[0],
             "codici_articolo_distinti": g["codice_articolo"].nunique()}
        for col in SCHEMA[2:]:
            r[col] = round(100 * (g[col].str.strip() != "").mean(), 1)
        rows.append(r)
    return pd.DataFrame(rows)


def style(ws, widths: dict[str, int]) -> None:
    head = PatternFill("solid", fgColor="1F3864")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, cell in enumerate(ws[1], start=1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(cell.value, 14)


def main() -> None:
    df = load_all()
    df = df.sort_values(["produttore", "brand", "collezione", "codice_articolo", "finitura", "formato_cm"])
    cat = df[SCHEMA]
    cat.to_csv(OUT / "catalogo_completo.csv", index=False, encoding="utf-8-sig")

    for sito, g in df.groupby("_sito"):
        recs = g[SCHEMA].to_dict(orient="records")
        for r in recs:
            try:
                r["attributi_extra"] = json.loads(r["attributi_extra"]) if r["attributi_extra"] else {}
            except json.JSONDecodeError:
                pass
        (OUT / f"{sito}.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")

    cov = coverage(df)
    xlsx = OUT / "catalogo_completo.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        cat.to_excel(xw, sheet_name="Catalogo", index=False)
        cov.to_excel(xw, sheet_name="Copertura", index=False)
        pd.DataFrame(NOTE).to_excel(xw, sheet_name="Fonti e note", index=False)
        style(xw.sheets["Fonti e note"], {"sito": 30, "fonte_dati": 50, "robots_txt": 40, "note": 110})
        style(xw.sheets["Catalogo"], {
            "produttore": 28, "brand": 14, "collezione": 20, "codice_articolo": 16,
            "colore": 18, "effetto": 16, "finitura": 16, "destinazione": 22,
            "resistenza_scivolamento": 18, "url_prodotto": 40, "url_immagine": 40,
            "url_scheda_tecnica": 40, "url_catalogo_pdf": 40, "attributi_extra": 60})
        style(xw.sheets["Copertura"], {"brand": 16})
    print(f"{len(cat)} righe -> {xlsx}")
    print(cov.to_string(index=False))


if __name__ == "__main__":
    main()
