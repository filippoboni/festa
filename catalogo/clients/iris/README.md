# Iris Ceramica – Python API Client

**Target:** https://www.irisceramica.it  
**Language:** Italian (`.it` domain)

---

## Important: No REST / JSON API

After full browser exploration and network traffic analysis, **no REST API or JSON
endpoint exists on this site**. All data is embedded in server-rendered HTML pages.
The client therefore performs HTTP requests and parses HTML with
[BeautifulSoup 4](https://www.crummy.com/software/BeautifulSoup/).

---

## Dependencies

```bash
pip install requests beautifulsoup4 curl_cffi
```

| Package | Purpose |
|---|---|
| `curl_cffi` | Impersonates Chrome's TLS fingerprint so the server does not reject the handshake (plain `urllib3` triggers an `SSLV3_ALERT_HANDSHAKE_FAILURE`). Falls back to `requests` if unavailable. |
| `beautifulsoup4` | HTML parsing |

The script automatically trusts the proxy CA bundle at `/root/.ccr/ca-bundle.crt`
when it exists (agent-proxy environment).

---

## Usage

```bash
python api_client.py          # runs the built-in demo / smoke-test
```

Or import in your code:

```python
from api_client import list_collections, get_collection_articles, get_article_detail, search_products
```

---

## Functions

### `list_collections(cat=None) → list[dict]`

Returns every collection from the site.

| `cat` value | Endpoint fetched | Returns |
|---|---|---|
| `None` (default) | `/collezioni` | All collections (34) |
| `'pav'` | `/listing-collezioni.php?cat=pav` | Floor-tile collections only |
| `'riv'` | `/listing-collezioni.php?cat=riv` | Wall-tile collections only |

**Each dict:**

```python
{
    "name":        "ARMONIE",
    "description": "Assonanze di stile ispirate da originali",
    "slug":        "armonie",
    "url":         "https://www.irisceramica.it/prodotti/armonie",
    "thumbnail":   "",   # usually empty on listing page
}
```

---

### `get_collection_articles(slug) → dict`

Fetches the collection overview page `/prodotti/<slug>`.

```python
coll = get_collection_articles("armonie")
# coll["articles"] is a list of 18 article dicts
```

**Return dict:**

```python
{
    "name":        "Armonie",
    "slug":        "armonie",
    "description": "...",
    "num_colors":  "18",
    "num_formats": "9",
    "catalog_pdf": "https://www.irisceramica.it/doc/cataloghi_catalogues/armonie-696.pdf",
    "articles": [
        {
            "name":          "Pietra di Madrid",
            "slug":          "pavimenti-pietra-di-madrid",
            "url":           "https://www.irisceramica.it/prodotti/armonie/pavimenti-pietra-di-madrid",
            "thumbnail_url": "https://www.irisceramica.it/images/prodotti/armonie/colori/files/pietra_di_madrid.jpg",
            "type":          "Pavimenti",   # or "Rivestimenti"
        },
        ...
    ],
}
```

---

### `get_article_detail(collection_slug, article_slug) → dict`

Fetches the full article page `/prodotti/<collection_slug>/<article_slug>`.

```python
detail = get_article_detail("armonie", "pavimenti-pietra-di-madrid")
```

**Return dict:**

```python
{
    "collection":    "armonie",
    "name":         "Pietra Di Madrid",
    "type":         "Pavimenti",          # Pavimenti | Rivestimenti
    "description":  "...",
    "url":          "https://...",
    "images":       [                     # gallery/texture/ambiente images
        "https://www.irisceramica.it/images/prodotti/armonie/pietra_di_madrid/texture/pietra_di_madrid.jpg",
        "https://www.irisceramica.it/images/prodotti/armonie/pietra_di_madrid/ambienti/...",
        ...
    ],
    "catalog_pdf":  "",                   # may be present on some articles
    "certifications": [                   # certification logo URLs
        "https://www.irisceramica.it/images/certificazioni/leed.png"
    ],
    "formats": [                          # from "Formati e finiture" table (item-1)
        {
            "formato":     "120X60 cm",
            "codice":      "8920010",
            "spessore":    "8 mm",
            "finitura":    "Natural",     # Natural | Antislip | Glossy | Active | ...
            "rettificato": False,         # True if √ present
        },
        {
            "formato":     "120X60 cm",
            "codice":      "89200168",
            "spessore":    "8 mm",
            "finitura":    "Antislip",
            "rettificato": False,
        },
        ...
    ],
    "special_pieces": [...],  # "Pezzi speciali" table (item-4), same structure
    "decorations":    [...],  # text from "Decori e mosaici" section (item-3)
                              # may contain R10/R11/R12 slip-resistance codes
}
```

---

### `search_products(effetto, colore, ambiente, page) → list[dict]`

Queries `/list-products.php` and returns matching **collection-level** results
(the site does not filter to individual articles at this endpoint).

```python
results = search_products(effetto="pietra", colore="grigio")
# Returns collection dicts: name, slug, url, thumbnail
```

**Filter values observed on site:**

| Parameter | Known values |
|---|---|
| `effetto` | `pietra`, `legno`, `marmo`, `cemento-resina`, `cotto`, `maiolica`, `metallo`, `vetro`, `design`, `colore` |
| `colore` | `bianco`, `grigio`, `beige`, `nero`, `blu`, `verde`, `marrone`, `rosso`, `arancione`, `giallo`, `rosa`, `bordeaux`, `azzurro`, `oro`, `platino` |
| `ambiente` | `cucina`, `living`, `bagno`, `outdoor`, `wellness`, `commerciale` |

> **Note:** The filter sidebar on the page actually links to `/soluzioni?…` (which is
> excluded by robots.txt). Using `list-products.php?…` directly works and is
> robots-compliant.

---

## Image URL Patterns

| Image type | Pattern |
|---|---|
| Colour swatch | `/images/prodotti/<collection>/colori/files/<article_slug>.jpg` |
| Texture tile | `/images/prodotti/<collection>/<article>/texture/<article>.jpg` |
| Room scene | `/images/prodotti/<collection>/<article>/ambienti/<filename>.jpg` |
| Background hero | `/images/prodotti/<collection>/<article>/sfondo/<filename>.jpg` |
| Certification logo | `/images/certificazioni/<cert>.png` |

Catalogue PDFs: `/doc/cataloghi_catalogues/<collection_name>-<id>.pdf`

---

## Technical attributes available in HTML

| Attribute | Available | Location |
|---|---|---|
| Codice articolo | ✅ | `formats[n]["codice"]` |
| Formato | ✅ | `formats[n]["formato"]` |
| Spessore | ✅ | `formats[n]["spessore"]` |
| Finitura | ✅ | `formats[n]["finitura"]` |
| Rettificato | ✅ | `formats[n]["rettificato"]` (bool) |
| Pavimento / Rivestimento | ✅ | `type` field (from page subtitle) |
| Antislip / slip resistance | ⚠️ Partial | `finitura == "Antislip"` or R-class codes in `decorations` |
| Indoor / Outdoor | ⚠️ Inferred | Pavimento + "Active" collection = outdoor capable |
| Variazione cromatica | ❌ | Not present in HTML |
| PEI class | ❌ | Not present in HTML |
| Certifications | ✅ | `certifications` list of logo URLs |
| Images | ✅ | `images` list |
| Catalogue PDF | ✅ | `catalog_pdf` on collection page |

---

## robots.txt compliance

The following paths are excluded and not visited:
- `/soluzioni` with query parameters
- `/html/`
- `/old/`
- `/vt/`

No login is performed. No PDFs or images are downloaded.
