from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
    # No need to mock webhook here as we only care about the order creation status
    response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    if response.status_code == 201:
        return response.json()["id"]
    return None

# Helper to register a webhook
def register_webhook(client: TestClient, api_key: str, url: str, secret: str) -> int:
    """Helper to register a webhook and return its ID."""
    webhook_data = {"url": url, "secret": secret}
    response = client.post(f"/api/webhooks?api_key={api_key}", json=webhook_data)
    assert response.status_code == 201
    return response.json()["id"]


def test_authentication_integration(integration_client: TestClient, db_session: Session, api_key: str):
    """
    Integration test covering authentication for various key endpoints.
    Checks for failures with missing and invalid API keys.
    """
    client = integration_client
    invalid_key = "this-is-not-the-key"

    # --- Setup some data using the valid key ---
    product_id = create_product(client, api_key, "Auth Test Prod", "unit", 1.0)
    set_inventory(client, api_key, product_id, 10.0)
    order_id = create_order(client, api_key, "auth_cust", product_id, 1.0)
    assert order_id is not None
    webhook_id = register_webhook(client, api_key, "https://auth-test.com", "auth_secret")

    # --- Test Endpoints with MISSING API Key ---
    # Products
    assert client.get("/api/products").status_code == 401
    assert client.post("/api/products", json={"name":"p","unit":"u","price_per_unit":1}).status_code == 401
    assert client.get(f"/api/products/{product_id}").status_code == 401
    assert client.patch(f"/api/products/{product_id}", json={"name":"p2"}).status_code == 401
    assert client.get("/api/products/search/?query=Auth").status_code == 401
    # Inventory
    assert client.patch(f"/api/inventory/{product_id}", json={"quantity": 5}).status_code == 401
    assert client.get(f"/api/inventory/status/{product_id}").status_code == 401
    assert client.get("/api/inventory").status_code == 401
    assert client.get(f"/api/inventory/{product_id}").status_code == 401
    # Orders
    assert client.post("/api/orders", json={"customer_id":"c","items":[{"product_id":product_id,"quantity":1}]}).status_code == 401
    assert client.patch(f"/api/orders/{order_id}/status", json={"status":"s"}).status_code == 401
    assert client.post("/api/orders/quick", params={"customer_id":"c","product_id":product_id,"quantity":1}).status_code == 401
    assert client.get(f"/api/orders?customer_id={'auth_cust'}").status_code == 401
    # Webhooks
    assert client.post("/api/webhooks", json={"url":"https://a.com","secret":"s"}).status_code == 401
    assert client.delete(f"/api/webhooks/{webhook_id}").status_code == 401
    # System
    assert client.get("/").status_code == 200 # Health check (root path) should not require auth

    # --- Test Endpoints with INVALID API Key ---
    # Products
    assert client.get(f"/api/products?api_key={invalid_key}").status_code == 401
    assert client.post(f"/api/products?api_key={invalid_key}", json={"name":"p","unit":"u","price_per_unit":1}).status_code == 401
    assert client.get(f"/api/products/{product_id}?api_key={invalid_key}").status_code == 401
    assert client.patch(f"/api/products/{product_id}?api_key={invalid_key}", json={"name":"p2"}).status_code == 401
    assert client.get(f"/api/products/search/?query=Auth&api_key={invalid_key}").status_code == 401
    # Inventory
    assert client.patch(f"/api/inventory/{product_id}?api_key={invalid_key}", json={"quantity": 5}).status_code == 401
    assert client.get(f"/api/inventory/status/{product_id}?api_key={invalid_key}").status_code == 401
    assert client.get(f"/api/inventory?api_key={invalid_key}").status_code == 401
    assert client.get(f"/api/inventory/{product_id}?api_key={invalid_key}").status_code == 401
    # Orders
    assert client.post(f"/api/orders?api_key={invalid_key}", json={"customer_id":"c","items":[{"product_id":product_id,"quantity":1}]}).status_code == 401
    assert client.patch(f"/api/orders/{order_id}/status?api_key={invalid_key}", json={"status":"s"}).status_code == 401
    assert client.post(f"/api/orders/quick?api_key={invalid_key}", params={"customer_id":"c","product_id":product_id,"quantity":1}).status_code == 401
    assert client.get(f"/api/orders?customer_id={'auth_cust'}&api_key={invalid_key}").status_code == 401
    # Webhooks
    assert client.post(f"/api/webhooks?api_key={invalid_key}", json={"url":"https://a.com","secret":"s"}).status_code == 401
    assert client.delete(f"/api/webhooks/{webhook_id}?api_key={invalid_key}").status_code == 401

    # --- Test one endpoint with VALID API Key (sanity check) ---
    assert client.get(f"/api/products?api_key={api_key}").status_code == 200
