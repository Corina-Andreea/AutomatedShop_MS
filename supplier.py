import requests
from bs4 import BeautifulSoup
import json
import time
import serpapi

SERPAPI_KEY = "769f5198e747a3bab0c1885b77b2e97f51cce0415b35496e7574a9ad300740f6"
KNOWLEDGE_BASE_FILE = "knowledge_base.json"

class SupplierAgent:
    def __init__(self):
        self.kb = self._load_kb()

    # --------------------
    # Knowledge Base
    # --------------------
    def _load_kb(self):
        try:
            with open(KNOWLEDGE_BASE_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save_kb(self):
        with open(KNOWLEDGE_BASE_FILE, "w") as f:
            json.dump(self.kb, f, indent=2)

    # --------------------
    # Public API
    # --------------------
    def fetch_product_info(self, product_query: str):
        # 1️⃣ Check knowledge base first
        if product_query in self.kb:
            return self.kb[product_query]

        # 2️⃣ Perform real-time web search
        search_results = self._search_web(product_query)

        # 3️⃣ Scrape first valid product page
        product_data = self._scrape_product_page(search_results)

        # 4️⃣ Store in knowledge base
        self.kb[product_query] = product_data
        self._save_kb()

        return product_data

    # --------------------
    # Web Search
    # --------------------
    def _search_web(self, query: str):
        params = {
            "q": query + " official product specifications price",
            "engine": "google",
            "api_key": SERPAPI_KEY,
            "num": 5
        }

        search = serpapi.search(params)
        results = search.as_dict()

        links = []
        for r in results.get("organic_results", []):
            links.append(r.get("link"))

        if not links:
            raise RuntimeError("No product pages found")

        return links

    # --------------------
    # Web Scraping
    # --------------------
    def _scrape_product_page(self, urls):
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(response.text, "html.parser")

                text = soup.get_text(separator=" ", strip=True)

                # VERY SIMPLE extraction (good enough for project)
                return {
                    "source_url": url,
                    "price": self._extract_price(text),
                    "specs": self._extract_specs(text),
                    "availability": "Unknown",
                    "timestamp": time.time()
                }
            except Exception:
                continue

        raise RuntimeError("Failed to scrape product page")

    # --------------------
    # Helpers
    # --------------------
    def _extract_price(self, text):
        for token in text.split():
            if token.startswith("€") or token.startswith("$"):
                return float(token[1:].replace(",", ""))
        return 0

    def _extract_specs(self, text):
        keywords = ["4K", "HDR", "OLED", "QLED", "65", "Smart TV"]
        return [k for k in keywords if k in text]
