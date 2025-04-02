# import pytest # Removed unused import
from fastapi.testclient import TestClient
# from sqlalchemy.orm import Session # Removed unused import
from typing import Dict, Any, List # Added List
from unittest.mock import patch, AsyncMock

# Use fixtures defined in root conftest.py

# Helper to create a product (can be moved to a shared conftest later if needed)
def create_product_helper(client: TestClient, api_key: str, name: str, unit: str, price: float, description: str | None = None, custom_properties: Dict[str, Any] | None = None) -> int:
    """Helper to create a product and return its ID."""
    payload: Dict[str, Any] = {"name": name, "unit": unit, "price_per_unit": price}
    if description:
        payload["description"] = description
    if custom_properties:
        payload["custom_properties"] = custom_properties
    prod_response = client.post(f"/api/products?api_key={api_key}", json=payload)
    assert prod_response.status_code == 201, f"Failed to create product {name}: {prod_response.text}"
    return prod_response.json()["id"]

# Helper to set inventory
def set_inventory_helper(client: TestClient, api_key: str, product_id: int, quantity: float):
    """Helper to set inventory for a product."""
    inv_response = client.patch(f"/api/inventory/{product_id}?api_key={api_key}", json={"quantity": quantity}) # Corrected syntax
    assert inv_response.status_code == 200

# Helper to create an order
def create_order_helper(client: TestClient, api_key: str, customer_id: str, items: List[Dict[str, Any]]) -> int: # Added specific type hint
    """Helper to create an order."""
    order_data = {"customer_id": customer_id, "items": items}
    with patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock): # Updated patch target
        response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response.status_code == 201
    return response.json()["id"]


def test_create_b2b_product_with_custom_props(integration_client: TestClient, api_key: str):
    """Test creating a product with B2B/food relevant custom properties."""
    client = integration_client
    b2b_props = {
        "supplier_code": "SUPPLIER_XYZ",
        "case_pack_size": 24,
        "storage_requirements": "Keep refrigerated (2-5°C)",
        "country_of_origin": "Philippines",
        "lead_time_days": 3,
        "is_tax_exempt": False
    }
    product_id = create_product_helper(
        client, api_key,
        name="Frozen Ube Paste (Case)",
        unit="case",
        price=1500.00,
        description="Case of 24 x 500g frozen ube paste",
        custom_properties=b2b_props
    )

    # Verify product creation and custom properties via GET
    response = client.get(f"/api/products/{product_id}?api_key={api_key}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Frozen Ube Paste (Case)"
    assert data["custom_properties"] == b2b_props

def test_update_b2b_product_custom_props(integration_client: TestClient, api_key: str):
    """Test updating B2B custom properties."""
    client = integration_client
    initial_props = {"supplier_code": "OLD_SUP", "case_pack_size": 12}
    product_id = create_product_helper(
        client, api_key, "Calamansi Concentrate", "bottle", 80.0, custom_properties=initial_props
    )

    # Update properties
    updated_props = {
        "supplier_code": "NEW_SUP",
        "case_pack_size": 24, # Changed
        "shelf_life_months": 12 # Added
    }
    update_payload = {"custom_properties": updated_props}
    response = client.patch(f"/api/products/{product_id}?api_key={api_key}", json=update_payload)
    assert response.status_code == 200

    # Verify update
    get_response = client.get(f"/api/products/{product_id}?api_key={api_key}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["custom_properties"] == updated_props


def test_customer_order_history_b2b(integration_client: TestClient, api_key: str):
    """Test the customer order history endpoint with multiple orders and products."""
    client = integration_client
    customer_id = "b2b_hist_cust"

    # Create products
    p1_id = create_product_helper(client, api_key, "Adobo Mix Sachets", "box", 300.0) # Box of 50
    p2_id = create_product_helper(client, api_key, "Sinigang Mix Sachets", "box", 350.0) # Box of 50
    p3_id = create_product_helper(client, api_key, "Cooking Oil", "liter", 90.0)
    set_inventory_helper(client, api_key, p1_id, 1000.0)
    set_inventory_helper(client, api_key, p2_id, 1000.0)
    set_inventory_helper(client, api_key, p3_id, 1000.0)

    # Create orders over time (mocking time is complex, just create sequentially)
    # Order 1: Adobo x 2 boxes
    create_order_helper(client, api_key, customer_id, [{"product_id": p1_id, "quantity": 2}])
    # Order 2: Sinigang x 1 box, Oil x 10 liters
    create_order_helper(client, api_key, customer_id, [{"product_id": p2_id, "quantity": 1}, {"product_id": p3_id, "quantity": 10}])
    # Order 3: Adobo x 3 boxes
    create_order_helper(client, api_key, customer_id, [{"product_id": p1_id, "quantity": 3}])
    # Order 4: Oil x 5 liters
    create_order_helper(client, api_key, customer_id, [{"product_id": p3_id, "quantity": 5}])

    # Get history using the list endpoint with customer filter
    response = client.get(f"/api/orders?customer_id={customer_id}&api_key={api_key}")
    assert response.status_code == 200
    orders_list = response.json() # This is now a list of orders

    assert isinstance(orders_list, list)
    assert len(orders_list) == 4 # Check the number of orders returned

    # Further assertions would need to process the list, e.g., check customer_id in each order
    assert all(o['customer_id'] == customer_id for o in orders_list)

    # Re-calculate product frequency from the list of orders
    product_counts: Dict[int, int] = {}
    for order in orders_list:
        for item in order.get('items', []):
            pid = item.get('product_id')
            if pid:
                product_counts[pid] = product_counts.get(pid, 0) + 1 # Count orders per product

    # Sort products by frequency (descending)
    sorted_products = sorted(product_counts.items(), key=lambda item: item[1], reverse=True)

    # Verify frequency and sorting (Adobo/p1: 2 orders, Oil/p3: 2 orders, Sinigang/p2: 1 order)
    assert len(sorted_products) == 3 # All 3 products ordered

    # Check top two (p1 and p3 have frequency 2, order between them isn't guaranteed)
    assert sorted_products[0][0] in [p1_id, p3_id]
    assert sorted_products[0][1] == 2
    assert sorted_products[1][0] in [p1_id, p3_id]
    assert sorted_products[1][1] == 2
    assert sorted_products[0][0] != sorted_products[1][0] # Ensure they are different

    # Check third product (p2 has frequency 1)
    assert sorted_products[2][0] == p2_id
    assert sorted_products[2][1] == 1

    # Test with shorter history period (e.g., 0 days - might get tricky without time mocking)
    # response_short = client.get(f"/api/orders/history/{customer_id}/history?days=0&api_key={api_key}")
    # assert response_short.status_code == 200
    # assert response_short.json()["order_count"] == 0 # Assuming orders weren't created *exactly* now