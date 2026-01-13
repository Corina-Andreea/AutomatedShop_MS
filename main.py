from state import OrderState
from salesperson import SalespersonAgent
from contracting import ContractingAgent
from shipping import ShippingAgent

def main():
    state = OrderState()
    agent = SalespersonAgent()

    print("🛒 Welcome to the Automated Shop!")

    while True:
        user_input = input("\nUser: ").strip()

        # Stop if order is fully completed
        if state.order_locked:
            print("\nSystem: Order already completed. Thank you!")
            break

        reply = agent.run(user_input, state.to_dict())

        # ---------------------------
        # Handle handoffs
        # ---------------------------
        if isinstance(reply, dict):
            if reply.get("handoff") == "contracting":
                agent = ContractingAgent()
                state.phase = "contracting"
                print("\nSystem: Transferring you to Contracting...")
                continue

            if reply.get("handoff") == "shipping":
                agent = ShippingAgent()
                state.phase = "shipping"
                print("\nSystem: Transferring you to Shipping...")
                continue

        # ---------------------------
        # Normal agent message
        # ---------------------------
        print("\nAgent:", reply)

        # ---------------------------
        # Finalization check
        # ---------------------------
        if state.phase == "complete":
            print("\nSystem: Order process completed successfully.")
            break


if __name__ == "__main__":
    main()
