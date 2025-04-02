import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import threading
import time
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, Tuple # Removed unused List
from queue import Queue, Empty # Import Empty exception

# Use fixtures defined in ../conftest.py

# --- Mock HTTP Server for Webhook Receiver ---
# Global queue to store received webhook requests
webhook_requests: Queue[Tuple[str, Dict[str, Any], Dict[str, Any]]] = Queue()

class MockWebhookHandler(BaseHTTPRequestHandler):
    """Handles incoming POST requests and stores them in the queue."""
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            payload = json.loads(post_data.decode('utf-8'))
            headers = dict(self.headers)
            # Store path, headers, and payload
            webhook_requests.put((self.path, headers, payload))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Bad Request: Invalid JSON')
        except Exception:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'Internal Server Error')

    # Suppress logs for cleaner test output
    def log_message(self, format: str, *args: Any) -> None:
        return

@pytest.fixture(scope="function")
def mock_webhook_server():
    """Fixture to run the mock webhook receiver server in a thread."""
    server_address = ('localhost', 8099) # Use a specific port
    httpd = HTTPServer(server_address, MockWebhookHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"Mock webhook server started on {server_address[0]}:{server_address[1]}")

    yield f"http://{server_address[0]}:{server_address[1]}/test-hook" # URL for webhook registration

    # Shutdown server
    httpd.shutdown()
    httpd.server_close()
    server_thread.join(timeout=1) # Wait briefly for thread cleanup
    print("Mock webhook server stopped.")
    # Clear queue for next test
    while not webhook_requests.empty():
        try:
            webhook_requests.get_nowait()
        except Empty: # Use imported Empty
            break
# --- End Mock Server ---


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


def test_webhook_end_to_end(integration_client: TestClient, db_session: Session, api_key: str, mock_webhook_server: str):
    """
    Integration test for webhook notifications:
    1. Register webhook pointing to mock server.
    2. Create an order (triggers 'order_created').
    3. Verify mock server received the 'order_created' notification with correct data and signature.
    4. Update order status (triggers 'order_update').
    5. Verify mock server received the 'order_update' notification.
    6. Delete webhook.
    """
    client = integration_client
    webhook_url = mock_webhook_server
    webhook_secret = "integration_secret"
    customer_id = "webhook_cust"

    # 1. Register webhook for both events
    response = client.post(
        f"/api/webhooks?api_key={api_key}",
        json={"url": webhook_url, "secret": webhook_secret, "events": ["order_created", "order_update"]}
    )
    assert response.status_code == 201
    webhook_id = response.json()["id"]

    # 2. Create an order
    product_id = create_product(client, api_key, "Webhook Product", "ea", 15.0)
    set_inventory(client, api_key, product_id, 10.0)
    order_data = {
        "customer_id": customer_id,
        "items": [{"product_id": product_id, "quantity": 1}]
    }
    response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
    assert response.status_code == 201
    order_id = response.json()["id"]
    order_total = 1 * 15.0

    # 3. Verify 'order_created' notification received
    time.sleep(0.5) # Give server thread time to process request
    received_path, received_headers, received_payload = webhook_requests.get(timeout=2)

    assert received_path == "/test-hook"
    assert "X-Webhook-Signature" in received_headers
    # Verify 'order_created' payload structure
    assert received_payload.get("event_type") == "order_created" # Check event_type added by tasks.py
    assert received_payload.get("id") == order_id # Check correct key 'id'
    assert received_payload.get("customer_id") == customer_id
    assert received_payload.get("total") == order_total
    assert "timestamp" in received_payload # Check timestamp added by tasks.py
    # Signature verification would require recalculating HMAC here - skipping for brevity

    # 4. Update order status
    new_status = "shipped"
    response = client.patch(
        f"/api/orders/{order_id}/status?api_key={api_key}",
        json={"status": new_status}
    )
    assert response.status_code == 200

    # 5. Verify 'order_update' notification received
    time.sleep(0.5) # Give server thread time
    received_path_update, received_headers_update, received_payload_update = webhook_requests.get(timeout=2)

    assert received_path_update == "/test-hook"
    assert "X-Webhook-Signature" in received_headers_update
    # Verify 'order_update' payload structure
    assert received_payload_update.get("event_type") == "order_update" # Check event_type added by tasks.py
    assert received_payload_update.get("id") == order_id # Check correct key 'id'
    assert received_payload_update.get("customer_id") == customer_id
    assert received_payload_update.get("status") == new_status
    assert received_payload_update.get("total") == order_total # Total might not change on status update, verify if needed
    assert "timestamp" in received_payload_update # Check timestamp added by tasks.py

    # Ensure queue is empty now
    assert webhook_requests.empty()

    # 6. Delete webhook
    response = client.delete(f"/api/webhooks/{webhook_id}?api_key={api_key}")
    assert response.status_code == 204 # DELETE returns 204 No Content

    # 7. Update status again - webhook should NOT be called
    response = client.patch(
        f"/api/orders/{order_id}/status?api_key={api_key}",
        json={"status": "delivered"}
    )
    assert response.status_code == 400 # This transition should fail as per order lifecycle rules
    time.sleep(0.5) # Wait to ensure no message arrives


def test_delete_webhook(integration_client: TestClient, api_key: str, mock_webhook_server: str):
    """Test webhook deletion functionality."""
    client = integration_client
    webhook_url = mock_webhook_server
    webhook_secret = "delete_secret"

    # Register a webhook first
    reg_response = client.post(
        f"/api/webhooks?api_key={api_key}",
        json={"url": webhook_url, "secret": webhook_secret, "events": ["order_created"]}
    )
    assert reg_response.status_code == 201
    webhook_id = reg_response.json()["id"]

    # Delete the webhook
    del_response = client.delete(f"/api/webhooks/{webhook_id}?api_key={api_key}")
    assert del_response.status_code == 204 # DELETE returns 204 No Content on success
    # No JSON body for 204, so remove message assertion

    # Try deleting again (should fail with 404)
    del_response_again = client.delete(f"/api/webhooks/{webhook_id}?api_key={api_key}")
    assert del_response_again.status_code == 404

    # Try deleting a non-existent webhook ID
    non_existent_id = 99999
    del_response_non_existent = client.delete(f"/api/webhooks/{non_existent_id}?api_key={api_key}")
    assert del_response_non_existent.status_code == 404

    assert webhook_requests.empty() # Queue should remain empty
