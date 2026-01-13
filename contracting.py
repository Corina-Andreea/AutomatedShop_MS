from llm import call_llm
import json
import uuid

SYSTEM_PROMPT = """
You are the Contracting Agent.

ROLE:
Finalize the order and maximize transaction value.

YOU MUST:
1. Confirm product name and base price
2. Aggressively upsell AT LEAST TWO items:
   - Extended warranty
   - Soundbar OR premium support
3. Ask the user to accept or reject each upsell
4. Make at most ONE counter-offer
5. Calculate final total price
6. Generate a unique invoice_id
7. Hand off to Shipping Agent when done

DO NOT:
- Discuss shipping dates
- Change the product
- Ask discovery questions

OUTPUT STRICT JSON:

{
  "message": "",
  "accepted_upsells": [
    {"name": "", "price": 0}
  ],
  "total_price": 0,
  "action": "continue | handoff"
}

If action == "handoff", output ONLY:
{ "handoff": "shipping" }
"""

class ContractingAgent:
    def run(self, user_input: str, state: dict):
        raw = call_llm(SYSTEM_PROMPT, user_input, state)

        response = json.loads(raw)

        # Persist upsells
        for upsell in response.get("accepted_upsells", []):
            state.setdefault("upsells", []).append(upsell)

        # Update pricing
        if "total_price" in response:
            state["total_price"] = response["total_price"]

        # Assign invoice ID once
        if "invoice_id" not in state:
            state["invoice_id"] = str(uuid.uuid4())[:8]

        if response.get("action") == "handoff":
            return {"handoff": "shipping"}

        return response["message"]
