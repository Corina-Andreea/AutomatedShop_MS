from llm import call_llm
import json
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
- Send confirmation email
- Generate PDF invoice
- Clearly state order is finalized

OUTPUT STRICT JSON:

{
  "message": "",
  "shipping_days": 0,
  "expedited_fee": 0,
  "action": "continue | finalize"
}

If action == "finalize", output ONLY:
{ "finalized": true }
"""


class ShippingAgent:
    def run(self, user_input: str, state: dict):
        raw = call_llm(SYSTEM_PROMPT, user_input, state)
        response = json.loads(raw)

        if "shipping_days" in response:
            state["shipping_final_days"] = response["shipping_days"]

        if "expedited_fee" in response:
            state["expedited_fee"] = response["expedited_fee"]

        if response.get("action") == "finalize":
            send_email(state)
            generate_invoice_pdf(state)
            return "Order finalized. Confirmation email and invoice sent."

        return response["message"]
