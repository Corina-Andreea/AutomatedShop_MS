import json
from supplier import SupplierAgent
from llm import call_llm


SYSTEM_PROMPT = """
You are the Salesperson Agent in an Automated Shop multi-agent system.

You must decide the next action using structured JSON.

Rules:
- Identify product + requirements.
- If price/specs/availability are needed -> set "needs_supplier": true and provide "product_query".
- If the user rejects the recommended product, set:
  "action": "reject"
  and "needs_supplier": true (to fetch another option)
- If user confirms purchase, set:
  "action": "handoff"

Return output STRICTLY as JSON only:
{
  "message": "...",
  "action": "ask" | "recommend" | "handoff" | "reject" | "none",
  "product": "...",
  "customer_need": "...",
  "needs_supplier": true | false,
  "product_query": "..."
}
"""


class SalespersonAgent:
    def __init__(self):
        self.supplier = SupplierAgent()

    # -------------------------
    # Helpers
    # -------------------------
    def _clean_json_text(self, text: str) -> str:
        cleaned = (text or "").strip()

        # remove markdown code fences
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "")
            cleaned = cleaned.replace("```", "")
            cleaned = cleaned.strip()

        # keep only JSON object
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            cleaned = cleaned[first:last + 1]

        return cleaned

    def safe_json_loads(self, text: str) -> dict:
        try:
            cleaned = self._clean_json_text(text)
            return json.loads(cleaned)
        except Exception:
            return {
                "message": (text or "").strip(),
                "action": "ask",
                "product": "",
                "customer_need": "",
                "needs_supplier": False,
                "product_query": ""
            }

    def ensure_state(self, state: dict):
        state.setdefault("phase", "discovery")
        state.setdefault("product", "")
        state.setdefault("customer_need", "")
        state.setdefault("supplier_data", None)
        state.setdefault("base_price", 0)

        # keep rejected urls/products for retry
        state.setdefault("rejected_products", [])     # list of urls
        state.setdefault("last_product_query", "")

    def build_messages(self, conversation: list, state: dict) -> list:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation:
            messages.extend(conversation)

        messages.append({
            "role": "user",
            "content": "STATE:\n" + json.dumps(state, indent=2)
        })
        return messages

    def format_supplier_answer(self, state: dict) -> str:
        """
        Supplier returns ONE product dict:
        {
            source_url, price, price_ron, availability, specs
        }
        """
        data = state.get("supplier_data") or {}

        url = data.get("source_url", "")
        availability = data.get("availability", "Unknown")

        # prefer RON price if present
        price = data.get("price_ron") or data.get("price", 0)

        specs = data.get("specs", [])

        # If supplier returned nothing usable
        if not url:
            return (
                "I couldn't find a clear product page for your requirements.\n"
                "Could you specify a budget or allow alternative brands/specs?"
            )

        lines = []
        lines.append(f"✅ **Product found**")
        if state.get("customer_need"):
            lines.append(f"🎯 Requirements: {state.get('customer_need')}")

        lines.append(f"📦 Availability: {availability}")

        if price and price != 0:
            lines.append(f"💰 Price: {price}")
        else:
            # don't show useless message - instead ask for budget
            lines.append("💰 Price: Not displayed clearly on the product page.")
            lines.append("👉 If you want, tell me your budget and I can search alternative stores/models.")

        if specs:
            lines.append("📌 Specs: " + ", ".join(specs[:10]))

        lines.append(f"🔗 Link: {url}")
        lines.append("\nWould you like to purchase it? ✅ (yes / no)")

        return "\n".join(lines)


    def run(self, user_input: str, state: dict, conversation: list):
        self.ensure_state(state)

        # Ask LLM for decision/action
        raw = call_llm(self.build_messages(conversation, state))
        response = self.safe_json_loads(raw)

        # Update state with extracted info
        if response.get("product"):
            state["product"] = response["product"]

        if response.get("customer_need"):
            state["customer_need"] = response["customer_need"]

        # Handoff to contracting
        if response.get("action") == "handoff":
            state["phase"] = "contracting"
            return {"handoff": "contracting"}

        # If reject -> exclude current product and search again
        if response.get("action") == "reject":
            current_url = (state.get("supplier_data") or {}).get("source_url", "")
            if current_url:
                state["rejected_products"].append(current_url)

            # reset supplier data
            state["supplier_data"] = None

            # force new supplier lookup
            response["needs_supplier"] = True

        # Supplier tool call
        if response.get("needs_supplier") is True:
            state["phase"] = "supplier_lookup"

            product_query = (
                response.get("product_query")
                or state.get("last_product_query")
                or state.get("product")
                or user_input
            )

            state["last_product_query"] = product_query

            # supplier call with excluded_urls support
            supplier_data = self.supplier.fetch_product_info(
                product_query,
                excluded_urls=state.get("rejected_products", [])
            )

            state["supplier_data"] = supplier_data

            # set base price properly
            state["base_price"] = supplier_data.get("price_ron") or supplier_data.get("price", 0)

            state["phase"] = "recommendation"

            return self.format_supplier_answer(state)

        # Normal response (clarifying question etc.)
        return response.get("message", "Can you tell me more about what you want to buy?")
