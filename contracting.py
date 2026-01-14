import json
import uuid
from llm import call_llm

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
  "action": "continue" | "handoff"
}

If action == "handoff", output ONLY:
{ "handoff": "shipping" }
"""


class ContractingAgent:
    def safe_json_loads(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            # fallback
            return {
                "message": text.strip(),
                "accepted_upsells": [],
                "total_price": 0,
                "action": "continue"
            }

    def build_messages(self, conversation: list, user_input: str, state: dict) -> list:
        """
        call_llm expects a messages list.
        We include:
         - system prompt
         - conversation history from main.py
         - latest user input (already in conversation usually, but ok)
         - state snapshot
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if conversation:
            messages.extend(conversation)

        # add state snapshot for correctness
        messages.append({
            "role": "user",
            "content": "STATE:\n" + json.dumps(state, indent=2)
        })

        return messages

    def run(self, user_input: str, state: dict, conversation: list):
        """
        ✅ IMPORTANT: signature matches main.py usage:
           run(user_input, state, conversation)
        """
        # assign invoice id once
        if "invoice_id" not in state:
            state["invoice_id"] = str(uuid.uuid4())[:8]

        # LLM call
        messages = self.build_messages(conversation, user_input, state)
        raw = call_llm(messages)
        response = self.safe_json_loads(raw)

        # If model decides handoff
        if response.get("handoff") == "shipping" or response.get("action") == "handoff":
            return {"handoff": "shipping"}

        # Persist upsells
        for upsell in response.get("accepted_upsells", []):
            state.setdefault("upsells", []).append(upsell)

        # Update pricing
        if "total_price" in response:
            state["total_price"] = response["total_price"]

        return response.get("message", "Do you accept the additional offers?")
