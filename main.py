from state import OrderState
from salesperson import SalespersonAgent
from contracting import ContractingAgent
from shipping import ShippingAgent

def main():
    state = OrderState()
    agent = SalespersonAgent()

    conversation_history = [] # istoric global al conversatiei

    print("🛒 Welcome to the Automated Shop!")

    while True:
        user_input = input("\nUser: ").strip()

        if state.order_locked:
            print("\nSystem: Order already completed. Thank you!")
            break

        # adauga input-ul userului in istoric
        conversation_history.append({"role": "user", "content": user_input})

        state_dict = state.to_dict()

        reply = agent.run(
            user_input=user_input,
            state=state_dict,
            conversation=conversation_history   # trimis mai departe
        )

        # ---------------------------
        # Handle handoffs
        # ---------------------------
        if isinstance(reply, dict):
            if reply.get("handoff") == "contracting":
                # sync updates back to OrderState before switching agents
                for k, v in state_dict.items():
                    setattr(state, k, v)
                agent = ContractingAgent()
                state.phase = "contracting"
                print("\nSystem: Transferring you to Contracting...")
                continue

            if reply.get("handoff") == "shipping":
                for k, v in state_dict.items():
                    setattr(state, k, v)
                agent = ShippingAgent()
                state.phase = "shipping"
                print("\nSystem: Transferring you to Shipping...")
                continue

        conversation_history.append({"role": "assistant", "content": reply})
        # ---------------------------
        # Normal agent message
        # ---------------------------
        print("\nAgent:", reply)

        # ---------------------------
        # Sync updated dict state back into OrderState so context persists
        # ---------------------------
        for k, v in state_dict.items():
            setattr(state, k, v)

        # ---------------------------
        # Finalization check
        # ---------------------------
        if state.phase == "complete":
            print("\nSystem: Order process completed successfully.")
            break


if __name__ == "__main__":
    main()
