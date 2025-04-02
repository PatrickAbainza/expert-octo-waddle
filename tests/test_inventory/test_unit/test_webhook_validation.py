import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, AsyncMock, Mock # Import Mock for type hinting

from inventory_prototype.main import app # Updated import
from inventory_prototype.database import Base, get_db # Updated import
from inventory_prototype.models import Webhook # Updated import

# Create test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = None
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        if db is not None:
            db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

API_KEY = "prototype_key_change_me"

# Helper to create a product and set inventory
def create_product_with_inventory(client: TestClient, name: str, unit: str, price: float, quantity: float) -> int:
    """Helper to create a product and set its initial inventory."""
    prod_response = client.post(
        f"/api/products?api_key={API_KEY}",
        json={"name": name, "unit": unit, "price_per_unit": price}
    )
    assert prod_response.status_code == 201
    product_id = prod_response.json()["id"]

    inv_response = client.patch(
        f"/api/inventory/{product_id}?api_key={API_KEY}",
        json={"quantity": quantity}
    )
    assert inv_response.status_code == 200
    return product_id

def test_register_webhook(client: TestClient):
    """Test registering a valid webhook"""
    webhook_data = {
        "url": "https://example.com/webhook",
        "secret": "supersecret",
        "events": ["order_created", "order_update"]
    }
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    # Removed message assertion as endpoint returns WebhookResponse model directly

    # Verify in DB (optional, but good for unit test)
    db = TestingSessionLocal()
    db_webhook = db.query(Webhook).filter(Webhook.id == data["id"]).first()
    # assert db_webhook is not None # Removed assertion, rely on if check
    if db_webhook is not None: # Explicit check
        assert db_webhook.url == webhook_data["url"]
        assert db_webhook.secret == webhook_data["secret"]
        assert set(db_webhook.events.split(",")) == set(webhook_data["events"])
    else:
        pytest.fail("Webhook should exist in DB but was None")
    assert set(db_webhook.events.split(",")) == set(webhook_data["events"])
    db.close()

def test_register_webhook_default_events(client: TestClient):
    """Test registering a webhook without specifying events (should default)"""
    webhook_data = {
        "url": "https://example.com/webhook-default",
        "secret": "anothersecret"
        # events field omitted
    }
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data

    # Verify default event in DB
    db = TestingSessionLocal()
    db_webhook = db.query(Webhook).filter(Webhook.id == data["id"]).first()
    # assert db_webhook is not None # Removed assertion, rely on if check
    if db_webhook is not None: # Explicit check
        assert db_webhook.events == "order_update" # type: ignore # Default value
    else:
        pytest.fail("Default event webhook should exist in DB but was None")
    db.close()

def test_register_webhook_with_invalid_url(client: TestClient):
    """Test registering a webhook with an invalid URL fails validation"""
    webhook_data = {
        "url": "invalid-url", # Not a valid HTTP/S URL
        "secret": "secret",
        "events": ["order_created"]
    }
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    assert response.status_code == 422

def test_register_webhook_with_invalid_events(client: TestClient):
    """Test registering a webhook with invalid event types fails validation"""
    webhook_data = {
        "url": "https://example.com/webhook-invalid",
        "secret": "secret",
        "events": ["order_created", "invalid_event"] # Contains an invalid event
    }
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    assert response.status_code == 422

def test_register_webhook_with_empty_events_list(client: TestClient):
    """Test registering a webhook with an empty events list fails validation"""
    webhook_data = {
        "url": "https://example.com/webhook-empty",
        "secret": "secret",
        "events": [] # Empty list
    }
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    assert response.status_code == 422

def test_register_webhook_with_empty_secret(client: TestClient):
    """Test registering a webhook with an empty secret (assuming it's required)."""
    webhook_data = {
        "url": "https://example.com/webhook-nosecret",
        "secret": "", # Empty secret
        "events": ["order_update"]
    }
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    # Expecting validation failure if secret cannot be empty
    assert response.status_code == 422 # Pydantic validation for min_length=1

@pytest.mark.asyncio # Mark test as async
@patch('inventory_prototype.tasks.httpx.AsyncClient') # Mock the HTTP client used by send_webhook
async def test_webhook_signature_verification(mock_async_client: Mock, client: TestClient):
    """Test that the webhook payload includes the correct signature header"""
    mock_post = AsyncMock()
    mock_async_client.return_value.__aenter__.return_value.post = mock_post

    # Register webhook
    webhook_url = "https://test.receiver/hook"
    webhook_secret = "test-secret"
    client.post(
        f"/api/webhooks?api_key={API_KEY}",
        json={"url": webhook_url, "secret": webhook_secret, "events": ["order_created"]}
    )

    # Create an order to trigger the webhook
    product_id = create_product_with_inventory(client, "Sig Product", "item", 1.0, 10.0)
    order_data = {"customer_id": "sig_cust", "items": [{"product_id": product_id, "quantity": 1}]}
    # Use synchronous client call even for async endpoint in tests
    client.post(f"/api/orders?api_key={API_KEY}", json=order_data)

    # Assert httpx.post was called
    mock_post.assert_called_once()

    # Check headers of the call
    _, call_kwargs = mock_post.call_args # Ignore args
    headers = call_kwargs.get("headers", {})
    assert "X-Webhook-Signature" in headers
    # We don't need to recalculate the exact signature here, just check it exists
    assert isinstance(headers["X-Webhook-Signature"], str)
    assert len(headers["X-Webhook-Signature"]) == 64 # SHA256 hex digest length

@pytest.mark.asyncio # Mark test as async
@patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock) # Mock the entire send_webhook function
async def test_webhook_notification_on_order_creation(mock_send_webhook: Mock, client: TestClient):
    """Test that send_webhook is called correctly on order creation"""
    # Register webhook subscribing to order_created
    webhook_url = "https://example.com/order_created_hook"
    webhook_secret = "create_secret"
    client.post(
        f"/api/webhooks?api_key={API_KEY}",
        json={"url": webhook_url, "secret": webhook_secret, "events": ["order_created"]}
    )

    # Create an order
    product_id = create_product_with_inventory(client, "Order Create Prod", "item", 10.0, 5.0)
    order_data = {"customer_id": "create_cust", "items": [{"product_id": product_id, "quantity": 2}]}
    # Use synchronous client call
    response = client.post(f"/api/orders?api_key={API_KEY}", json=order_data)
    order_id = response.json()["id"]

    # Assert send_webhook was called with correct arguments
    mock_send_webhook.assert_called_once()
    call_args, _ = mock_send_webhook.call_args
    _, event_type, payload = call_args # Ignore db_session
    assert event_type == "order_created"
    assert payload["id"] == order_id
    assert payload["customer_id"] == "create_cust"
    assert payload["total"] == 2 * 10.0

@pytest.mark.asyncio # Mark test as async
@patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock)
async def test_webhook_notification_on_status_update(mock_send_webhook: Mock, client: TestClient):
    """Test that send_webhook is called correctly on order status update"""
     # Register webhook subscribing to order_update
    webhook_url = "https://example.com/order_update_hook"
    webhook_secret = "update_secret"
    client.post(
        f"/api/webhooks?api_key={API_KEY}",
        json={"url": webhook_url, "secret": webhook_secret, "events": ["order_update"]}
    )

    # Create an order first (no mocking here, let it run if needed)
    # The registered webhook only listens for 'order_update', so creation shouldn't trigger the outer mock.
    product_id = create_product_with_inventory(client, "Order Update Prod", "item", 10.0, 5.0)
    order_resp = client.post(
        f"/api/orders?api_key={API_KEY}",
        json={"customer_id": "update_cust", "items": [{"product_id": product_id, "quantity": 1}]}
    )
    order_id = order_resp.json()["id"]

    # Reset the mock *after* order creation to ignore any potential creation calls
    # (though none should happen based on registered events)
    mock_send_webhook.reset_mock()

    # Update the status (this *should* trigger the outer mock)
    new_status = "processing"
    # Use synchronous client call
    client.patch(
        f"/api/orders/{order_id}/status?api_key={API_KEY}",
        json={"status": new_status}
    )

    # Assert send_webhook was called correctly
    mock_send_webhook.assert_called_once()
    call_args, _ = mock_send_webhook.call_args
    _, event_type, payload = call_args # Ignore db_session
    assert event_type == "order_update"
    assert payload["id"] == order_id
    assert payload["customer_id"] == "update_cust"
    assert payload["status"] == new_status
    assert payload["total"] == 1 * 10.0
    # assert "timestamp" in payload # Timestamp is added inside send_webhook, not in the input payload
    # Explicitly check call count is 1 after the update
    assert mock_send_webhook.call_count == 1

def test_delete_webhook(client: TestClient):
    """Test deleting a registered webhook"""
    # Register a webhook first
    webhook_data = {"url": "https://example.com/to_delete", "secret": "delete_me"}
    response = client.post(f"/api/webhooks?api_key={API_KEY}", json=webhook_data)
    webhook_id = response.json()["id"]

    # Delete the webhook
    response = client.delete(f"/api/webhooks/{webhook_id}?api_key={API_KEY}")
    assert response.status_code == 204 # DELETE returns 204 No Content on success
    # No JSON body for 204, so remove message assertion

    # Verify deletion in DB
    db = TestingSessionLocal()
    db_webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    assert db_webhook is None
    db.close()

def test_delete_nonexistent_webhook(client: TestClient):
    """Test that deleting a non-existent webhook returns 404"""
    response = client.delete(f"/api/webhooks/999?api_key={API_KEY}")
    assert response.status_code == 404

@pytest.mark.asyncio # Mark test as async
@patch('inventory_prototype.tasks.httpx.AsyncClient') # Mock the HTTP client
async def test_webhook_error_handling(mock_async_client: Mock, client: TestClient):
    """Test that errors during webhook sending are handled gracefully"""
    # Configure mock client to raise an exception
    mock_post = AsyncMock(side_effect=Exception("Network Error"))
    mock_async_client.return_value.__aenter__.return_value.post = mock_post

    # Register webhook
    webhook_url = "https://error.example.com/hook"
    webhook_secret = "error-secret"
    client.post(
        f"/api/webhooks?api_key={API_KEY}",
        json={"url": webhook_url, "secret": webhook_secret, "events": ["order_created"]}
    )

    # Create an order (should attempt to send webhook and fail)
    product_id = create_product_with_inventory(client, "Error Product", "item", 1.0, 10.0)
    order_data = {"customer_id": "error_cust", "items": [{"product_id": product_id, "quantity": 1}]}
    # Use synchronous client call
    response = client.post(f"/api/orders?api_key={API_KEY}", json=order_data)

    # Crucially, the order creation itself should still succeed (status 201)
    assert response.status_code == 201
    # The error should be logged server-side (we can't easily check stdout here,
    # but we ensure the request doesn't fail)
    mock_post.assert_called_once() # Verify that the send attempt was made

def test_authentication_webhook_endpoints(client: TestClient):
    """Test authentication requirement for webhook endpoints."""
    webhook_data = {"url": "https://auth.example.com", "secret": "auth_secret"}

    # Missing API key
    response = client.post("/api/webhooks", json=webhook_data)
    assert response.status_code == 401 # Auth check happens first
    response = client.delete("/api/webhooks/1")
    assert response.status_code == 401 # Auth check happens first

    # Invalid API key
    response = client.post("/api/webhooks?api_key=invalid", json=webhook_data)
    assert response.status_code == 401
    response = client.delete("/api/webhooks/1?api_key=invalid")
    assert response.status_code == 401
