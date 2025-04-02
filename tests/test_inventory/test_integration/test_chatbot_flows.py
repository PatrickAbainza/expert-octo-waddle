# import pytest # Keep pytest for skip marker - Removed as no longer needed
from fastapi.testclient import TestClient
from typing import Dict # Added Dict for fixture type hint
from unittest.mock import patch, AsyncMock # Added for mocking webhooks

# Use fixtures defined in root conftest.py

# Assume helpers from other integration tests might be refactored into conftest later
# For now, potentially redefine or import if needed

def test_chatbot_check_availability(integration_client: TestClient, api_key: str, chatbot_products: Dict[str, int]):
    """Simulate chatbot checking product availability.""" # Rewritten docstring
    # pytest.skip("Skipping test: Requires product setup fixture/helper") # Skip removed
    client = integration_client
    # Setup: Uses the chatbot_products fixture which creates 'Test Flour' with 100kg inventory

    # 1. Chatbot searches for 'flour'
    search_response = client.get(f"/api/products/search/?query=flour&api_key={api_key}")
    assert search_response.status_code == 200
    search_results = search_response.json()
    # Find the specific product ID from results
    assert len(search_results) > 0, "Search for 'flour' returned no results"
    product_id = -1
    for p in search_results:
        if p['name'] == "Test Flour":
            product_id = p['id']
            break
    assert product_id != -1, "Could not find 'Test Flour' in search results"
    assert product_id == chatbot_products["Test Flour"] # Verify it's the correct ID from fixture

    # 2. Chatbot checks status for the found product
    status_response = client.get(f"/api/inventory/status/{product_id}?api_key={api_key}")
    assert status_response.status_code == 200
    status_data = status_response.json()

    # 3. Assertions based on expected chatbot response logic
    assert status_data['status'] == 'in_stock' # Initial inventory is 100kg
    assert status_data['quantity'] == 100.0 # Check quantity from fixture setup
    # assert status_data['available'] is True # Removed: 'available' key is not returned by this endpoint

def test_chatbot_place_order_via_search(integration_client: TestClient, api_key: str, chatbot_products: Dict[str, int]):
    """Simulate chatbot placing an order after searching.""" # Rewritten docstring
    # pytest.skip("Skipping test: Requires product setup fixture/helper") # Skip removed
    client = integration_client
    customer_id = "chatbot_order_cust_sugar" # Unique customer ID
    # Setup: Uses chatbot_products fixture ('Test Sugar' with 50kg inventory)

    # 1. Chatbot searches for 'sugar'
    search_response = client.get(f"/api/products/search/?query=sugar&api_key={api_key}")
    assert search_response.status_code == 200
    search_results = search_response.json()
    assert len(search_results) > 0, "Search for 'sugar' returned no results"
    product_id = -1
    product_price = -1.0
    for p in search_results:
        if p['name'] == "Test Sugar":
            product_id = p['id']
            product_price = p['price_per_unit']
            break
    assert product_id != -1, "Could not find 'Test Sugar' in search results"
    assert product_id == chatbot_products["Test Sugar"] # Verify correct ID
    assert product_price == 40.0 # Verify correct price from fixture setup

    order_quantity = 10.0

    # 2. Chatbot places order using found product ID (Using standard order)
    order_payload = {"customer_id": customer_id, "items": [{"product_id": product_id, "quantity": order_quantity}]}
    # Mock webhook during order creation
    with patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock):
        order_response = client.post(f"/api/orders?api_key={api_key}", json=order_payload)
    assert order_response.status_code == 201, f"Order placement failed: {order_response.text}"
    order_id = order_response.json()['id']

    # 3. Verify order details
    get_order_response = client.get(f"/api/orders/{order_id}?api_key={api_key}")
    assert get_order_response.status_code == 200
    order_details = get_order_response.json()
    assert order_details['customer_id'] == customer_id
    assert len(order_details['items']) == 1
    assert order_details['items'][0]['product_id'] == product_id
    assert order_details['items'][0]['quantity'] == order_quantity
    assert order_details['total'] == product_price * order_quantity # 40.0 * 10.0 = 400.0

    # 4. Verify inventory deduction (optional but good)
    status_response = client.get(f"/api/inventory/status/{product_id}?api_key={api_key}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data['quantity'] == 40.0 # Initial 50kg - 10kg ordered

def test_chatbot_reorder_frequent(integration_client: TestClient, api_key: str, chatbot_products: Dict[str, int], chatbot_order_history: str):
    """Simulate chatbot suggesting and placing a reorder based on history.""" # Rewritten docstring
    # pytest.skip("Skipping test: Requires product and order history setup fixture/helper") # Skip removed
    client = integration_client
    customer_id = chatbot_order_history # Use customer_id from the fixture
    # Setup: Uses chatbot_order_history fixture which creates orders for 'Test Flour' (3 times) and 'Test Sugar' (1 time)

    # 1. Chatbot gets customer history (using list endpoint)
    history_response = client.get(f"/api/orders?customer_id={customer_id}&api_key={api_key}")
    assert history_response.status_code == 200
    orders_list = history_response.json() # This is now a list
    assert isinstance(orders_list, list)
    assert len(orders_list) == 3 # 3 orders created in fixture

    # 2. Chatbot identifies most frequent product (needs recalculation)
    product_counts: Dict[int, int] = {}
    for order in orders_list:
        for item in order.get('items', []):
            pid = item.get('product_id')
            if pid:
                product_counts[pid] = product_counts.get(pid, 0) + 1 # Count orders per product

    assert len(product_counts) > 0, "No products found in order history"
    # Find the product ID with the highest count
    frequent_product_id = max(product_counts.keys(), key=lambda k: product_counts[k]) # Use lambda for key

    assert frequent_product_id == chatbot_products["Test Flour"] # Verify Flour is most frequent
    assert product_counts[frequent_product_id] == 3 # Verify frequency count

    # 3. Chatbot places quick reorder for the most frequent product
    # Mock webhook during order creation
    with patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock):
        reorder_response = client.post(f"/api/orders/quick?api_key={api_key}", params={"customer_id": customer_id, "product_id": frequent_product_id})
    assert reorder_response.status_code == 201, f"Quick reorder failed: {reorder_response.text}"
    reorder_data = reorder_response.json()

    # 4. Verify order creation and details
    assert reorder_data['customer_id'] == customer_id
    assert len(reorder_data['items']) == 1
    assert reorder_data['items'][0]['product_id'] == frequent_product_id
    # Quick order defaults quantity to 1.0 if not provided
    assert reorder_data['items'][0]['quantity'] == 1.0 # Expecting 1.0 as default

    # 5. Check history again (optional, count should increase) using the list endpoint
    history_response_after = client.get(f"/api/orders?customer_id={customer_id}&api_key={api_key}")
    assert history_response_after.status_code == 200
    assert len(history_response_after.json()) == 4 # Original 3 + 1 reorder

def test_chatbot_get_featured(integration_client: TestClient, api_key: str, chatbot_products: Dict[str, int]):
    """Simulate chatbot getting featured products.""" # Rewritten docstring
    # pytest.skip("Skipping test: Requires product setup fixture/helper") # Skip removed
    client = integration_client
    # Setup: Uses chatbot_products fixture (Flour: 100kg, Sugar: 50kg, Coffee: 20kg)

    # 1. Chatbot calls featured endpoint
    response = client.get(f"/api/products/featured?limit=3&api_key={api_key}")
    assert response.status_code == 200
    featured_products = response.json()

    # 2. Assertions on response structure and content
    assert isinstance(featured_products, list)
    # The fixture creates 3 products, so we expect up to 3 featured products
    assert len(featured_products) > 0, "Featured products endpoint returned an empty list"
    assert len(featured_products) <= 3 # Check limit respected

    found_product_ids = set()
    for product in featured_products:
        assert 'id' in product
        assert 'name' in product
        assert 'available' in product
        assert 'quantity' in product
        found_product_ids.add(product['id'])
        # Check if the product details match one of the fixture products
        assert product['id'] in chatbot_products.values()
        if product['id'] == chatbot_products["Test Flour"]:
            assert product['name'] == "Test Flour"
            assert product['quantity'] == 100.0
            assert product['available'] is True
        elif product['id'] == chatbot_products["Test Sugar"]:
            assert product['name'] == "Test Sugar"
            assert product['quantity'] == 50.0 # Or 40.0 if previous test ran in same scope (shouldn't due to function scope fixtures)
            assert product['available'] is True
        elif product['id'] == chatbot_products["Test Coffee"]:
            assert product['name'] == "Test Coffee"
            assert product['quantity'] == 20.0
            assert product['available'] is True

    # Ensure all fixture products were potentially featured (if limit allows)
    # This depends on the featured logic (e.g., highest inventory, newest, etc.)
    # For now, just check that the returned products are from our fixture set.
    assert len(found_product_ids) == len(featured_products) # Ensure unique products returned