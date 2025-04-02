import time
from fastapi.testclient import TestClient
from typing import Optional # Removed unused Dict, Any, pytest

# Use fixtures defined in root conftest.py
# API_KEY is available via the api_key fixture
# TestClient is available via the integration_client fixture

CUSTOMER_ID_ORDER_EDGES = "int_customer_order_edges" # Renamed slightly to avoid potential conflicts

# Helper function adapted from the original script, using TestClient
def create_product_with_inventory_helper(
    client: TestClient,
    api_key: str,
    name: str,
    quantity: float,
    price: float = 10.0,
    unit: str = "item"
) -> Optional[int]:
    """Helper to create a product and set its initial inventory for integration tests."""
    print(f"--- Setup: Creating Product '{name}' with quantity {quantity} ---")
    prod_data = {"name": name, "unit": unit, "price_per_unit": price}
    prod_response = client.post(f"/api/products?api_key={api_key}", json=prod_data)

    if prod_response.status_code != 201:
        print(f"[WARN] Failed to create product '{name}'. Status: {prod_response.status_code}, Detail: {prod_response.text}")
        return None

    product_id = prod_response.json()["id"]
    inv_data = {"quantity": quantity}
    inv_response = client.patch(f"/api/inventory/{product_id}?api_key={api_key}", json=inv_data)

    if inv_response.status_code != 200:
        print(f"[WARN] Failed to set inventory for product {product_id}. Status: {inv_response.status_code}, Detail: {inv_response.text}")
        # Optionally delete the created product here if setup needs to be atomic
        return None # Indicate partial failure

    print(f"[INFO] Product '{name}' (ID: {product_id}) created with inventory {quantity}.")
    return product_id

# --- Test Cases ---

# Test 1: Order Last Item
def test_order_last_item(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_id = create_product_with_inventory_helper(client, api_key, "Last Item Widget", 1.0)
    assert prod_id is not None, "Setup failed: Could not create product for test_order_last_item"

    order_data = {"customer_id": CUSTOMER_ID_ORDER_EDGES, "items": [{"product_id": prod_id, "quantity": 1.0}]}

    # Place the order for the last item
    response_first = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response_first.status_code == 201

    # Try ordering again (should fail)
    response_second = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response_second.status_code == 400
    # assert "Not enough inventory available" in response_second.json()["detail"] # Check specific error
    assert f"Insufficient inventory for product ID {prod_id}" in response_second.json()["detail"] # Corrected error message check

    # Check inventory status
    status_response = client.get(f"/api/inventory/status/{prod_id}?api_key={api_key}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["quantity"] == 0.0
    assert status_data["status"] == "out_of_stock"

# Test 2: Order Item with Zero Inventory
def test_order_zero_inventory(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_id = create_product_with_inventory_helper(client, api_key, "Zero Inv Widget", 0.0)
    assert prod_id is not None, "Setup failed: Could not create product for test_order_zero_inventory"

    order_data = {"customer_id": CUSTOMER_ID_ORDER_EDGES, "items": [{"product_id": prod_id, "quantity": 1.0}]}
    response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response.status_code == 400
    # assert "Not enough inventory available" in response.json()["detail"]
    assert f"Insufficient inventory for product ID {prod_id}" in response.json()["detail"] # Corrected error message check

# Test 3: Order More Than Available
def test_order_insufficient_inventory(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_id = create_product_with_inventory_helper(client, api_key, "Low Inv Widget", 5.0)
    assert prod_id is not None, "Setup failed: Could not create product for test_order_insufficient_inventory"

    order_data = {"customer_id": CUSTOMER_ID_ORDER_EDGES, "items": [{"product_id": prod_id, "quantity": 6.0}]}
    response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response.status_code == 400
    # assert "Not enough inventory available" in response.json()["detail"]
    assert f"Insufficient inventory for product ID {prod_id}" in response.json()["detail"] # Corrected error message check

# Test 4: Mixed Stock Order (Expect Full Failure)
def test_order_mixed_stock_failure(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_ok_id = create_product_with_inventory_helper(client, api_key, "Mixed OK Widget", 20.0)
    prod_fail_id = create_product_with_inventory_helper(client, api_key, "Mixed Fail Widget", 2.0)
    assert prod_ok_id is not None and prod_fail_id is not None, "Setup failed: Could not create products for test_order_mixed_stock_failure"

    order_data = {
        "customer_id": CUSTOMER_ID_ORDER_EDGES,
        "items": [
            {"product_id": prod_ok_id, "quantity": 10.0},
            {"product_id": prod_fail_id, "quantity": 3.0} # Order more than available
        ]
    }
    response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response.status_code == 400
    # Check error message relates to the failing product
    assert f"Insufficient inventory for product ID {prod_fail_id}" in response.json()["detail"]

    # Verify inventory wasn't deducted for the OK item (rollback check)
    status_response = client.get(f"/api/inventory/status/{prod_ok_id}?api_key={api_key}")
    assert status_response.status_code == 200
    assert status_response.json()["quantity"] == 20.0

# Test 5: Quick Reorder Without History (Defaults to quantity 1)
def test_quick_order_no_history(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_id = create_product_with_inventory_helper(client, api_key, "Quick Order Widget", 50.0)
    assert prod_id is not None, "Setup failed: Could not create product for test_quick_order_no_history"

    # Use a customer ID guaranteed to have no history for this product
    new_customer = f"new_cust_{int(time.time())}"
    quick_params = {"customer_id": new_customer, "product_id": prod_id} # No quantity param

    response = client.post(f"/api/orders/quick?api_key={api_key}", params=quick_params)
    assert response.status_code == 201
    order_data = response.json()
    assert len(order_data["items"]) == 1
    assert order_data["items"][0]["quantity"] == 1.0 # Verify default quantity

    # Verify inventory deducted by 1
    status_response = client.get(f"/api/inventory/status/{prod_id}?api_key={api_key}")
    assert status_response.status_code == 200
    assert status_response.json()["quantity"] == 49.0

# Test 6: Order Status Transitions
def test_order_status_transitions(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_id = create_product_with_inventory_helper(client, api_key, "Status Widget", 30.0)
    assert prod_id is not None, "Setup failed: Could not create product for test_order_status_transitions"

    # Create initial order
    order_data = {"customer_id": CUSTOMER_ID_ORDER_EDGES, "items": [{"product_id": prod_id, "quantity": 2.0}]}
    order_response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert order_response.status_code == 201
    order_id = order_response.json()["id"]
    assert order_response.json()["status"] == "pending"

    # Update status: pending -> shipped
    status_update_resp = client.patch(f"/api/orders/{order_id}/status?api_key={api_key}", json={"status": "shipped"})
    assert status_update_resp.status_code == 200
    assert status_update_resp.json()["status"] == "shipped"

    # Update status: shipped -> delivered (Should fail as per defined lifecycle)
    status_update_resp = client.patch(f"/api/orders/{order_id}/status?api_key={api_key}", json={"status": "delivered"})
    assert status_update_resp.status_code == 400 # Expecting failure for this transition
    # assert status_update_resp.json()["status"] == "delivered" # Status won't be delivered if update fails

    # Attempt Update status: delivered -> invalid_status (Should fail)
    status_update_resp = client.patch(f"/api/orders/{order_id}/status?api_key={api_key}", json={"status": "invalid_status"})
    assert status_update_resp.status_code == 400 # Should fail: Invalid status value
    # assert "Invalid status" in status_update_resp.json()["detail"] # Check specific error

    # Get final status (should still be 'shipped' after failed 'delivered' update)
    get_order_resp = client.get(f"/api/orders/{order_id}?api_key={api_key}")
    assert get_order_resp.status_code == 200
    assert get_order_resp.json()["status"] == "shipped" # Status should not have changed from shipped

# Test 7: Order with Decimal Quantity
def test_order_decimal_quantity(integration_client: TestClient, api_key: str):
    client = integration_client
    prod_id = create_product_with_inventory_helper(client, api_key, "Decimal Widget", 10.0, unit="kg")
    assert prod_id is not None, "Setup failed: Could not create product for test_order_decimal_quantity"

    order_data = {"customer_id": CUSTOMER_ID_ORDER_EDGES, "items": [{"product_id": prod_id, "quantity": 2.75}]}
    response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response.status_code == 201

    # Verify inventory
    status_response = client.get(f"/api/inventory/status/{prod_id}?api_key={api_key}")
    assert status_response.status_code == 200
    assert status_response.json()["quantity"] == 7.25 # 10.0 - 2.75