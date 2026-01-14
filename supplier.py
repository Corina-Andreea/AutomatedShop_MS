import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup
from serpapi import GoogleSearch


# -----------------------------
# CONFIG
# -----------------------------
KNOWLEDGE_BASE_FILE = "knowledge_base.json"

# ✅ Set environment variable SERPAPI_KEY
# PowerShell:
#   $env:SERPAPI_KEY="...."
# CMD:
#   set SERPAPI_KEY=....
SERPAPI_KEY = "769f5198e747a3bab0c1885b77b2e97f51cce0415b35496e7574a9ad300740f6"

# ✅ Retailers / known sources (whitelist)
TRUSTED_DOMAINS = [
    # Romania
    "emag.ro",
    "altex.ro",
    "mediagalaxy.ro",
    "flanco.ro",
    "evomag.ro",
    "cel.ro",
    "pcgarage.ro",

    # EU (backup)
    "amazon.de",
    "amazon.it",
    "amazon.fr",
    "amazon.es",
]

# if you want to force only Romania:
# TRUSTED_DOMAINS = ["emag.ro", "altex.ro", "mediagalaxy.ro", "flanco.ro", "evomag.ro", "cel.ro", "pcgarage.ro"]

MAX_URLS_TO_TRY = 10
REQUEST_TIMEOUT = 10

# Optional: approximate conversion if we scrape EUR price (not required)
EUR_TO_RON = 5.0


class SupplierAgent:
    """
    SupplierAgent V2
    - Searches using SerpAPI Google engine
    - Restricts to trusted domains (retailers)
    - Scrapes price/specs/availability from real product pages
    - Uses JSON-LD & meta tags to extract price reliably
    - Caches results in knowledge_base.json
    """

    def __init__(self):
        self.kb = self._load_kb()

    # -----------------------------
    # Knowledge Base
    # -----------------------------
    def _load_kb(self):
        try:
            with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def _save_kb(self):
        try:
            with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.kb, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _cache_key(self, query: str) -> str:
        return query.strip().lower()

    # -----------------------------
    # Public API
    # -----------------------------
    def fetch_product_info(self, product_query: str) -> dict:
        product_query = (product_query or "").strip()

        if not product_query:
            return {
                "source_url": "",
                "price": 0,
                "currency": "",
                "price_ron": 0,
                "specs": [],
                "availability": "Unknown",
                "timestamp": time.time(),
                "error": "Empty product query"
            }

        key = self._cache_key(product_query)

        # cache hit
        if key in self.kb:
            return self.kb[key]

        # search
        urls = self._search_web(product_query)

        # scrape multiple URLs (until success)
        product_data = self._scrape_product_pages(urls)

        # save cache
        self.kb[key] = product_data
        self._save_kb()

        return product_data

    # -----------------------------
    # Search (SerpAPI)
    # -----------------------------
    def _search_web(self, query: str) -> list[str]:
        if not SERPAPI_KEY:
            raise RuntimeError("SERPAPI_KEY missing. Set env var SERPAPI_KEY before running.")

        domain_filter = " OR ".join([f"site:{d}" for d in TRUSTED_DOMAINS])

        # We restrict to trusted domains and include commerce terms
        q = f'{query} (price OR pret OR "in stoc" OR stock) ({domain_filter})'

        params = {
            "engine": "google",
            "q": q,
            "api_key": SERPAPI_KEY,

            # ✅ Localize to Romania (avoid weird regions)
            "hl": "ro",
            "gl": "ro",

            "num": 10
        }

        search = GoogleSearch(params)
        results = search.get_dict()

        links = []
        for r in results.get("organic_results", []):
            link = r.get("link")
            if link:
                links.append(link)

        if not links:
            raise RuntimeError("No product pages found on trusted domains.")

        return links[:MAX_URLS_TO_TRY]

    # -----------------------------
    # Scraping
    # -----------------------------
    def _scrape_product_pages(self, urls: list[str]) -> dict:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.7,en;q=0.6"
        }

        best_candidate = None

        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    continue

                soup = BeautifulSoup(r.text, "html.parser")

                page_text = soup.get_text(separator=" ", strip=True)

                # Extract price
                price_info = self._extract_price(soup, page_text)

                # Extract availability
                availability = self._extract_availability(soup, page_text)

                # Extract specs (generic keywords / TV + phone oriented)
                specs = self._extract_specs(page_text)

                candidate = {
                    "source_url": url,
                    "price": price_info.get("price", 0),
                    "currency": price_info.get("currency", ""),
                    "price_ron": price_info.get("price_ron", 0),
                    "specs": specs,
                    "availability": availability,
                    "timestamp": time.time()
                }

                # If we found a clear price + in stock -> return immediately
                if candidate["availability"] == "In stock" and candidate["price"] != 0:
                    return candidate

                # Otherwise remember best candidate (some sites don't show stock)
                if best_candidate is None:
                    best_candidate = candidate
                else:
                    best_candidate = self._better_candidate(best_candidate, candidate)

            except Exception:
                continue

        if best_candidate:
            return best_candidate

        return {
            "source_url": "",
            "price": 0,
            "currency": "",
            "price_ron": 0,
            "specs": [],
            "availability": "Unknown",
            "timestamp": time.time(),
            "error": "Failed to scrape product pages"
        }

    def _better_candidate(self, a: dict, b: dict) -> dict:
        """
        Pick better result:
        - prefer in stock
        - prefer having price
        """
        score_a = 0
        score_b = 0

        if a.get("availability") == "In stock":
            score_a += 2
        if b.get("availability") == "In stock":
            score_b += 2

        if a.get("price", 0) != 0:
            score_a += 2
        if b.get("price", 0) != 0:
            score_b += 2

        if len(a.get("specs", [])) >= 3:
            score_a += 1
        if len(b.get("specs", [])) >= 3:
            score_b += 1

        return b if score_b > score_a else a

    # -----------------------------
    # Price extraction
    # -----------------------------
    def _extract_price(self, soup: BeautifulSoup, text: str) -> dict:
        """
        Returns dict:
        {
          "price": float,
          "currency": "RON"/"EUR"/...,
          "price_ron": float
        }
        """

        # 1) JSON-LD (best)
        price = self._extract_price_from_jsonld(soup)
        if price:
            return price

        # 2) meta tags
        price = self._extract_price_from_meta(soup)
        if price:
            return price

        # 3) regex fallback
        price = self._extract_price_from_text(text)
        if price:
            return price

        return {"price": 0, "currency": "", "price_ron": 0}

    def _extract_price_from_jsonld(self, soup: BeautifulSoup):
        scripts = soup.find_all("script", type="application/ld+json")
        for tag in scripts:
            raw = tag.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)

                # can be list or dict
                if isinstance(data, list):
                    for obj in data:
                        result = self._price_from_ldjson_obj(obj)
                        if result:
                            return result
                else:
                    result = self._price_from_ldjson_obj(data)
                    if result:
                        return result

            except Exception:
                continue
        return None

    def _price_from_ldjson_obj(self, obj):
        """
        Tries to find:
        offers.price + offers.priceCurrency
        """
        if not isinstance(obj, dict):
            return None

        offers = obj.get("offers")
        if offers is None:
            return None

        # offers can be dict or list
        candidates = []
        if isinstance(offers, dict):
            candidates.append(offers)
        elif isinstance(offers, list):
            candidates.extend([o for o in offers if isinstance(o, dict)])

        for off in candidates:
            price_raw = off.get("price") or off.get("lowPrice") or off.get("highPrice")
            currency = off.get("priceCurrency", "")

            if price_raw is None:
                continue

            try:
                price_value = float(str(price_raw).replace(",", "."))
                currency = currency.upper() if currency else ""
                return self._normalize_price(price_value, currency)
            except Exception:
                continue

        return None

    def _extract_price_from_meta(self, soup: BeautifulSoup):
        # facebook / open graph
        meta_price = soup.find("meta", {"property": "product:price:amount"})
        meta_curr = soup.find("meta", {"property": "product:price:currency"})
        if meta_price and meta_price.get("content"):
            try:
                price_value = float(meta_price["content"].replace(",", "."))
                currency = (meta_curr.get("content") if meta_curr else "RON").upper()
                return self._normalize_price(price_value, currency)
            except Exception:
                pass

        # schema
        meta_price2 = soup.find("meta", {"itemprop": "price"})
        meta_curr2 = soup.find("meta", {"itemprop": "priceCurrency"})
        if meta_price2 and meta_price2.get("content"):
            try:
                price_value = float(meta_price2["content"].replace(",", "."))
                currency = (meta_curr2.get("content") if meta_curr2 else "RON").upper()
                return self._normalize_price(price_value, currency)
            except Exception:
                pass

        return None

    def _extract_price_from_text(self, text: str):
        t = text.replace("\xa0", " ").lower()

        # lei / ron (common in RO)
        m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*(lei|ron)", t)
        if m:
            return self._normalize_price(self._to_float(m.group(1)), "RON")

        # euro
        m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*(€|eur)", t)
        if m:
            return self._normalize_price(self._to_float(m.group(1)), "EUR")

        # dollars
        m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*(\$|usd)", t)
        if m:
            return self._normalize_price(self._to_float(m.group(1)), "USD")

        return None

    def _to_float(self, s: str) -> float:
        s = s.replace(" ", "")
        # "1.299,99" -> 1299.99
        if s.count(",") == 1 and s.count(".") >= 1:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".").replace(".", "")
        # last resort:
        try:
            return float(s)
        except Exception:
            # fallback simple parse
            digits = re.sub(r"[^\d.]", "", s)
            return float(digits) if digits else 0

    def _normalize_price(self, price_value: float, currency: str):
        currency = (currency or "").upper()

        price_ron = 0
        if currency in ("RON", "LEI", ""):
            currency = "RON"
            price_ron = price_value
        elif currency == "EUR":
            price_ron = price_value * EUR_TO_RON
        elif currency == "USD":
            # rough convert if you want
            price_ron = price_value * (EUR_TO_RON * 0.92)
        else:
            price_ron = 0

        return {
            "price": float(price_value),
            "currency": currency,
            "price_ron": float(price_ron)
        }

    # -----------------------------
    # Availability extraction
    # -----------------------------
    def _extract_availability(self, soup: BeautifulSoup, text: str) -> str:
        """
        Attempts to detect stock status.
        Works best for Romanian retailers.
        """
        lowered = text.lower()

        in_stock_patterns = [
            "in stoc", "pe stoc", "disponibil", "available", "in stock"
        ]
        out_stock_patterns = [
            "stoc epuizat", "indisponibil", "out of stock", "unavailable", "nu este in stoc"
        ]

        # Strong signals: out of stock first
        for p in out_stock_patterns:
            if p in lowered:
                return "Out of stock"

        for p in in_stock_patterns:
            if p in lowered:
                return "In stock"

        # Try schema.org availability in JSON-LD
        scripts = soup.find_all("script", type="application/ld+json")
        for tag in scripts:
            raw = tag.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)
                availability = self._availability_from_ldjson(data)
                if availability:
                    return availability
            except Exception:
                continue

        return "Unknown"

    def _availability_from_ldjson(self, data):
        """
        Search for offers.availability:
        - https://schema.org/InStock
        - https://schema.org/OutOfStock
        """
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            offers = obj.get("offers")
            offers_list = []
            if isinstance(offers, dict):
                offers_list = [offers]
            elif isinstance(offers, list):
                offers_list = [o for o in offers if isinstance(o, dict)]

            for off in offers_list:
                av = off.get("availability", "")
                if isinstance(av, str):
                    av_lower = av.lower()
                    if "instock" in av_lower:
                        return "In stock"
                    if "outofstock" in av_lower:
                        return "Out of stock"
        return None

    # -----------------------------
    # Specs extraction (generic)
    # -----------------------------
    def _extract_specs(self, text: str):
        """
        Extract generic specs for:
        - TVs
        - phones
        """
        lowered = text.lower()

        keywords = [
            # TV common
            "4k", "uhd", "8k", "hdr", "dolby vision", "dolby atmos",
            "oled", "qled", "qned", "led", "smart tv",
            "android tv", "google tv", "webos", "tizen",
            "120hz", "60hz", "hdmi", "hdmi 2.1",

            # sizes in cm/inch (best-effort)
            "120 cm", "121 cm", "122 cm", "48 inch", "49 inch", "50 inch", "55 inch",

            # phone common
            "iphone", "samsung galaxy", "256gb", "128gb", "512gb",
            "a16", "a17", "snapdragon", "5g", "oled", "usb-c"
        ]

        found = []
        for k in keywords:
            if k in lowered:
                found.append(k)

        # Keep unique, preserve order
        unique = []
        for f in found:
            if f not in unique:
                unique.append(f)

        return unique[:12]
