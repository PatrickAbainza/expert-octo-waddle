from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock

# Import models needed for verification
from inventory_prototype.models import Product, OrderItem # Updated import path

# Use fixtures defined in ../conftest.py
# pytestmark = pytest.mark.usefixtures("setup_integration_database") # Removed as setup is handled in other fixtures

# Helper to create a product
def create_product(client: TestClient, api_key: str, name: str, unit: str, price: float) -> int:
    """Helper to create a product and return its ID."""
    prod_response = client.post(
        f"/api/products?api_key={api_key}",
        json={"name": name, "unit": unit, "price_per_unit": price}
    )
    assert prod_response.status_code == 201
    return prod_response.json()["id"]

# Helper to set inventory
def set_inventory(client: TestClient, api_key: str, product_id: int, quantity: float):
    """Helper to set inventory for a product."""
    inv_response = client.patch(
        f"/api/inventory/{product_id}?api_key={api_key}",
        json={"quantity": quantity}
    )
    assert inv_response.status_code == 200

# Helper to create an order
def create_order(client: TestClient, api_key: str, customer_id: str, product_id: int, quantity: float) -> int | None:
    """Helper to create an order. Returns order ID on success, None on failure."""
    order_data = {
        "customer_id": customer_id,
        "items": [{"product_id": product_id, "quantity": quantity}]
    }
    # Mock webhook during order creation for integration tests
    with patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock): # Updated patch target
        response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    if response.status_code == 201:
        return response.json()["id"]
    return None

def test_product_price_consistency_in_orders(integration_client: TestClient, db_session: Session, api_key: str):
    """
    Integration test for product price consistency:
    1. Create Product C with initial price.
    2. Set inventory.
    3. Create Order 1 for Product C.
    4. Update Product C's price.
    5. Create Order 2 for Product C.
    6. Verify price_at_order for items in Order 1 and Order 2 reflect the price at the time of each order.
    """
    client = integration_client
    customer_id = "price_consistency_cust"
    initial_price = 25.0
    updated_price = 30.0
    order_quantity = 2.0

    # 1. Create Product C
    product_id = create_product(client, api_key, "Product C", "item", initial_price)

    # 2. Set Inventory
    set_inventory(client, api_key, product_id, 10.0)

    # 3. Create Order 1
    order1_id = create_order(client, api_key, customer_id, product_id, order_quantity)
    assert order1_id is not None

    # 4. Update Product C's price
    response = client.patch(
        f"/api/products/{product_id}?api_key={api_key}",
        json={"price_per_unit": updated_price}
    )
    assert response.status_code == 200
    assert response.json()["price_per_unit"] == updated_price

    # 5. Create Order 2
    order2_id = create_order(client, api_key, customer_id, product_id, order_quantity)
    assert order2_id is not None

    # 6. Verify price_at_order in database
    db_session.commit()
    db_session.expire_all()

    # Verify Order 1 Item Price
    order1_item = db_session.query(OrderItem).filter(OrderItem.order_id == order1_id).first()
    assert order1_item is not None # Explicit check
    assert order1_item.product_id == product_id # type: ignore # Explicit check
    assert order1_item.price_at_order == initial_price # type: ignore # Should use the price at the time of Order 1

    # Verify Order 2 Item Price
    order2_item = db_session.query(OrderItem).filter(OrderItem.order_id == order2_id).first()
    assert order2_item is not None # Explicit check
    assert order2_item.product_id == product_id # type: ignore # Explicit check
    assert order2_item.price_at_order == updated_price # type: ignore # Should use the updated price at the time of Order 2

    # Verify final product price in DB
    db_product = db_session.query(Product).filter(Product.id == product_id).first()
    assert db_product is not None # Explicit check
    assert db_product.price_per_unit == updated_price # type: ignore
