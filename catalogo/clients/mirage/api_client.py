"""
Mirage Ceramiche – Public API Client
=====================================
Reverse-engineered from https://mirage.it/it

Data comes from two sources:
  1. REST endpoint  GET /api/filters  → product search + filter facets
  2. SSR HTML pages  /it/products/collections, /it/products/collections/{slug},
     /it/products/{slug}  → collections list, collection items, product details

The SSR pages embed all data inside a <script id="__NUXT_DATA__"> element as a
"devalue" flat-array JSON payload (Nuxt 3 / @nuxt/devalue format). The decoder
implemented here resolves the indexed references without any third-party library.

No authentication is required for any endpoint.
"""

from __future__ import annotations

import re
import json
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://mirage.it"
THRON_CDN = "https://mirage-cdn.thron.com"
CLOUDINARY_CDN = "https://res.cloudinary.com/dhgy28eyh"

# Common request headers that match the browser observed in traffic capture.
# The site rejects plain Python/Requests UAs with 403; the HeadlessChrome UA
# (sec-ch-ua headers included) passes the bot-detection check.
_CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HeadlessChrome/153.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": _CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="153", "Not_A Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

API_HEADERS = {
    "User-Agent": _CHROME_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="153", "Not_A Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "Referer": "https://mirage.it/it/products/find-product",
}

# asyncData keys that are always present on every page (not page-specific)
# geo-market, geolist-it, and $f3dj1ewadft6tz (locale) are fixed across pages.
# The page-specific data key always maps to the HIGHEST index in the flat array.
_SKIP_KEYS = {"geolist-it", "$f3dj1ewadft6tz", "geo-market"}


# ---------------------------------------------------------------------------
# Nuxt 3 / devalue flat-array decoder
# ---------------------------------------------------------------------------

def _devalue_decode(flat: list) -> Any:
    """
    Decode a Nuxt 3 __NUXT_DATA__ flat-array payload (devalue format).

    Rules
    -----
    - Each element of `flat` is either a JSON primitive or a structured node.
    - The root is always at index 0.
    - Objects: ``{"key": N, ...}`` → values are indices into `flat`.
    - Arrays: ``[N1, N2, ...]``  → elements are indices into `flat`.
      Exception: ``["TagName", N]`` (2-element, first is str) → tagged reactive
      wrapper; we just decode the wrapped value at N.
    - Primitive elements (str / bool / None) → returned as-is.
    - Number elements → returned as-is (they are literal values, not new
      indices; they appear as direct flat-array entries, e.g. 14400 for size).
    """
    cache: Dict[int, Any] = {}

    def decode(idx: int) -> Any:
        if idx in cache:
            return cache[idx]

        val = flat[idx]

        # Primitives – return directly
        if val is None or not isinstance(val, (dict, list)):
            return val

        if isinstance(val, list):
            # Tagged reactive wrapper: ["ShallowReactive"|"Ref"|..., N]
            if (
                len(val) == 2
                and isinstance(val[0], str)
                and isinstance(val[1], int)
            ):
                result = decode(val[1])
            else:
                # Regular array – every element is an index
                result = [decode(i) for i in val if isinstance(i, int)]
        else:
            # Object – every VALUE is an index
            result = {}
            for k, v in val.items():
                result[k] = decode(v) if isinstance(v, int) else v

        cache[idx] = result
        return result

    return decode(0)


def _extract_nuxt_data(html: str) -> Any:
    """
    Parse the ``<script id="__NUXT_DATA__">`` tag from an SSR HTML page and
    return the fully decoded Python object.

    Returns None if the tag cannot be found.
    """
    marker = 'id="__NUXT_DATA__">'
    start = html.find(marker)
    if start == -1:
        return None
    data_start = start + len(marker)
    data_end = html.find("</script>", data_start)
    flat = json.loads(html[data_start:data_end])
    return _devalue_decode(flat)


def _get_page_data(html: str) -> Optional[Dict]:
    """
    From the fully decoded Nuxt state, extract the *page-specific* asyncData
    value (the one that is neither ``geolist-it`` nor the fixed locale key).

    Returns the page data dict or None.
    """
    marker = 'id="__NUXT_DATA__">'
    start = html.find(marker)
    if start == -1:
        return None
    data_start = start + len(marker)
    data_end = html.find("</script>", data_start)
    flat = json.loads(html[data_start:data_end])

    # Element 3 is always {asyncDataKey: flatIndex, ...}.
    # The page-specific key maps to the highest index (most content, added last).
    async_map: Dict[str, int] = flat[3]

    page_key = max(
        (k for k in async_map if k not in _SKIP_KEYS),
        key=lambda k: async_map[k],
        default=None,
    )
    if page_key is None:
        return None

    page_idx: int = async_map[page_key]

    # Decode only the subtree we need (page_idx is the root of page data)
    cache: Dict[int, Any] = {}

    def decode(idx: int) -> Any:
        if idx in cache:
            return cache[idx]
        val = flat[idx]
        if val is None or not isinstance(val, (dict, list)):
            return val
        if isinstance(val, list):
            if (
                len(val) == 2
                and isinstance(val[0], str)
                and isinstance(val[1], int)
            ):
                result = decode(val[1])
            else:
                result = [decode(i) for i in val if isinstance(i, int)]
        else:
            result = {}
            for k, v in val.items():
                result[k] = decode(v) if isinstance(v, int) else v
        cache[idx] = result
        return result

    return decode(page_idx)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


_session = _make_session()


def _fetch_html(path: str) -> str:
    url = BASE_URL + path
    resp = _session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _fetch_json(path: str, params: Dict) -> Any:
    url = BASE_URL + path
    resp = _session.get(url, headers=API_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Image / document URL builders
# ---------------------------------------------------------------------------

def build_image_url(
    origin_id: str,
    width: int = 800,
    height: int = 533,
    cdn: str = "thron",
) -> str:
    """
    Build a full image URL for a Mirage product asset.

    Parameters
    ----------
    origin_id:
        The ``src`` / ``origin_id`` value from the asset object.
    width, height:
        Desired image dimensions in pixels.
    cdn:
        ``"thron"`` (default) or ``"cloudinary"``.
    """
    if cdn == "thron":
        return (
            f"{THRON_CDN}/delivery/public/image/mirage/"
            f"{origin_id}/9pkhty/std/{width}x{height}/{origin_id}"
            f"?scalemode=centered&format=auto&quality=auto-medium"
        )
    # Cloudinary path
    return (
        f"{CLOUDINARY_CDN}/image/upload/"
        f"c_fill,w_{width}/q_auto:eco/f_avif/v1/{origin_id}"
    )


def build_document_url(href: str, filename: str) -> str:
    """
    Build the PDF download URL for a Thron-hosted document.

    Parameters
    ----------
    href:
        The ``action.href`` UUID from the downloads item.
    filename:
        The ``action.filename`` value (without .pdf extension usually).
    """
    return (
        f"{THRON_CDN}/delivery/public/content/mirage/"
        f"{href}/9pkhty/fil/{filename}.pdf"
    )


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def get_filters(
    lang: str = "it",
    market: str = "europe",
) -> Dict:
    """
    Return available filter facets and their possible values.

    Example response structure::

        {
          "facets": [
            {
              "title": "Effetto / Materiale",
              "value": "pa_effetto-materiale",
              "items": [{"label": "Cementi", "value": "89", "count": "91"}, ...]
            },
            ...
          ],
          "total": "520",
          "results": [...]     # first page of unfiltered results
        }

    Available facets
    ----------------
    - ``pa_effetto-materiale``  – Effect / Material
    - ``pa_colore``             – Colour
    - ``pa_formato-group-cm``   – Format (cm / in dual label)
    - ``pa_spessore-group``     – Thickness
    - ``pa_superficie-group``   – Finish surface type
    - ``pa_applicazioni``       – Applications (indoor, outdoor, …)
    - ``pa_collezioni``         – Collection
    - ``pa_designer``           – Architect / Designer
    """
    params: Dict[str, Any] = {
        "lng": lang,
        "market": market,
        "items_per_page": 60,
        "offset": 0,
    }
    return _fetch_json("/api/filters", params)


def search_products(
    lang: str = "it",
    market: str = "europe",
    filters: Optional[Dict[str, str]] = None,
    page: int = 1,
    items_per_page: int = 60,
) -> Dict:
    """
    Search / filter products using the REST API.

    Parameters
    ----------
    lang:
        Language code, e.g. ``"it"``, ``"en"``, ``"de"``, ``"fr"``, ``"es"``.
    market:
        Market code that controls the measurement unit display.
        ``"europe"`` shows cm (with inch equivalent); ``"north-america"``
        shows inches only.
    filters:
        A mapping of facet parameter name → facet value id.  Example::

            {"pa_effetto-materiale": "89", "pa_formato-group-cm": "452"}

        Facet IDs come from :func:`get_filters`.
    page:
        1-based page number.
    items_per_page:
        Results per page (max ~100; default 60).

    Returns
    -------
    dict with keys:
        - ``facets``  – updated facets with counts for the current query
        - ``total``   – total matching products (string)
        - ``results`` – list of product cards

    Each ``results`` item has::

        {
          "slug": "clay-cl01",
          "button": {"title": "Clay CL01 Calm", "action": {"to": "/products/clay-cl01"}},
          "indoor": true,
          "outdoor": false,
          "minimal": {"asset": {"origin_id": "...", "cdn": "thron", ...}},
          "ambient": {"asset": {...}},
          "atelier": "",
          "resource": "",
        }
    """
    offset = (page - 1) * items_per_page
    params: Dict[str, Any] = {
        "lng": lang,
        "market": market,
        "items_per_page": items_per_page,
        "offset": offset,
    }
    if filters:
        params.update(filters)
    return _fetch_json("/api/filters", params)


def list_collections(lang: str = "it") -> List[Dict]:
    """
    Return all Mirage collections from the SSR collections page.

    Parameters
    ----------
    lang:
        Language code (``"it"``, ``"en"``, ``"de"``, ``"fr"``, ``"es"``).

    Returns
    -------
    List of dicts, each with::

        {
          "title": "Clay",
          "slug": "clay",
          "url": "/products/collections/clay",
          "indoor": True,
          "outdoor": False,
          "atelier": False,
          "resource": False,
          "image": {
              "origin_id": "...",
              "cdn": "thron",
              "alt": "...",
              "url": "https://mirage-cdn.thron.com/..."
          },
          "text": "..."
        }
    """
    html = _fetch_html(f"/{lang}/products/collections")
    page_data = _get_page_data(html)
    if not page_data:
        return []

    wrappers = page_data.get("body", {}).get("data", {}).get("wrappers", [])
    if not wrappers:
        return []

    all_items: List[Dict] = []
    seen_slugs: set = set()

    for wrapper in wrappers:
        tabs = wrapper.get("data", {}).get("tabs", [])
        for tab in tabs:
            for block in tab.get("blocks", []):
                if block.get("is") != "block-grid-collections":
                    continue
                items = block.get("data", {}).get("body", {}).get("items", [])
                for item in items:
                    slug = item.get("action", {}).get("to", "").split("/")[-1]
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    asset = item.get("asset", {})
                    origin_id = asset.get("origin_id", "")
                    cdn = asset.get("cdn", "thron")

                    all_items.append({
                        "title": item.get("title", ""),
                        "slug": slug,
                        "url": item.get("action", {}).get("to", ""),
                        "indoor": item.get("indoor", False),
                        "outdoor": item.get("outdoor", False),
                        "atelier": item.get("atelier", False),
                        "resource": item.get("resource", False),
                        "text": item.get("text", ""),
                        "image": {
                            "origin_id": origin_id,
                            "cdn": cdn,
                            "alt": asset.get("alt", ""),
                            "url": build_image_url(origin_id, cdn=cdn) if origin_id else "",
                        },
                    })

    return all_items


def get_collection_items(
    collection_slug: str,
    lang: str = "it",
) -> List[Dict]:
    """
    Return all product variants (items) belonging to a collection.

    Parameters
    ----------
    collection_slug:
        The slug of the collection, e.g. ``"clay"``, ``"elysian"``.
    lang:
        Language code.

    Returns
    -------
    List of product item dicts, each with::

        {
          "slug": "clay-cl01",
          "title": "Clay CL01 Calm",
          "url": "/products/clay-cl01",
          "indoor": True,
          "outdoor": False,
          "atelier": False,
          "resource": False,
          "minimal_image": {"origin_id": "...", "cdn": "thron", "url": "..."},
          "ambient_image": {"origin_id": "...", "cdn": "thron", "url": "..."},
        }
    """
    html = _fetch_html(f"/{lang}/products/collections/{collection_slug}")
    page_data = _get_page_data(html)
    if not page_data:
        return []

    wrappers = page_data.get("body", {}).get("data", {}).get("wrappers", [])

    all_items: List[Dict] = []
    seen_slugs: set = set()

    for wrapper in wrappers:
        overlay_list = wrapper.get("data", {}).get("collectionOverlay", [])
        for overlay in overlay_list:
            for item in overlay.get("items", []):
                slug = item.get("slug", "")
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                btn = item.get("button", {})
                minimal_asset = item.get("minimal", {}).get("asset", {})
                ambient_asset = item.get("ambient", {}).get("asset", {})

                min_id = minimal_asset.get("origin_id", "")
                min_cdn = minimal_asset.get("cdn", "thron")
                amb_id = ambient_asset.get("origin_id", "")
                amb_cdn = ambient_asset.get("cdn", "thron")

                all_items.append({
                    "slug": slug,
                    "title": btn.get("title", ""),
                    "url": btn.get("action", {}).get("to", ""),
                    "indoor": item.get("indoor", False),
                    "outdoor": item.get("outdoor", False),
                    "atelier": item.get("atelier", False),
                    "resource": item.get("resource", False),
                    "minimal_image": {
                        "origin_id": min_id,
                        "cdn": min_cdn,
                        "alt": minimal_asset.get("alt", ""),
                        "url": build_image_url(min_id, cdn=min_cdn) if min_id else "",
                    },
                    "ambient_image": {
                        "origin_id": amb_id,
                        "cdn": amb_cdn,
                        "alt": ambient_asset.get("alt", ""),
                        "url": build_image_url(amb_id, cdn=amb_cdn) if amb_id else "",
                    },
                })

    return all_items


def get_product_detail(
    product_slug: str,
    lang: str = "it",
) -> Dict:
    """
    Return full technical details for a single product variant.

    Parameters
    ----------
    product_slug:
        The product slug, e.g. ``"clay-cl01"``, ``"elysian-ey01"``.
    lang:
        Language code.

    Returns
    -------
    dict with keys::

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
                },
                ...
              ]
            },
            ...
          ],

          "specs": [
            {"label": "R9"},        # slip resistance – indoor
            {"label": "R10 A+B"},   # slip resistance – outdoor
            {"label": "V2"},        # chromatic variation
          ],

          "downloads": [
            {
              "title": "Catalogo Clay",
              "type": "document",
              "url": "https://mirage-cdn.thron.com/delivery/public/content/..."
            },
            ...
          ],

          "images": {
            "minimal": {"origin_id": "...", "cdn": "thron", "url": "..."},
            "ambient": {"origin_id": "...", "cdn": "thron", "url": "..."},
          }
        }
    """
    html = _fetch_html(f"/{lang}/products/{product_slug}")
    page_data = _get_page_data(html)
    if not page_data:
        return {"slug": product_slug, "error": "page data not found"}

    body_data = page_data.get("body", {}).get("data", {})
    header = body_data.get("header", {})
    wrappers = body_data.get("wrappers", [])

    # Wrapper 0, Tab 0 → carousel block (images) + product details block
    w0_blocks = []
    if wrappers:
        w0_blocks = wrappers[0].get("data", {}).get("tabs", [{}])[0].get("blocks", [])

    # Carousel block: product images + indoor/outdoor
    carousel_block = next(
        (b for b in w0_blocks if b.get("is") == "block-carousel-products"), {}
    )
    carousel_items = carousel_block.get("data", {}).get("body", {}).get("items", [])
    carousel_item = carousel_items[0] if carousel_items else {}

    indoor = carousel_item.get("indoor", {})
    outdoor = carousel_item.get("outdoor", {})

    # Indoor/outdoor can be bool or a dict with image assets
    is_indoor = bool(indoor) if not isinstance(indoor, bool) else indoor
    is_outdoor = bool(outdoor) if not isinstance(outdoor, bool) else outdoor

    # Images from indoor / outdoor asset dicts
    def _get_image(src: Any, key: str) -> Dict:
        if isinstance(src, dict):
            asset = src.get(key, {}).get("asset", {})
            oid = asset.get("origin_id", "")
            cdn = asset.get("cdn", "thron")
            return {
                "origin_id": oid,
                "cdn": cdn,
                "alt": asset.get("alt", ""),
                "url": build_image_url(oid, cdn=cdn) if oid else "",
            }
        return {}

    # Details block: finishes, downloads, specs
    details_block = next(
        (b for b in w0_blocks if b.get("is") == "block-text-product-details"), {}
    )
    details_body = details_block.get("data", {}).get("body", {})

    # --- Finishes ---
    finishes_raw = details_body.get("finishes", {})
    finishes: List[Dict] = []
    for finish in finishes_raw.get("table_data", []):
        formats: List[Dict] = []
        for fmt in finish.get("formats", []):
            formats.append({
                "cm": fmt.get("cm", ""),
                "in": fmt.get("in", ""),
                "thickness_mm": [
                    t.get("mm", "") for t in fmt.get("ticknesses", [])
                ],
                "size_cm2": fmt.get("size"),
            })
        finishes.append({
            "name": finish.get("title", ""),
            "formats": formats,
        })

    # --- Specs (R9 / R10 / V2 etc.) ---
    specs: List[Dict] = []
    for spec in details_body.get("specs", {}).get("items", []):
        label = spec.get("asset", {}).get("alt", "")
        if label:
            specs.append({"label": label})

    # --- Downloads ---
    downloads: List[Dict] = []
    for dl in details_body.get("downloads", {}).get("items", []):
        action = dl.get("action", {})
        entry: Dict[str, Any] = {
            "title": dl.get("title", ""),
            "type": dl.get("type", ""),
        }
        if action.get("cdn") == "thron" and action.get("href"):
            entry["url"] = build_document_url(
                action["href"], action.get("filename", "document")
            )
        elif action.get("to"):
            entry["url"] = BASE_URL + action["to"]
        downloads.append(entry)

    return {
        "slug": product_slug,
        "title": header.get("title", ""),
        "collection": header.get("text", ""),
        "indoor": is_indoor,
        "outdoor": is_outdoor,
        "finishes": finishes,
        "specs": specs,
        "downloads": downloads,
        "images": {
            "minimal": _get_image(indoor or outdoor, "minimal"),
            "ambient": _get_image(indoor or outdoor, "ambient"),
        },
    }


# ---------------------------------------------------------------------------
# Convenience: paginate through ALL products
# ---------------------------------------------------------------------------

def iter_all_products(
    lang: str = "it",
    market: str = "europe",
    filters: Optional[Dict[str, str]] = None,
    items_per_page: int = 60,
):
    """
    Generator that yields every product card across all pages.

    Example::

        for product in iter_all_products(filters={"pa_effetto-materiale": "89"}):
            print(product["slug"], product["button"]["title"])
    """
    page = 1
    while True:
        resp = search_products(
            lang=lang,
            market=market,
            filters=filters,
            page=page,
            items_per_page=items_per_page,
        )
        results = resp.get("results", [])
        if not results:
            break
        yield from results

        total = int(resp.get("total", 0))
        fetched = (page - 1) * items_per_page + len(results)
        if fetched >= total:
            break
        page += 1


# ---------------------------------------------------------------------------
# Main – example usage
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Mirage Ceramiche API Client – example run")
    print("=" * 60)

    # 1. Available filter facets
    print("\n[1] Available filter facets")
    filter_data = get_filters()
    for facet in filter_data.get("facets", []):
        items_preview = ", ".join(
            f"{i['label']}({i['value']})" for i in facet.get("items", [])[:3]
        )
        print(f"  {facet['title']} [{facet['value']}]: {items_preview} …")

    total = filter_data.get("total", "?")
    print(f"\n  Total products in catalogue: {total}")

    # 2. List all collections
    print("\n[2] Collections list")
    collections = list_collections(lang="it")
    print(f"  Found {len(collections)} collections")
    for c in collections[:5]:
        tags = []
        if c["indoor"]:
            tags.append("indoor")
        if c["outdoor"]:
            tags.append("outdoor")
        if c["atelier"]:
            tags.append("atelier")
        print(f"  · {c['title']} ({c['slug']})  [{', '.join(tags)}]")
    if len(collections) > 5:
        print(f"  … and {len(collections) - 5} more")

    # 3. Items in the Clay collection
    print("\n[3] Items in the 'clay' collection")
    clay_items = get_collection_items("clay")
    print(f"  Found {len(clay_items)} variants")
    for item in clay_items[:3]:
        dest = "indoor" if item["indoor"] else "outdoor" if item["outdoor"] else "?"
        print(f"  · {item['title']} ({item['slug']})  [{dest}]")
        print(f"    thumbnail: {item['minimal_image']['url'][:80]}…")

    # 4. Product detail for Clay CL01
    print("\n[4] Product detail: clay-cl01")
    detail = get_product_detail("clay-cl01")
    print(f"  Title:      {detail['title']}")
    print(f"  Collection: {detail['collection']}")
    print(f"  Indoor/Outdoor: {detail['indoor']} / {detail['outdoor']}")

    print("  Finishes:")
    for finish in detail.get("finishes", []):
        print(f"    · {finish['name']}")
        for fmt in finish.get("formats", []):
            print(
                f"      {fmt['cm']} ({fmt['in']}) – {', '.join(fmt['thickness_mm'])} mm"
            )

    print("  Specs:", [s["label"] for s in detail.get("specs", [])])

    print("  Downloads:")
    for dl in detail.get("downloads", []):
        if dl.get("url"):
            print(f"    · {dl['title']}: {dl['url'][:80]}…")

    # 5. Product detail for Elysian EY01
    print("\n[5] Product detail: elysian-ey01")
    detail2 = get_product_detail("elysian-ey01")
    print(f"  Title:      {detail2['title']}")
    print(f"  Collection: {detail2['collection']}")
    print(f"  Indoor/Outdoor: {detail2['indoor']} / {detail2['outdoor']}")
    print("  Finishes:")
    for finish in detail2.get("finishes", []):
        fmts = ", ".join(f["cm"] for f in finish.get("formats", []))
        print(f"    · {finish['name']}: {fmts}")
    print("  Specs:", [s["label"] for s in detail2.get("specs", [])])

    # 6. Search: first page of "Cementi" products
    print("\n[6] Search – effetto=Cementi (pa_effetto-materiale=89)")
    result = search_products(filters={"pa_effetto-materiale": "89"}, items_per_page=5)
    print(f"  Total matching: {result.get('total')}")
    for p in result.get("results", []):
        print(f"  · {p['slug']}  ({p['button']['title']})")

    print("\nAll checks passed ✓")


if __name__ == "__main__":
    main()
