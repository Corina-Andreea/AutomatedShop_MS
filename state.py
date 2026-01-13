from dataclasses import dataclass, asdict, field
from typing import Dict, List

@dataclass
class OrderState:
    # Global workflow
    phase: str = "discovery"
    contract_finalized: bool = False
    order_locked: bool = False

    # Customer & product
    customer_need: str = ""
    product: str = ""
    base_price: float = 0.0

    # Supplier
    supplier_data: Dict = field(default_factory=dict)
    supplier_last_updated: float = 0.0

    # Contracting
    upsells: List[Dict] = field(default_factory=list)
    upsell_attempts: int = 0
    total_price: float = 0.0
    invoice_id: str = ""

    # Shipping
    shipping_requested_days: int = 0
    shipping_final_days: int = 0
    expedited_fee: float = 0.0
    shipping_negotiation_turns: int = 0

    def to_dict(self):
        return asdict(self)
