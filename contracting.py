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
            cleaned = (text or "").strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()
            first = cleaned.find("{")
            last = cleaned.rfind("}")
            if first != -1 and last != -1 and last > first:
                cleaned = cleaned[first:last + 1]
            return json.loads(cleaned)
        except Exception:
            return {
                "message": (text or "").strip(),
                "accepted_upsells": [],
                "total_price": 0,
                "action": "continue"
            }

    def build_messages(self, conversation: list, state: dict) -> list:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if conversation:
            messages.extend(conversation)

        messages.append({
            "role": "user",
            "content": "STATE:\n" + json.dumps(state, indent=2)
        })

        return messages

    def compute_total(self, state: dict) -> float:
        base_price = float(state.get("base_price", 0) or 0)
        upsells = state.get("upsells", []) or []
        upsells_total = 0.0

        for u in upsells:
            try:
                upsells_total += float(u.get("price", 0) or 0)
            except Exception:
                pass

        return base_price + upsells_total

    def run(self, user_input: str, state: dict, conversation: list):
        # defaults
        state.setdefault("upsells", [])
        state.setdefault("base_price", 0)
        state.setdefault("total_price", 0)

        # assign invoice id once
        if not state.get("invoice_id"):
            state["invoice_id"] = str(uuid.uuid4())[:8]

        # LLM call
        messages = self.build_messages(conversation, state)
        raw = call_llm(messages)
        response = self.safe_json_loads(raw)

        # If model decides handoff
        if response.get("handoff") == "shipping" or response.get("action") == "handoff":
            # ✅ compute final total before handoff
            state["total_price"] = self.compute_total(state)
            return {"handoff": "shipping"}

        # Persist upsells (only if provided)
        for upsell in response.get("accepted_upsells", []):
            # normalize data
            name = upsell.get("name", "")
            price = upsell.get("price", 0)
            if name:
                state["upsells"].append({"name": name, "price": price})

        # ✅ ALWAYS recompute total in code (even if no upsells)
        state["total_price"] = self.compute_total(state)

        return response.get("message", "Do you accept the additional offers?")
