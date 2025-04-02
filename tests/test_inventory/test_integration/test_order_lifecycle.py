from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock # For mocking webhook send
# Removed unused Dict, Any imports

# Import models needed for verification - None needed directly in this file now
# from inventory_prototype.models import Product, Inventory, Order, OrderItem # Updated import path

# Use fixtures defined in ../conftest.py
# pytestmark = pytest.mark.usefixtures("setup_integration_database") # Removed as setup is handled in other fixtures

# Removed duplicated imports and old test function below

def test_list_orders_with_pagination_and_filter(integration_client: TestClient, db_session: Session, api_key: str):
    """
    Tests the functionality of the GET /api/orders endpoint, specifically focusing
    on pagination (skip, limit) and filtering by customer_id.

    Steps:
    1. Creates two distinct products and sets their inventory.
    2. Creates multiple orders (5 total) for two different customer IDs (cust1, cust2),
       mocking webhook calls.
    3. Lists all orders without filters and verifies that at least the created orders
       are present in the response.
    4. Lists orders using the 'limit' parameter and verifies the correct number
       and IDs of orders are returned based on creation time descending.
    5. Lists orders using 'skip' and 'limit' parameters and verifies the correct
       subset and IDs of orders are returned based on creation time descending.
    6. Lists orders filtered by the first customer ID (cust1) and verifies the
       count and customer ID match.
    7. Lists orders filtered by the second customer ID (cust2) with pagination (limit),
       verifying the first page results based on creation time descending.
    8. Lists orders filtered by the second customer ID (cust2) with pagination
       (skip and limit), verifying the second page results based on creation time descending.
    """
    client = integration_client

    # 1. Create Products
    p1_resp = client.post(f"/api/products?api_key={api_key}", json={"name": "ListOrder P1", "unit": "item", "price_per_unit": 10.0})
    p2_resp = client.post(f"/api/products?api_key={api_key}", json={"name": "ListOrder P2", "unit": "item", "price_per_unit": 20.0})
    p1_id = p1_resp.json()["id"]
    p2_id = p2_resp.json()["id"]
    client.patch(f"/api/inventory/{p1_id}?api_key={api_key}", json={"quantity": 100})
    client.patch(f"/api/inventory/{p2_id}?api_key={api_key}", json={"quantity": 100})

    # 2. Create Orders
    cust1 = "list_cust_A"
    cust2 = "list_cust_B"
    order_ids = []
    with patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock):
        # Cust A orders
        order_ids.append(client.post(f"/api/orders?api_key={api_key}", json={"customer_id": cust1, "items": [{"product_id": p1_id, "quantity": 1}]}).json()["id"])
        order_ids.append(client.post(f"/api/orders?api_key={api_key}", json={"customer_id": cust1, "items": [{"product_id": p2_id, "quantity": 2}]}).json()["id"])
        # Cust B orders
        order_ids.append(client.post(f"/api/orders?api_key={api_key}", json={"customer_id": cust2, "items": [{"product_id": p1_id, "quantity": 3}]}).json()["id"])
        order_ids.append(client.post(f"/api/orders?api_key={api_key}", json={"customer_id": cust2, "items": [{"product_id": p2_id, "quantity": 4}]}).json()["id"])
        order_ids.append(client.post(f"/api/orders?api_key={api_key}", json={"customer_id": cust2, "items": [{"product_id": p1_id, "quantity": 5}]}).json()["id"])

    total_orders_created = 5
    cust1_orders = 2
    cust2_orders = 3
    # order_ids list created during setup is useful for checking presence

    # 3. List all orders and determine correct order (created_at desc)
    response_all = client.get(f"/api/orders?limit=100&api_key={api_key}") # Fetch all relevant orders
    assert response_all.status_code == 200
    data_all = response_all.json()
    assert isinstance(data_all, list)
    # Check if at least the created orders are present
    assert len(data_all) >= total_orders_created
    listed_all_ids = {o['id'] for o in data_all}
    assert set(order_ids).issubset(listed_all_ids) # Check all created orders are returned

    # Sort the fetched orders by created_at descending to match API behavior
    # Filter only the orders we created in this test to avoid interference
    test_orders = [o for o in data_all if o['id'] in order_ids]
    correctly_ordered_ids = [o['id'] for o in sorted(test_orders, key=lambda x: x['created_at'], reverse=True)]

    # 4. List orders with limit
    limit = 2
    response_limit = client.get(f"/api/orders?limit={limit}&api_key={api_key}")
    assert response_limit.status_code == 200
    data_limit = response_limit.json()
    assert len(data_limit) == limit
    assert data_limit[0]['id'] == correctly_ordered_ids[0] # Use correctly sorted list
    assert data_limit[1]['id'] == correctly_ordered_ids[1] # Use correctly sorted list

    # 5. List orders with skip and limit
    skip = 1
    limit = 3
    response_skip_limit = client.get(f"/api/orders?skip={skip}&limit={limit}&api_key={api_key}")
    assert response_skip_limit.status_code == 200
    data_skip_limit = response_skip_limit.json()
    # Adjust expected length if skip + limit exceeds total items
    expected_len = min(limit, len(correctly_ordered_ids) - skip)
    assert len(data_skip_limit) == expected_len
    if expected_len > 0:
        assert data_skip_limit[0]['id'] == correctly_ordered_ids[skip] # Use correctly sorted list
    if expected_len > 1:
        assert data_skip_limit[1]['id'] == correctly_ordered_ids[skip + 1] # Use correctly sorted list
    if expected_len > 2:
        assert data_skip_limit[2]['id'] == correctly_ordered_ids[skip + 2] # Use correctly sorted list

    # 6. List orders filtered by customer_id (cust1)
    response_cust1 = client.get(f"/api/orders?customer_id={cust1}&api_key={api_key}")
    assert response_cust1.status_code == 200
    data_cust1 = response_cust1.json()
    assert len(data_cust1) == cust1_orders
    assert all(o['customer_id'] == cust1 for o in data_cust1)

    # 7. List orders filtered by customer_id (cust2) with pagination
    limit_cust2 = 2
    response_cust2_page1 = client.get(f"/api/orders?customer_id={cust2}&limit={limit_cust2}&api_key={api_key}")
    assert response_cust2_page1.status_code == 200
    data_cust2_page1 = response_cust2_page1.json()
    assert len(data_cust2_page1) == limit_cust2
    assert all(o['customer_id'] == cust2 for o in data_cust2_page1)
    # Get correctly ordered IDs for cust2 only
    cust2_correctly_ordered_ids = [o['id'] for o in sorted(test_orders, key=lambda x: x['created_at'], reverse=True) if o['customer_id'] == cust2]
    assert data_cust2_page1[0]['id'] == cust2_correctly_ordered_ids[0]
    assert data_cust2_page1[1]['id'] == cust2_correctly_ordered_ids[1]

    skip_cust2 = 2
    response_cust2_page2 = client.get(f"/api/orders?customer_id={cust2}&skip={skip_cust2}&limit={limit_cust2}&api_key={api_key}")
    assert response_cust2_page2.status_code == 200
    data_cust2_page2 = response_cust2_page2.json()
    assert len(data_cust2_page2) == cust2_orders - skip_cust2 # Remaining orders
    assert all(o['customer_id'] == cust2 for o in data_cust2_page2)
    assert data_cust2_page2[0]['id'] == cust2_correctly_ordered_ids[skip_cust2]
