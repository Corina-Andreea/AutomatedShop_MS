import os
import json
import time
import re
import random
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from serpapi import GoogleSearch


# -----------------------------
# CONFIG
# -----------------------------
KNOWLEDGE_BASE_FILE = "knowledge_base.json"
SERPAPI_KEY = "769f5198e747a3bab0c1885b77b2e97f51cce0415b35496e7574a9ad300740f6"

DEBUG = True

SERP_NUM_RESULTS = 20
MAX_URLS_TO_TRY = 30

REQUEST_TIMEOUT = 25  # ✅ bigger timeout
MAX_RETRIES = 3       # ✅ retries per URL

EUR_TO_RON = 5.0

# Pass 1: RO
TRUSTED_DOMAINS_RO = [
    "pcgarage.ro",
    "evomag.ro",
    "emag.ro",
    "cel.ro",
    "flanco.ro",
    "mediagalaxy.ro",
    #"altex.ro",
]

# Pass 2: fallback EU/comparators
TRUSTED_DOMAINS_FALLBACK = [
    "compari.ro",
    "price.ro",
    "idealo.de",
    "amazon.de",
    "amazon.it",
    "amazon.fr",
    "amazon.es",
]


class SupplierAgent:
    """
    SupplierAgent V5:
    ✅ requests.Session (stable)
    ✅ retry + backoff
    ✅ per-domain URL limiting
    ✅ domain penalty if too many timeouts
    ✅ short randomized delay between requests
    ✅ robust price extraction (json-ld/meta/regex)
    ✅ excluded_urls support
    ✅ caching
    """

    def __init__(self):
        self.kb = self._load_kb()
        self.session = requests.Session()
        self.domain_failures = {}  # domain -> failure_count

    # -----------------------------
    # KB
    # -----------------------------
    def _load_kb(self):
        try:
            with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_kb(self):
        try:
            with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.kb, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _cache_key(self, q: str) -> str:
        return (q or "").strip().lower()

    # -----------------------------
    # Public API
    # -----------------------------
    def fetch_product_info(self, product_query: str, excluded_urls=None) -> dict:
        product_query = (product_query or "").strip()
        excluded_urls = excluded_urls or []
        excluded_urls = set(excluded_urls)

        if not product_query:
            return {
                "source_url": "",
                "price": 0,
                "currency": "",
                "price_ron": 0,
                "availability": "Unknown",
                "specs": [],
                "timestamp": time.time(),
                "error": "Empty query"
            }

        key = self._cache_key(product_query)

        # cache only if no exclusions
        if key in self.kb and not excluded_urls:
            if DEBUG:
                print("[SUPPLIER] cache hit")
            return self.kb[key]

        urls = []
        # 2-pass search
        try:
            urls += self._search_web(product_query, TRUSTED_DOMAINS_RO, hl="ro", gl="ro")
        except Exception as e:
            if DEBUG:
                print("[SUPPLIER] RO search failed:", e)

        try:
            urls += self._search_web(product_query, TRUSTED_DOMAINS_FALLBACK, hl="en", gl="de")
        except Exception as e:
            if DEBUG:
                print("[SUPPLIER] Fallback search failed:", e)

        # deduplicate and exclude
        seen = set()
        unique_urls = []
        for u in urls:
            if u not in seen and u not in excluded_urls:
                unique_urls.append(u)
                seen.add(u)

        # ✅ limit per domain
        unique_urls = self._limit_per_domain(unique_urls, max_per_domain=3)

        # prefer product pages first
        unique_urls = self._prioritize_urls(unique_urls)
        unique_urls = unique_urls[:MAX_URLS_TO_TRY]

        if DEBUG:
            print("\n[SUPPLIER] URLs to try:")
            for u in unique_urls:
                print(" -", u)

        best = self._scrape_best_product(unique_urls, product_query)

        # cache only if no exclusions
        if not excluded_urls:
            self.kb[key] = best
            self._save_kb()

        return best

    # -----------------------------
    # Search
    # -----------------------------
    def _search_web(self, query: str, domains: list[str], hl="ro", gl="ro") -> list[str]:
        if not SERPAPI_KEY:
            raise RuntimeError("SERPAPI_KEY missing. Set env var SERPAPI_KEY before running.")

        domain_filter = " OR ".join([f"site:{d}" for d in domains])

        q = (
            f'"{query}" (pret OR price OR "in stoc" OR stock OR buy OR "add to cart") '
            f'({domain_filter})'
        )

        params = {
            "engine": "google",
            "q": q,
            "api_key": SERPAPI_KEY,
            "hl": hl,
            "gl": gl,
            "num": SERP_NUM_RESULTS,
        }

        results = GoogleSearch(params).get_dict()
        links = []

        for r in results.get("organic_results", []):
            link = r.get("link")
            if link:
                links.append(link)

        return links

    # -----------------------------
    # URL helpers
    # -----------------------------
    def _prioritize_urls(self, urls: list[str]) -> list[str]:
        def score(url: str) -> int:
            u = (url or "").lower()
            s = 0

            good = ["/produs/", "/product/", ".html", "/dp/", "/pd/", "/p/"]
            bad = ["search", "cauta", "categorie", "category", "catalog", "/brand", "/brands"]

            if any(g in u for g in good):
                s += 6
            if any(b in u for b in bad):
                s -= 5

            # comparator sites still useful
            if "compari" in u or "price.ro" in u or "idealo" in u:
                s += 2

            # penalize domains that recently failed a lot
            domain = urlparse(u).netloc
            failures = self.domain_failures.get(domain, 0)
            s -= failures * 2

            return s

        return sorted(urls, key=score, reverse=True)

    def _limit_per_domain(self, urls: list[str], max_per_domain: int = 3) -> list[str]:
        counts = {}
        result = []
        for u in urls:
            dom = urlparse(u).netloc
            counts.setdefault(dom, 0)
            if counts[dom] < max_per_domain:
                result.append(u)
                counts[dom] += 1
        return result

    # -----------------------------
    # Fetch with retry/backoff
    # -----------------------------
    def _fetch_html(self, url: str) -> str | None:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.7,en;q=0.6",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        domain = urlparse(url).netloc

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # ✅ random sleep to avoid rate limits
                time.sleep(random.uniform(0.3, 0.9))

                resp = self.session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200 and resp.text:
                    # reset failures on success
                    self.domain_failures[domain] = max(self.domain_failures.get(domain, 0) - 1, 0)
                    return resp.text

                # penalize non-200
                self.domain_failures[domain] = self.domain_failures.get(domain, 0) + 1

            except Exception as e:
                # penalize domain
                self.domain_failures[domain] = self.domain_failures.get(domain, 0) + 1

                if DEBUG:
                    print(f"[SUPPLIER] fetch retry {attempt}/{MAX_RETRIES} failed for {url}: {e}")

                # backoff
                time.sleep(1.0 + attempt)

        return None

    # -----------------------------
    # Scraping
    # -----------------------------
    def _scrape_best_product(self, urls: list[str], query: str) -> dict:
        best = None
        best_score = -1

        for idx, url in enumerate(urls):
            domain = urlparse(url).netloc

            # skip domains with too many failures
            if self.domain_failures.get(domain, 0) >= 6:
                if DEBUG:
                    print(f"[SUPPLIER] Skip domain (too many failures): {domain}")
                continue

            html = self._fetch_html(url)
            if not html:
                if DEBUG:
                    print(f"[SUPPLIER] error scraping url: {url} error: timed out / blocked")
                continue

            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)

            price_info, price_quality = self._extract_price_best(soup, text)
            availability = self._extract_availability(soup, text)
            specs = self._extract_specs(text, query=query)

            candidate = {
                "source_url": url,
                "price": price_info.get("price", 0),
                "currency": price_info.get("currency", ""),
                "price_ron": price_info.get("price_ron", 0),
                "availability": availability,
                "specs": specs,
                "timestamp": time.time(),
            }

            score = self._score_candidate(candidate, price_quality)

            if DEBUG:
                print(f"[SUPPLIER] Try {idx+1}/{len(urls)} score={score} url={url}")
                print("           availability:", availability)
                print("           price:", candidate["price"], candidate["currency"], "| price_ron:", candidate["price_ron"])
                print("           price_quality:", price_quality)

            if score > best_score:
                best_score = score
                best = candidate

            # Early stop: best-quality price
            if self._is_strong(candidate, price_quality):
                if DEBUG:
                    print("[SUPPLIER] Strong candidate found -> stop")
                return candidate

        if best:
            return best

        return {
            "source_url": "",
            "price": 0,
            "currency": "",
            "price_ron": 0,
            "availability": "Unknown",
            "specs": [],
            "timestamp": time.time(),
            "error": "No usable product page found (blocked/timeouts)."
        }

    def _score_candidate(self, candidate: dict, price_quality: int) -> float:
        score = 0.0

        av = candidate.get("availability", "Unknown")
        has_price = (candidate.get("price_ron") or candidate.get("price")) not in (0, None)

        if av == "In stock":
            score += 6
        elif av == "Unknown":
            score += 2

        if has_price:
            score += 8

        score += price_quality * 4
        score += min(len(candidate.get("specs", [])), 10) * 0.25

        if candidate.get("currency") == "RON":
            score += 2

        return score

    def _is_strong(self, candidate: dict, price_quality: int) -> bool:
        has_price = (candidate.get("price_ron") or candidate.get("price")) not in (0, None)
        return has_price and price_quality >= 2

    # -----------------------------
    # Price extraction
    # -----------------------------
    def _extract_price_best(self, soup: BeautifulSoup, text: str):
        p = self._extract_price_from_jsonld(soup)
        if p:
            return p, 3

        p = self._extract_price_from_meta(soup)
        if p:
            return p, 2

        p = self._extract_price_from_text(text)
        if p:
            return p, 1

        return {"price": 0, "currency": "", "price_ron": 0}, 0

    def _extract_price_from_jsonld(self, soup: BeautifulSoup):
        scripts = soup.find_all("script", type="application/ld+json")
        for tag in scripts:
            raw = tag.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)
                objs = data if isinstance(data, list) else [data]
                for obj in objs:
                    res = self._price_from_ldjson_obj(obj)
                    if res:
                        return res
            except Exception:
                continue
        return None

    def _price_from_ldjson_obj(self, obj):
        if not isinstance(obj, dict):
            return None

        offers = obj.get("offers")
        if offers is None:
            return None

        offers_list = []
        if isinstance(offers, dict):
            offers_list = [offers]
        elif isinstance(offers, list):
            offers_list = [o for o in offers if isinstance(o, dict)]

        for off in offers_list:
            price_raw = off.get("price") or off.get("lowPrice") or off.get("highPrice")
            currency = off.get("priceCurrency", "")

            if price_raw is None:
                continue

            try:
                price_value = float(str(price_raw).replace(",", "."))
                return self._normalize_price(price_value, currency)
            except Exception:
                continue

        return None

    def _extract_price_from_meta(self, soup: BeautifulSoup):
        meta_price = soup.find("meta", {"property": "product:price:amount"})
        meta_curr = soup.find("meta", {"property": "product:price:currency"})

        if meta_price and meta_price.get("content"):
            try:
                price_value = float(meta_price["content"].replace(",", "."))
                currency = (meta_curr.get("content") if meta_curr else "RON")
                return self._normalize_price(price_value, currency)
            except Exception:
                pass

        meta_price2 = soup.find("meta", {"itemprop": "price"})
        meta_curr2 = soup.find("meta", {"itemprop": "priceCurrency"})

        if meta_price2 and meta_price2.get("content"):
            try:
                price_value = float(meta_price2["content"].replace(",", "."))
                currency = (meta_curr2.get("content") if meta_curr2 else "RON")
                return self._normalize_price(price_value, currency)
            except Exception:
                pass

        return None

    def _extract_price_from_text(self, text: str):
        t = (text or "").replace("\xa0", " ").lower()

        if ("lei" not in t) and ("ron" not in t) and ("€" not in t) and ("eur" not in t):
            return None

        m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*(lei|ron)", t)
        if m:
            return self._normalize_price(self._to_float(m.group(1)), "RON")

        m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*(€|eur)", t)
        if m:
            return self._normalize_price(self._to_float(m.group(1)), "EUR")

        return None

    def _to_float(self, s: str) -> float:
        s = (s or "").strip().replace("\xa0", " ")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(" ", "").replace(",", ".")

        try:
            return float(s)
        except Exception:
            digits = re.sub(r"[^\d.]", "", s)
            return float(digits) if digits else 0.0

    def _normalize_price(self, price_value: float, currency: str):
        currency = (currency or "").upper()
        price_ron = 0.0

        if currency in ("RON", "LEI", ""):
            currency = "RON"
            price_ron = price_value
        elif currency == "EUR":
            price_ron = price_value * EUR_TO_RON

        return {
            "price": float(price_value),
            "currency": currency,
            "price_ron": float(price_ron)
        }

    # -----------------------------
    # Availability
    # -----------------------------
    def _extract_availability(self, soup: BeautifulSoup, text: str) -> str:
        lowered = (text or "").lower()
        out_stock = [
            "stoc epuizat", "indisponibil", "out of stock", "unavailable", "nu este in stoc"
        ]
        in_stock = [
            "in stoc", "pe stoc", "disponibil", "available", "in stock"
        ]

        for p in out_stock:
            if p in lowered:
                return "Out of stock"
        for p in in_stock:
            if p in lowered:
                return "In stock"
        return "Unknown"

    # -----------------------------
    # Specs
    # -----------------------------
    def _extract_specs(self, text: str, query: str = "") -> list:
        q = (query or "").lower()
        lowered = (text or "").lower()

        laptop_keywords = [
            "16gb", "ram", "ddr4", "ddr5", "ssd", "512gb", "1tb",
            "intel", "core i5", "core i7", "core i9", "i5", "i7", "i9",
            "ryzen", "windows 11", "ips", "144hz", "165hz", "rtx", "gtx"
        ]

        tv_keywords = ["4k", "uhd", "hdr", "oled", "qled", "smart tv", "120hz", "60hz", "hdmi"]
        phone_keywords = ["5g", "128gb", "256gb", "512gb", "usb-c", "oled", "amoled"]

        if "laptop" in q or "asus" in q or "notebook" in q:
            keywords = laptop_keywords
        elif "tv" in q:
            keywords = tv_keywords
        else:
            keywords = phone_keywords

        found = []
        for k in keywords:
            if k in lowered:
                found.append(k)

        unique = []
        for f in found:
            if f not in unique:
                unique.append(f)

        return unique[:10]
