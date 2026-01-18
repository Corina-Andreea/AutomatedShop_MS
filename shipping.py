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
   - Offer 2-day expedited shipping with extra fee
4. Negotiate for MAX 2 turns
5. Lock the final shipping date

AFTER LOCK:
- Output JSON finalize signal

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
    # -----------------------------
    # JSON parsing helpers
    # -----------------------------
    def _clean_json_text(self, text: str) -> str:
        cleaned = (text or "").strip()

        # remove markdown code fences
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "")
            cleaned = cleaned.replace("```", "")
            cleaned = cleaned.strip()

        # cut only json object if extra text exists
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
                "shipping_days": 0,
                "expedited_fee": 0,
                "action": "continue"
            }

    # -----------------------------
    # LLM messages
    # -----------------------------
    def build_messages(self, conversation: list, state: dict) -> list:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation:
            messages.extend(conversation)

        messages.append({
            "role": "user",
            "content": "STATE:\n" + json.dumps(state, indent=2)
        })
        return messages

    # -----------------------------
    # Pricing
    # -----------------------------
    def compute_final_total(self, state: dict) -> float:
        total_price = float(state.get("total_price", 0) or 0)   # base + upsells
        expedited_fee = float(state.get("expedited_fee", 0) or 0)
        return total_price + expedited_fee

    # -----------------------------
    # Main
    # -----------------------------
    def run(self, user_input: str, state: dict, conversation: list):

        # defaults
        state.setdefault("shipping_final_days", 0)
        state.setdefault("expedited_fee", 0)
        state.setdefault("final_total_price", 0)
        state.setdefault("finalized", False)

        # If already finalized, do not repeat
        if state.get("finalized") is True:
            return "✅ Order already finalized. You should receive confirmation email + invoice."

        # LLM call
        raw = call_llm(self.build_messages(conversation, state))
        response = self.safe_json_loads(raw)

        # DEBUG (keep for testing)
        #print("[DEBUG SHIPPING] RAW:", raw)
        #print("[DEBUG SHIPPING] PARSED:", response)

        # Update shipping info
        if "shipping_days" in response and response["shipping_days"]:
            state["shipping_final_days"] = response["shipping_days"]

        if "expedited_fee" in response:
            state["expedited_fee"] = response["expedited_fee"]

        # Always compute final total continuously
        state["final_total_price"] = self.compute_final_total(state)

        # Finalize condition
        if response.get("finalized") is True or response.get("action") == "finalize":
            print("Generating PDF + sending email...")

            state["finalized"] = True
                    
            # set state to complete after pdf+email
            state["order_locked"] = True
            state["phase"] = "complete"

            state["final_total_price"] = self.compute_final_total(state)

            # Ensure invoice_id exists (avoid invoice_.pdf)
            if not state.get("invoice_id"):
                state["invoice_id"] = "INV001"

            # Generate PDF
            pdf_path = generate_invoice_pdf(state)

            # Try sending email
            try:
                send_email(state, pdf_path)
            except Exception as e:
                print("[EMAIL ERROR]", e)

            return (
                "✅ Order finalized.\n"
                f"- Shipping: {state.get('shipping_final_days')} days\n"
                f"- Expedited fee: {state.get('expedited_fee')} RON\n"
                f"- Final total: {state.get('final_total_price')} RON\n"
                "📄 Invoice PDF generated (and email attempted)."
            )

        # Continue negotiation
        return response.get(
            "message",
            "Standard delivery is 5–7 days. Do you have a preference?"
        )
