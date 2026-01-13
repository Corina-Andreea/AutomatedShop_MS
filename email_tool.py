def send_email(order):
    print("\nEMAIL SENT")
    print(f"Invoice: {order.invoice_id}")
    print(f"Shipping: {order.shipping_final_days} days")
    print(f"Total: €{order.total_price}")
