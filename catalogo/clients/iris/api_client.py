"""
Iris Ceramica (www.irisceramica.it) - Python HTML scraping client
=================================================================
Data is served as plain HTML (no REST/JSON API discovered).
BeautifulSoup is used for robust HTML parsing.

Functions
---------
list_collections(cat=None)
    Returns every collection from /collezioni (or filtered by cat='pav'/'riv').

get_collection_articles(slug)
    Returns all articles/variants in a collection page /prodotti/<slug>.

get_article_detail(collection_slug, article_slug)
    Returns full technical specs for one article:
    /prodotti/<collection_slug>/<article_slug>.

search_products(effetto=None, colore=None, ambiente=None)
    Queries /list-products.php and returns matching collection-level results.
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import urljoin, urlencode

# The server's TLS handshake fails with Python's OpenSSL (SSLV3_ALERT_HANDSHAKE_FAILURE),
# while plain libcurl works. curl_cffi is used only as a libcurl binding:
# NO browser impersonation (modified after generation, see catalogo/report.md).
import curl_cffi.requests as requests

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.irisceramica.it"

# Session shared across all calls – keeps cookies & connections alive.
SESSION = requests.Session()

# Trust the proxy CA bundle (pre-configured for this environment).
import os as _os
_CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
SESSION.verify = _CA_BUNDLE if _os.path.exists(_CA_BUNDLE) else True

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(path: str, params: Optional[dict] = None) -> BeautifulSoup:
    """
    Perform a GET request and return a BeautifulSoup object.
    Raises requests.HTTPError for 4xx/5xx responses.

    Uses curl_cffi (libcurl) without browser impersonation.
    """
    url = urljoin(BASE_URL, path)
    kwargs: dict = {"timeout": 30}
    resp = SESSION.get(url, params=params, **kwargs)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _abs_url(href: str) -> str:
    """Convert a relative URL to absolute."""
    return urljoin(BASE_URL, href)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_collections(cat: Optional[str] = None) -> list[dict]:
    """
    Return a list of collections.

    Parameters
    ----------
    cat : str, optional
        Filter by category:
        - None   → all collections  (/collezioni)
        - 'pav'  → floor tiles       (/listing-collezioni.php?cat=pav)
        - 'riv'  → wall tiles        (/listing-collezioni.php?cat=riv)

    Returns
    -------
    list of dict with keys:
        name        : str   – collection name  (e.g. "ARMONIE")
        description : str   – short tagline
        slug        : str   – URL slug         (e.g. "armonie")
        url         : str   – absolute URL to collection page
        thumbnail   : str   – absolute URL to thumbnail image (if present)
    """
    if cat in ("pav", "riv"):
        path = f"/listing-collezioni.php?cat={cat}"
    else:
        path = "/collezioni"

    soup = _get(path)
    collections: list[dict] = []
    seen: set[str] = set()

    # Collection cards are <a href="/prodotti/<slug>"> that contain an h2.
    # Layout: each card is a direct child anchor of the main listing container.
    for link in soup.select("a[href^='/prodotti/']"):
        href = link.get("href", "")
        # Only collection-level URLs: exactly /prodotti/<slug>
        # (article URLs have three path segments)
        parts = [p for p in href.strip("/").split("/") if p]
        if len(parts) != 2 or parts[0] != "prodotti":
            continue

        slug = parts[1]
        # Skip if slug looks like it has spaces or other anomalies
        if " " in slug or not slug:
            continue
        if slug in seen:
            continue

        name_el = link.find("h2")
        if not name_el:
            continue   # skip non-card anchor elements (menu items, etc.)
        name = name_el.get_text(strip=True)

        # Description: the next sibling generic/div inside the same card
        desc = ""
        for tag in link.find_all(["p", "span", "div"]):
            if tag == name_el:
                continue
            text = tag.get_text(strip=True)
            if text and text != name:
                desc = text
                break

        # Thumbnail image inside the card (usually not present on this listing page)
        img_el = link.find("img")
        thumbnail = _abs_url(img_el["src"]) if img_el and img_el.get("src") else ""

        seen.add(slug)
        collections.append(
            {
                "name": name,
                "description": desc,
                "slug": slug,
                "url": _abs_url(href),
                "thumbnail": thumbnail,
            }
        )

    return collections


def get_collection_articles(slug: str) -> dict:
    """
    Fetch a collection page and return all its articles/colour variants.

    Parameters
    ----------
    slug : str – collection slug, e.g. "armonie"

    Returns
    -------
    dict with keys:
        name         : str
        slug         : str
        description  : str
        num_colors   : str   – as stated on the page  (e.g. "18")
        num_formats  : str
        catalog_pdf  : str   – absolute URL to PDF catalogue (may be "")
        articles     : list[dict]
            Each article dict has:
                name           : str
                slug           : str
                url            : str
                thumbnail_url  : str
                type           : str  – "Pavimenti" | "Rivestimenti" | ...
    """
    soup = _get(f"/prodotti/{slug}")

    # --- Collection metadata ---
    name_el = soup.find(["h1", "h2"])
    name = name_el.get_text(strip=True) if name_el else slug.upper().replace("-", " ")

    desc_el = soup.select_one(".col-lg-5 p, .product-item__description, .paragrafo")
    description = desc_el.get_text(strip=True) if desc_el else ""

    # Counts (18 Colori / 9 FORMATI shown in a list at the top)
    num_colors = ""
    num_formats = ""
    for li in soup.select("li"):
        text = li.get_text(separator=" ", strip=True)
        m_col = re.match(r"(\d+)\s*(Colori|colori)", text)
        m_fmt = re.match(r"(\d+)\s*(FORMATI|Formati|formati)", text, re.I)
        if m_col:
            num_colors = m_col.group(1)
        if m_fmt:
            num_formats = m_fmt.group(1)

    # Catalog PDF download link
    catalog_pdf = ""
    for a in soup.select("a[href$='.pdf'], a[href*='/doc/']"):
        href = a.get("href", "")
        if href:
            catalog_pdf = _abs_url(href)
            break

    # --- Articles ---
    # Page structure (per collection page):
    # <h2>Pavimenti</h2>  or  <h2>Rivestimenti</h2>
    # <div class="model-41 ...">
    #   <div class="model-41__item">
    #     <div class="color-pav"><a href="/prodotti/<slug>/<article>"><img.../></a></div>
    #     <a class="hoverable-link" href="/prodotti/<slug>/<article>">
    #       <h3 class="model-41__color">Article Name</h3>
    #     </a>
    #   </div>
    # </div>

    articles: list[dict] = []
    seen_slugs: set[str] = set()

    # Walk through all section headings + item cards
    # We track the current section type from the nearest preceding h2.
    current_type = ""
    for el in soup.find_all(["h2", "div"]):
        # Section type heading
        if el.name == "h2":
            txt = el.get_text(strip=True)
            if txt in ("Pavimenti", "Rivestimenti"):
                current_type = txt
            continue

        # Article item card
        if "model-41__item" not in (el.get("class") or []):
            continue

        # Name: from h3 inside the hoverable-link anchor
        name_link = el.select_one("a.hoverable-link")
        if not name_link:
            continue
        h3 = name_link.find("h3")
        art_name = h3.get_text(strip=True) if h3 else name_link.get_text(strip=True)
        if not art_name:
            continue

        href = name_link.get("href", "")
        parts = [p for p in href.strip("/").split("/") if p]
        if len(parts) != 3 or parts[0] != "prodotti" or parts[1] != slug:
            continue

        article_slug = parts[2]
        if article_slug in seen_slugs:
            continue
        seen_slugs.add(article_slug)

        # Thumbnail: from the color-pav image
        img_el = el.select_one(".color-pav img")
        thumb = _abs_url(img_el["src"]) if img_el and img_el.get("src") else ""

        articles.append(
            {
                "name": art_name,
                "slug": article_slug,
                "url": _abs_url(href),
                "thumbnail_url": thumb,
                "type": current_type,
            }
        )

    return {
        "name": name,
        "slug": slug,
        "description": description,
        "num_colors": num_colors,
        "num_formats": num_formats,
        "catalog_pdf": catalog_pdf,
        "articles": articles,
    }


def get_article_detail(collection_slug: str, article_slug: str) -> dict:
    """
    Fetch full technical specification for a single article.

    Parameters
    ----------
    collection_slug : str – e.g. "armonie"
    article_slug    : str – e.g. "pavimenti-pietra-di-madrid"

    Returns
    -------
    dict with keys:
        collection      : str
        name            : str   – e.g. "Pietra Di Madrid"
        type            : str   – "Pavimenti" | "Rivestimenti"
        description     : str
        url             : str
        images          : list[str]  – absolute URLs of gallery/texture images
        catalog_pdf     : str        – absolute URL (may be "")
        certifications  : list[str]  – certification logo URLs
        formats         : list[dict]
            Each format dict has:
                formato     : str   – "120X60 cm"
                codice      : str   – article code, e.g. "8920010"
                spessore    : str   – thickness, e.g. "8 mm"
                finitura    : str   – finish, e.g. "Natural" / "Antislip"
                rettificato : bool  – True if cell contains "√"
        special_pieces  : list[dict] – same structure as formats (pezzi speciali)
        decorations     : list[str]  – raw text from "Decori e mosaici" section
    """
    soup = _get(f"/prodotti/{collection_slug}/{article_slug}")

    # --- Header ---
    hat_el = soup.select_one(".hat")
    collection = hat_el.get_text(strip=True) if hat_el else collection_slug

    title_el = soup.select_one("h1.title")
    name = title_el.get_text(strip=True) if title_el else article_slug

    subtitle_el = soup.select_one(".subtitle")
    art_type = subtitle_el.get_text(strip=True) if subtitle_el else ""

    para_el = soup.select_one(".paragrafo")
    description = para_el.get_text(strip=True) if para_el else ""

    url = f"{BASE_URL}/prodotti/{collection_slug}/{article_slug}"

    # --- Images ---
    images: list[str] = []
    seen_imgs: set[str] = set()
    for img in soup.select("img.carousel-cell-image, img.images, .gallery-prod img"):
        src = img.get("src", "")
        if src and src not in seen_imgs:
            seen_imgs.add(src)
            images.append(_abs_url(src))

    # Fallback: also collect any texture/ambienti/sfondo images
    for img in soup.select("img[src*='/images/prodotti/']"):
        src = img.get("src", "")
        if src and src not in seen_imgs:
            seen_imgs.add(src)
            images.append(_abs_url(src))

    # --- Catalog PDF (if present on the article page) ---
    catalog_pdf = ""
    for a in soup.select("a[href$='.pdf'], a[href*='/doc/']"):
        href = a.get("href", "")
        if href:
            catalog_pdf = _abs_url(href)
            break

    # --- Certifications (item-2) ---
    certifications: list[str] = []
    item2 = soup.find(id="item-2")
    if item2:
        for img in item2.find_all("img"):
            src = img.get("src", "")
            if src:
                certifications.append(_abs_url(src))

    # --- Technical formats table (item-1) ---
    formats = _parse_formats_table(soup, "item-1")

    # --- Special pieces table (item-4) ---
    special_pieces = _parse_formats_table(soup, "item-4")

    # --- Decorations / mosaics (item-3) ---
    decorations: list[str] = []
    item3 = soup.find(id="item-3")
    if item3:
        for p in item3.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            if text:
                decorations.append(text)
        # Also plain text divs
        for div in item3.find_all("div"):
            text = div.get_text(separator=" ", strip=True)
            if text and text not in decorations:
                decorations.append(text)

    return {
        "collection": collection,
        "name": name,
        "type": art_type,
        "description": description,
        "url": url,
        "images": images,
        "catalog_pdf": catalog_pdf,
        "certifications": certifications,
        "formats": formats,
        "special_pieces": special_pieces,
        "decorations": decorations,
    }


def _parse_formats_table(soup: BeautifulSoup, item_id: str) -> list[dict]:
    """
    Parse a technical table inside #<item_id>.

    Supported columns (case-insensitive match):
    FORMATI / Formato, Codice, SPESSORE / Spessore, Finitura / FINITURE,
    Rettificato, DESCRIZIONE.

    Returns list of dicts with normalised keys.
    """
    container = soup.find(id=item_id)
    if not container:
        return []

    table = container.find("table", class_=lambda c: c and "d-none" in c)
    if not table:
        table = container.find("table")
    if not table:
        return []

    headers: list[str] = []
    for th in table.find_all("th"):
        headers.append(th.get_text(strip=True).lower())

    rows: list[dict] = []
    for tr in table.find("tbody").find_all("tr"):
        # get_text with separator to handle <strong>*</strong> etc., then strip
        cells = [td.get_text(separator="", strip=True) for td in tr.find_all("td")]
        if not any(cells):
            continue
        row: dict = {}
        for i, h in enumerate(headers):
            if i >= len(cells):
                break
            val = cells[i]
            if "format" in h:
                row["formato"] = val
            elif "codice" in h or "codic" in h:
                # Strip footnote markers (* + letters) appended to code
                row["codice"] = re.sub(r"\s*[\*†‡§#]+.*$", "", val).strip()
            elif "spessor" in h:
                row["spessore"] = val
            elif "finitura" in h or "finiture" in h or "colori" in h:
                row["finitura"] = val
            elif "rettificat" in h:
                row["rettificato"] = "√" in val
            elif "descrizione" in h:
                row["descrizione"] = val
            else:
                row[h] = val
        if row:
            rows.append(row)

    return rows


def search_products(
    effetto: Optional[str] = None,
    colore: Optional[str] = None,
    ambiente: Optional[str] = None,
    page: int = 1,
) -> list[dict]:
    """
    Search products via /list-products.php.

    Parameters
    ----------
    effetto  : str, optional – e.g. "pietra", "legno", "marmo", "cemento-resina",
                               "cotto", "maiolica", "metallo", "vetro", "design", "colore"
    colore   : str, optional – e.g. "bianco", "grigio", "beige", "nero", "blu" …
    ambiente : str, optional – e.g. "cucina", "living", "bagno",
                               "outdoor", "wellness", "commerciale"
    page     : int           – page number (1-based); only used if site supports it.

    Returns
    -------
    list of dict (collection-level results) each with keys:
        name        : str
        slug        : str
        url         : str
        thumbnail   : str
    """
    params: dict = {}
    if effetto:
        params["effetto"] = effetto
    if colore:
        params["colore"] = colore
    if ambiente:
        params["ambiente"] = ambiente
    if page > 1:
        params["page"] = page

    soup = _get("/list-products.php", params=params)

    results: list[dict] = []
    seen: set[str] = set()

    for a in soup.select("a[href^='/prodotti/']"):
        href = a.get("href", "")
        parts = [p for p in href.strip("/").split("/") if p]
        # We want collection-level links: /prodotti/<slug>
        if len(parts) == 2 and parts[0] == "prodotti":
            slug = parts[1]
            if slug in seen:
                continue
            seen.add(slug)
            # Grab display name from heading or link text
            heading = a.find(["h2", "h3"])
            name = heading.get_text(strip=True) if heading else a.get_text(strip=True)
            img_el = a.find("img")
            thumb = _abs_url(img_el["src"]) if img_el and img_el.get("src") else ""
            results.append(
                {"name": name, "slug": slug, "url": _abs_url(href), "thumbnail": thumb}
            )

    return results


# ---------------------------------------------------------------------------
# Main – demo / smoke test
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Iris Ceramica – API Client Demo")
    print("=" * 60)

    # 1. List all collections
    print("\n[1] All collections:")
    all_collections = list_collections()
    for c in all_collections:
        print(f"  {c['name']:30s}  slug={c['slug']}")
    print(f"  → {len(all_collections)} collections found")

    # 2. Floor-tile collections
    print("\n[2] Floor-tile collections (cat=pav):")
    pav = list_collections(cat="pav")
    print(f"  → {len(pav)} floor-tile collections")

    # 3. Wall-tile collections
    print("\n[3] Wall-tile collections (cat=riv):")
    riv = list_collections(cat="riv")
    print(f"  → {len(riv)} wall-tile collections")

    # 4. Articles in ARMONIE collection
    print("\n[4] Articles in collection 'armonie':")
    coll = get_collection_articles("armonie")
    print(f"  Name:       {coll['name']}")
    print(f"  Num colors: {coll['num_colors']}")
    print(f"  Num formats:{coll['num_formats']}")
    print(f"  Catalog PDF:{coll['catalog_pdf']}")
    print(f"  Articles ({len(coll['articles'])}):")
    for art in coll["articles"][:5]:
        print(f"    [{art['type']:12s}] {art['name']:40s}  {art['slug']}")
    if len(coll["articles"]) > 5:
        print(f"    … and {len(coll['articles']) - 5} more")

    # 5. Article detail
    if coll["articles"]:
        first = coll["articles"][0]
        print(f"\n[5] Detail for: {first['slug']}")
        detail = get_article_detail("armonie", first["slug"])
        print(f"  Collection: {detail['collection']}")
        print(f"  Name:       {detail['name']}")
        print(f"  Type:       {detail['type']}")
        print(f"  Images:     {len(detail['images'])} found")
        print(f"  Formats ({len(detail['formats'])}):")
        for fmt in detail["formats"][:4]:
            rett = "√" if fmt.get("rettificato") else " "
            print(
                f"    [{rett}] {fmt.get('formato','?'):12s} "
                f"cod={fmt.get('codice','?'):12s} "
                f"sp={fmt.get('spessore','?'):6s} "
                f"fin={fmt.get('finitura','?')}"
            )
        if detail["certifications"]:
            print(f"  Certifications: {detail['certifications']}")

    # 6. Search products
    print("\n[6] Product search (effetto=pietra, colore=grigio):")
    results = search_products(effetto="pietra", colore="grigio")
    for r in results[:5]:
        print(f"  {r['name']:30s}  {r['url']}")
    print(f"  → {len(results)} results")


if __name__ == "__main__":
    main()
