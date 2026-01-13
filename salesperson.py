from llm import call_llm
from supplier import SupplierAgent
import json

SYSTEM_PROMPT = """
You are the Salesperson Agent in an automated shop.

ROLE:
- Initial customer interaction
- Product recommendation
- Sales closing

YOU MUST:
1. Greet the customer only once
2. Ask open-ended questions to understand needs
3. Decide when requirements are sufficient
4. If product details (price/specs/availability) are missing:
   → request Supplier Agent data
5. Present ONE concrete product recommendation
6. When the product category and key features are known,STOP asking questions and allow Python to trigger the Supplier Agent.
7. Attempt to sell
8. When the user confirms purchase:
   → STOP and hand off to Contracting Agent

IMPORTANT RULES:
- Do NOT loop or re-ask known information
- Do NOT invent specs or prices
- Do NOT finalize contracts
- Do NOT upsell (that is Contracting's job)

OUTPUT FORMAT (MANDATORY JSON):

{
  "message": "<text to show user>",
  "needs_supplier": true | false,
  "product_query": "<product name or empty>",
  "state_updates": { ... },
  "action": "continue | handoff"
}

If action == "handoff", output ONLY:
{
  "handoff": "contracting"
}
"""


class SalespersonAgent:
    def __init__(self):
        self.supplier = SupplierAgent()

    def has_enough_info(self, state: dict):
        return (
                state.get("product", "") != ""
                and state.get("customer_need", "") != ""
        )

    def extract_product_category(self, user_input: str):
        keywords = {
            "gaming mouse": ["mouse"],
            "keyboard": ["keyboard"],
            "monitor": ["monitor"],
            "headphones": ["headphones"],
            "smart tv": ["tv", "television"]
        }

        text = user_input.lower()
        for product, keys in keywords.items():
            if any(k in text for k in keys):
                return product

        return ""
    def run(self, user_input: str, state: dict):
        # 1️⃣ Deterministically extract product category
        if not state.get("product"):
            detected = self.extract_product_category(user_input)
            if detected:
                state["product"] = detected

        # 2️⃣ Call LLM to interpret preferences
        raw = call_llm(SYSTEM_PROMPT, user_input, state)
        response = json.loads(raw)

        # 3️⃣ Apply LLM state updates (preferences, phase hints)
        for k, v in response.get("state_updates", {}).items():
            state[k] = v

        # 4️⃣ 🔴 HARD STOP: trigger supplier as soon as info is sufficient
        if state["phase"] == "discovery" and self.has_enough_info(state):
            state["phase"] = "supplier_lookup"

            product_query = f"{state['product']} {state['customer_need']}"
            supplier_data = self.supplier.fetch_product_info(product_query)

            state["supplier_data"] = supplier_data
            state["base_price"] = supplier_data.get("price", 0)
            state["phase"] = "recommendation"

            followup = call_llm(
                SYSTEM_PROMPT,
                "Present ONE concrete product recommendation using supplier data and ask for purchase confirmation.",
                state
            )

            followup_json = json.loads(followup)
            return followup_json["message"]

        # 5️⃣ Handoff
        if response.get("action") == "handoff":
            state["phase"] = "contracting"
            return {"handoff": "contracting"}

        return response["message"]
