# Catalogo ceramiche – report estrazioni

Stato: **piloti** (una collezione per sito). Scarico completo non ancora eseguito.
Generato da `build_excel.py` → `output/catalogo_completo.xlsx` / `.csv` + un JSON per sito.

## Fonti per sito

| Brand | run_id | Fonte dati | robots.txt | Pilota |
|---|---|---|---|---|
| Mirage | `52e4de75ad0e` | API JSON `/api/filters` + JSON Nuxt incorporato nelle pagine SSR | nessuna restrizione | Clay: 10 colori, 48 righe |
| Iris Ceramica | `d0a92de5cbe0` | **solo HTML** (nessuna API), BeautifulSoup | vietati `/soluzioni?…`, `/html/`, `/old/`, `/vt/`, asset | Armonie: 18 colori, 65 codici/righe |
| casa39.it (rivenditore) | – | non estratto: protezione anti-bot Anubis su tutto il sito | – | – |

Totali catalogo: Mirage 37 collezioni / 520 prodotti-colore (API) – 556 pagine prodotto (sitemap).

## Copertura campi (piloti, % righe compilate)

| Campo | Mirage | Iris |
|---|---|---|
| codice_articolo | 100 (codice colore) | 100 (codice per formato) |
| colore, formato, spessore, finitura | 100 | 100 |
| effetto | 100 (livello collezione) | 0 |
| rettificato | 0 | 0 (colonna vuota sul sito) |
| destinazione | 100 (livello collezione) | 100 (da tipo pagina) |
| uso | 100 | 0 |
| resistenza_scivolamento | 100 | 0 |
| variazione_cromatica | 100 | 0 |
| url_scheda_tecnica | 100 | 0 |
| url_catalogo_pdf, url_immagine, url_prodotto | 100 | 100 |

## Lacune e scelte
- Campi mancanti lasciati vuoti, mai dedotti.
- Formati uniformati come `lato corto x lato lungo` (es. Iris `120X60 cm` → `60x120`).
- Mirage: nessun codice articolo per formato sul sito; `rettificato` non pubblicato. Client con User-Agent Chrome (UA Python → 403).
- Iris: effetto/uso non ricavabili senza `/soluzioni?…` (vietato da robots). Scivolosità, variazione cromatica e rettificato probabilmente solo nei PDF.
- Iris: client modificato dopo la generazione per togliere l'impersonificazione TLS di Chrome (`curl_cffi`): serve solo libcurl perché l'OpenSSL di Python fallisce l'handshake.
- Immagini e PDF non scaricati: solo URL.

## Struttura
- `clients/<sito>/` client generati da reverse-api-engineer
- `common.py` rate limit 1 req/s per dominio, retry con backoff, cache in `raw/<sito>/`
- `extract_<sito>.py [collezione | --all]` → `output/<sito>/*.csv`
- `build_excel.py` → catalogo unificato con colonna `produttore`
