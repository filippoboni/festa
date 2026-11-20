# Mirage Ceramiche – API Client

Reverse-engineered Python client for the public product catalogue of
[mirage.it](https://mirage.it/it) (Italian locale).

## APIs discovered

| Source | URL | Type |
|--------|-----|------|
| Filter/search | `GET /api/filters` | **REST JSON** |
| Collections list | `GET /it/products/collections` | SSR HTML + embedded payload |
| Collection items | `GET /it/products/collections/{slug}` | SSR HTML + embedded payload |
| Product detail | `GET /it/products/{slug}` | SSR HTML + embedded payload |

### No authentication required

All endpoints are publicly accessible. No cookies, tokens, or login needed.

---

## REST API: `/api/filters`

The only true REST endpoint. Returns faceted filters and paginated product results.

```
GET https://mirage.it/api/filters
```

### Query parameters

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `lng` | string | `it` | Language: `it`, `en`, `de`, `fr`, `es` |
| `market` | string | `europe` | Measurement units: `europe` (cm+in), `north-america` (in only) |
| `items_per_page` | int | `60` | Products per page |
| `offset` | int | `0` | Zero-based offset for pagination |
| `pa_effetto-materiale` | string | — | Effect/material facet value ID |
| `pa_colore` | string | — | Colour facet value ID |
| `pa_formato-group-cm` | string | — | Format facet value ID |
| `pa_spessore-group` | string | — | Thickness facet value ID |
| `pa_superficie-group` | string | — | Surface finish facet value ID |
| `pa_applicazioni` | string | — | Application facet value ID |
| `pa_collezioni` | string | — | Collection facet value ID |
| `pa_designer` | string | — | Designer/architect facet value ID |

### Response structure

```json
{
  "facets": [
    {
      "title": "Effetto / Materiale",
      "value": "pa_effetto-materiale",
      "items": [
        {"label": "Cementi", "value": "89", "count": "91"},
        ...
      ]
    }
  ],
  "total": "520",
  "results": [
    {
      "slug": "clay-cl01",
      "button": {"title": "Clay CL01 Calm", "action": {"to": "/products/clay-cl01"}},
      "indoor": true,
      "outdoor": false,
      "minimal": {"asset": {"origin_id": "...", "cdn": "thron", ...}},
      "ambient": {"asset": {...}}
    },
    ...
  ]
}
```

**Total products:** 520 (as of the capture date). Paginate using `offset`.

---

## SSR pages (Nuxt 3 `__NUXT_DATA__` decoder)

The remaining three endpoints return server-side-rendered HTML pages that embed
all data in a `<script id="__NUXT_DATA__">` JSON blob.

The blob uses the **devalue flat-array format** (Nuxt 3 / `@nuxt/devalue`):
- The root is at index 0.
- Object values and array elements are indices into the flat array.
- Primitives (strings, numbers, booleans, `null`) are stored as literals.
- Tagged types like `["ShallowReactive", N]` are reactive wrappers; the client
  unwraps them transparently.

Index 3 in the flat array is always the `asyncData` map (`{key: index, ...}`).
The page-specific data key is identified as the one that maps to the highest
flat-array index (the locales key `$f3dj1ewadft6tz`, `geolist-it`, and
`geo-market` are static and always at lower indices).

---

## Bot detection

The site returns **HTTP 403** for requests with standard Python/Requests user
agents. The HeadlessChrome user agent (observed in real browser traffic) passes
the check:

```
Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)
HeadlessChrome/153.0.0.0 Safari/537.36
```

The `sec-ch-ua`, `sec-ch-ua-mobile`, and `sec-ch-ua-platform` headers must also
be present. These are hardcoded in the client.

---

## Image URLs

Product images are served from two CDNs:

**Thron CDN** (most images):
```
https://mirage-cdn.thron.com/delivery/public/image/mirage/{origin_id}/9pkhty/std/{w}x{h}/{origin_id}
  ?scalemode=centered&format=auto&quality=auto-medium
```

**Cloudinary** (some promotional images):
```
https://res.cloudinary.com/dhgy28eyh/image/upload/c_fill,w_{w}/q_auto:eco/f_avif/v1/{origin_id}
```

## PDF document URLs

Technical data sheets, catalogs, and capitolati are on Thron CDN:
```
https://mirage-cdn.thron.com/delivery/public/content/mirage/{href_uuid}/9pkhty/fil/{filename}.pdf
```

---

## Installation

```bash
pip install requests
```

---

## Usage examples

```python
from api_client import (
    list_collections,
    get_collection_items,
    get_product_detail,
    search_products,
    get_filters,
    iter_all_products,
    build_image_url,
)

# 1. List all collections
collections = list_collections(lang="it")
for c in collections:
    print(c["title"], c["slug"], c["indoor"], c["outdoor"])

# 2. Get all variants in a collection
items = get_collection_items("clay", lang="it")
for item in items:
    print(item["slug"], item["title"])

# 3. Full technical detail for a product variant
detail = get_product_detail("clay-cl01", lang="it")
print(detail["title"])
print(detail["collection"])
for finish in detail["finishes"]:
    for fmt in finish["formats"]:
        print(f"  {finish['name']} – {fmt['cm']} – {fmt['thickness_mm']} mm")
for spec in detail["specs"]:
    print("Spec:", spec["label"])        # e.g. "R9", "V2"
for dl in detail["downloads"]:
    if dl.get("url"):
        print("PDF:", dl["title"], dl["url"])

# 4. Search with filters (paginated REST API)
result = search_products(
    lang="it",
    market="europe",
    filters={"pa_effetto-materiale": "89"},   # Cementi
    page=1,
    items_per_page=60,
)
print(f"{result['total']} matching products")
for p in result["results"]:
    print(p["slug"], p["button"]["title"])

# 5. Iterate over ALL products (handles pagination automatically)
for product in iter_all_products(filters={"pa_effetto-materiale": "89"}):
    print(product["slug"])

# 6. Get facet values (to build filter queries)
filters = get_filters()
for facet in filters["facets"]:
    print(facet["title"], facet["value"])
    for item in facet["items"]:
        print(f"  {item['label']} → value={item['value']} (count={item['count']})")

# 7. Build image URLs
url = build_image_url("c88af0b3-539c-4908-bf38-a7b93ced2ba2", width=800, height=533)
print(url)
```

---

## Data model

### Collection (from `list_collections`)

```python
{
  "title": "Clay",
  "slug": "clay",
  "url": "/products/collections/clay",
  "indoor": True,
  "outdoor": False,
  "atelier": False,
  "resource": False,
  "text": "...",
  "image": {
    "origin_id": "uuid",
    "cdn": "thron",
    "alt": "...",
    "url": "https://mirage-cdn.thron.com/..."
  }
}
```

### Collection item (from `get_collection_items`)

```python
{
  "slug": "clay-cl01",
  "title": "Clay CL01 Calm",
  "url": "/products/clay-cl01",
  "indoor": True,
  "outdoor": False,
  "atelier": False,
  "resource": False,
  "minimal_image": {"origin_id": "...", "cdn": "thron", "alt": "...", "url": "..."},
  "ambient_image": {"origin_id": "...", "cdn": "thron", "alt": "...", "url": "..."}
}
```

### Product detail (from `get_product_detail`)

```python
{
  "slug": "clay-cl01",
  "title": "Clay CL01 Calm",
  "collection": "Collezione Clay",
  "indoor": True,
  "outdoor": False,

  "finishes": [
    {
      "name": "Spazzolato",
      "formats": [
        {
          "cm": "120x120",
          "in": "48x48",
          "thickness_mm": ["9"],
          "size_cm2": 14400
        }
      ]
    }
  ],

  "specs": [
    {"label": "R9"},        # slip resistance class (indoor) → scivolamento
    {"label": "V2"},        # chromatic variation level       → variazione cromatica
    {"label": "R10 A+B"},   # slip resistance (outdoor)
  ],

  "downloads": [
    {
      "title": "Catalogo Clay",
      "type": "document",
      "url": "https://mirage-cdn.thron.com/delivery/public/content/mirage/{uuid}/9pkhty/fil/catalogo-clay-pdf.pdf"
    },
    {
      "title": "Scheda tecnica",
      "type": "document",
      "url": "https://mirage-cdn.thron.com/..."
    }
  ],

  "images": {
    "minimal": {"origin_id": "...", "cdn": "thron", "url": "..."},
    "ambient": {"origin_id": "...", "cdn": "thron", "url": "..."}
  }
}
```

---

## Notes

- **37 collections** are listed on the collections page (some shown in a "Novità"
  block and all in a full grid).
- **520 products** in the product catalogue as of the capture date.
- The `specs` list encodes both **slip resistance** (`R9`, `R10 A+B`) and
  **chromatic variation** (`V2`, `V3`, etc.) as text labels extracted from icon
  image alt-text. `rettificato` (rectified) is not stored as an explicit
  attribute in the page payload; all Mirage porcelain is rectified by default.
- The `outdoor` flag on a product (or the presence of a 20 mm thickness format)
  indicates outdoor suitability. The `applicazioni` facet in the filter API
  provides more detailed `destinazione d'uso` classification.
- PDF documents from the Thron CDN may require a browser session to download;
  direct `requests` fetches work for image thumbnails.
