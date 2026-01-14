import json
from supplier import SupplierAgent
from llm import call_llm


SYSTEM_PROMPT = """
You are the Salesperson Agent in an Automated Shop multi-agent system.

You must decide what to do next using structured JSON.

Rules:
- If product details (price/specs/availability) are needed and missing, you MUST request supplier lookup by setting:
  "needs_supplier": true
  and provide a "product_query".

- Do NOT waste turns saying "I will check" or "please wait".
  If a supplier lookup is needed, request it immediately.
  The system will perform the lookup and then you will respond with concrete results.

Return output STRICTLY as JSON only:
{
  "message": "...",
  "action": "ask" | "recommend" | "handoff" | "none",
  "product": "...",
  "customer_need": "...",
  "needs_supplier": true | false,
  "product_query": "..."
}
"""


class SalespersonAgent:
    def __init__(self):
        self.supplier = SupplierAgent()

    def safe_json_loads(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            return {
                "message": text.strip(),
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
        data = state.get("supplier_data") or {}
        url = data.get("source_url", "")
        price = data.get("price", 0)
        availability = data.get("availability", "Unknown")
        specs = data.get("specs", [])

        lines = []
        lines.append(f"✅ Product: {state.get('product', 'Unknown')}")
        if state.get("customer_need"):
            lines.append(f"🎯 Requirements: {state.get('customer_need')}")

        lines.append(f"📦 Availability: {availability}")

        if price and price != 0:
            lines.append(f"💰 Price: {price}")
        else:
            lines.append("💰 Price: Not found exactly (no clear price on scraped page).")

        if specs:
            lines.append("📌 Key specs found: " + ", ".join(specs[:8]))
        else:
            lines.append("📌 Specs: Not enough specs extracted from the supplier page.")

        if url:
            lines.append(f"🔗 Source: {url}")

        lines.append("\nWould you like to purchase it? ✅")
        return "\n".join(lines)

    def run(self, user_input: str, state: dict, conversation: list):
        self.ensure_state(state)

        # 1) Ask LLM what the next action is (AI decision)
        raw = call_llm(self.build_messages(conversation, state))
        response = self.safe_json_loads(raw)

        # 2) Update state
        if response.get("product"):
            state["product"] = response["product"]

        if response.get("customer_need"):
            state["customer_need"] = response["customer_need"]

        # 3) Handoff to contracting if needed
        if response.get("action") == "handoff":
            state["phase"] = "contracting"
            return {"handoff": "contracting"}

        # 4) ✅ Supplier tool-call (AI-driven)
        if response.get("needs_supplier") is True:
            state["phase"] = "supplier_lookup"

            product_query = (
                response.get("product_query")
                or state.get("product")
                or user_input
            )

            # REAL supplier call
            supplier_data = self.supplier.fetch_product_info(product_query)

            state["supplier_data"] = supplier_data
            state["base_price"] = supplier_data.get("price", 0)
            state["phase"] = "recommendation"

            # IMPORTANT: return DIRECT details (no extra LLM turn)
            return self.format_supplier_answer(state)

        # 5) normal message (ask clarifying questions etc.)
        return response.get("message", "Can you tell me more about what you need?")
