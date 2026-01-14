import json
from llm import call_llm
from email_tool import send_email
from invoice_pdf import generate_invoice_pdf


SYSTEM_PROMPT = """
You are the Shipping Department Agent.

ROLE:
Manage logistics and delivery negotiation.

YOU MUST:
1. Initially propose 5–7 day delivery
2. Ask customer for preference
3. If customer requests ≤3 days:
   - Counter with 4 days OR
   - Offer 2-day shipping with extra fee
4. Negotiate for MAX 2 turns
5. Lock the final shipping date
6. Update ORDER_STATE

AFTER LOCK:
- Generate PDF invoice
- Send confirmation email (with PDF attached)
- Clearly state order is finalized

OUTPUT STRICT JSON:

{
  "message": "",
  "shipping_days": 0,
  "expedited_fee": 0,
  "action": "continue" | "finalize"
}

If action == "finalize", output ONLY:
{ "finalized": true }
"""


class ShippingAgent:
    def _clean_json_text(self, text: str) -> str:
        """Removes markdown ```json blocks if present."""
        cleaned = (text or "").strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "")
            cleaned = cleaned.replace("```", "")
            cleaned = cleaned.strip()

        # sometimes model adds leading/trailing text
        # attempt to cut only JSON object
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            cleaned = cleaned[first:last + 1]

        return cleaned

    def safe_json_loads(self, text: str) -> dict:
        """Parse JSON safely. Fallback to continue."""
        try:
            cleaned = self._clean_json_text(text)
            return json.loads(cleaned)
        except Exception:
            return {
                "message": (text or "").strip(),
                "shipping_days": 0,
                "expedited_fee": 0,
                "action": "continue",
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

    def run(self, user_input: str, state: dict, conversation: list):
        """
        ✅ Signature matches main.py:
           run(user_input, state, conversation)
        """

        # ensure defaults
        state.setdefault("shipping_final_days", 0)
        state.setdefault("expedited_fee", 0)
        state.setdefault("finalized", False)

        # If already finalized, stop duplicating
        if state.get("finalized") is True:
            return "✅ Order already finalized. You will receive email + invoice."

        # LLM call
        messages = self.build_messages(conversation, state)
        raw = call_llm(messages)

        response = self.safe_json_loads(raw)

        # DEBUG (optional, keep while testing)
        print("[DEBUG SHIPPING] RAW:", raw)
        print("[DEBUG SHIPPING] PARSED:", response)

        # Update state
        if "shipping_days" in response and response["shipping_days"]:
            state["shipping_final_days"] = response["shipping_days"]

        if "expedited_fee" in response:
            state["expedited_fee"] = response["expedited_fee"]

        # ✅ FINALIZE condition (this is the important block)
        if response.get("finalized") is True or response.get("action") == "finalize":
            print("[DEBUG SHIPPING] Finalize condition met. Generating PDF + sending email...")

            # mark finalized (prevents sending twice)
            state["finalized"] = True

            # ✅ generate pdf first
            pdf_path = generate_invoice_pdf(state)

            # ✅ send email with attachment
            send_email(state, pdf_path)

            return "✅ Order finalized. Confirmation email sent and PDF invoice generated."

        return response.get("message", "Standard delivery is 5–7 days. Do you have a preference?")
