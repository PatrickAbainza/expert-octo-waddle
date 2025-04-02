import httpx
import os
import time
import json
import hmac
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from queue import Queue
from typing import Dict, Any, Optional, Tuple
from threading import Thread

# --- Configuration ---
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "prototype_key_change_me")
WEBHOOK_PORT = 8099  # Use a different port than the main API
WEBHOOK_URL = f"http://localhost:{WEBHOOK_PORT}/webhook"
WEBHOOK_SECRET = "sim_secret_123"

# Queue to store received webhook requests
webhook_requests: Queue[Tuple[Dict[str, Any], Dict[str, Any]]] = Queue()

# Mock Webhook Server
class MockWebhookHandler(BaseHTTPRequestHandler):
    """Handles incoming webhook POST requests."""
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode('utf-8'))
            headers = dict(self.headers)

            # Ignore ping requests used for verification
            if payload == {"test": "ping"}:
                print("[WEBHOOK] Received ping request.")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'PONG')
                return # Don't process ping as a real webhook

            # Verify signature
            signature = headers.get('X-Webhook-Signature')
            if not signature:
                print("[WEBHOOK] Warning: No signature in webhook request")
            else:
                # Calculate expected signature
                payload_json = json.dumps(payload, sort_keys=True)
                expected_signature = hmac.new(
                    WEBHOOK_SECRET.encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()

                if signature == expected_signature:
                    print("[WEBHOOK] Signature verified ✓")
                else:
                    print("[WEBHOOK] Warning: Signature verification failed!")
                    print(f"Expected: {expected_signature}")
                    print(f"Received: {signature}")

            # Store headers and payload
            webhook_requests.put((headers, payload))
            print(f"\n[WEBHOOK] Received notification:")
            print(f"Headers: {json.dumps({k:v for k,v in headers.items() if k != 'X-Webhook-Signature'}, indent=2)}")
            print(f"Payload: {json.dumps(payload, indent=2)}")

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        except Exception as e:
            print(f"[WEBHOOK] Error processing request: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass # Correctly indented pass

# Removed cleanup_old_webhooks function as GET /api/webhooks is not supported

def verify_mock_server(url: str, timeout: float = 2.0) -> bool:
    """Verify the mock server is running and responding."""
    try:
        with httpx.Client() as client:
            response = client.post(url, json={"test": "ping"}, timeout=timeout)
            return response.status_code == 200
    except Exception:
        return False

# Function to start webhook server
def start_webhook_server() -> HTTPServer:
    """Start the mock webhook server and verify it's running."""
    server = HTTPServer(('localhost', WEBHOOK_PORT), MockWebhookHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Wait for server to start and verify it's responding
    max_attempts = 3
    for attempt in range(max_attempts):
        print(f"Verifying mock server (attempt {attempt + 1}/{max_attempts})...")
        if verify_mock_server(WEBHOOK_URL):
            print("Mock server verified.")
            return server
        time.sleep(1)
    raise RuntimeError("Failed to start or verify mock webhook server")

def make_request(
    client: httpx.Client,
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Optional[Any]: # Return type can be dict or list
    """Helper function to make API requests and handle basic errors."""
    if params is None:
        params = {}
    # Ensure api_key is always included, even if params is initially None
    params["api_key"] = API_KEY

    print(f"\n> {method.upper()} {BASE_URL}{endpoint}")
    if params and len(params) > 1: # Don't print if only api_key
         print(f"  Params: { {k:v for k,v in params.items() if k != 'api_key'} }")
    if json_data:
        print(f"  Payload: {json.dumps(json_data)}")

    try:
        response = client.request(method, f"{BASE_URL}{endpoint}", params=params, json=json_data, timeout=10.0)
        response.raise_for_status() # Raise exception for 4xx/5xx errors
        print(f"< {response.status_code} {response.reason_phrase}")
        if response.content:
            result = response.json()
            print(f"  Response: {json.dumps(result)}")
            return result
        else:
            print("  Response: (No Content)")
            return None
    except httpx.RequestError as exc:
        print(f"[ERROR] Request failed: {exc}")
        return None
    except httpx.HTTPStatusError as exc:
        print(f"[ERROR] HTTP Error: {exc.response.status_code} {exc.response.reason_phrase}")
        try:
            print(f"  Error Detail: {exc.response.json()}")
        except json.JSONDecodeError:
            print(f"  Error Detail: (Non-JSON response)")
        # Return the error response content if available, for checking 404s etc.
        return exc.response.json() if exc.response.content else None


def run_simulation():
    """Runs the Webhook Management simulation with a mock webhook server."""
    webhook_id: Optional[int] = None
    product_id: Optional[int] = None
    order_id: Optional[int] = None

    # Start mock webhook server
    print("\n--- Starting Mock Webhook Server ---")
    server = start_webhook_server()
    print(f"Mock webhook server listening on {WEBHOOK_URL}")
    time.sleep(1)  # Give server time to start

    try:
        with httpx.Client() as client:
            # Removed cleanup_old_webhooks call as the function was removed

            print("--- Starting Webhook Management Simulation ---")

            # 1. Register Webhook for both events
            print("\n--- Step 1: Register Webhook ---")
            webhook_data = {
                "url": WEBHOOK_URL,
                "secret": WEBHOOK_SECRET,
                "events": ["order_created", "order_update"]
            }
            registered_webhook = make_request(client, "POST", "/api/webhooks", json_data=webhook_data)
            if registered_webhook and isinstance(registered_webhook, dict) and "id" in registered_webhook:
                webhook_id = registered_webhook["id"]
                print(f"[INFO] Webhook registered with ID: {webhook_id}")
            else:
                print("[FATAL] Failed to register webhook. Aborting simulation.")
                return

            # 2. Create a product (for order test)
            print("\n--- Step 2: Create Test Product ---")
            product_data = {
                "name": "Webhook Test Product",
                "unit": "piece",
                "price_per_unit": 10.0
            }
            created_product = make_request(client, "POST", "/api/products", json_data=product_data)
            if created_product and isinstance(created_product, dict):
                product_id = created_product["id"]
                # Set inventory
                make_request(client, "PATCH", f"/api/inventory/{product_id}", json_data={"quantity": 5.0})

            # 3. Create an order (should trigger order_created webhook)
            print("\n--- Step 3: Create Order (Triggers order_created) ---")
            order_data = {
                "customer_id": "webhook_test_customer",
                "items": [{"product_id": product_id, "quantity": 1.0}]
            }
            created_order = make_request(client, "POST", "/api/orders", json_data=order_data)
            if created_order and isinstance(created_order, dict):
                order_id = created_order["id"]
                print("[INFO] Waiting for order_created webhook (increased wait)...")
                time.sleep(3) # Further increased wait time

                # Process all webhooks received after creation
                received_creation_webhook = False
                while not webhook_requests.empty():
                    headers, payload = webhook_requests.get()
                    received_creation_webhook = True
                    signature = headers.get('X-Webhook-Signature', '')
                    print(f"\n[WEBHOOK] Received notification (after creation):")
                    print(f"Event Type: {payload.get('event_type')}")
                    print(f"Order Status: {payload.get('status')}")
                    print(f"Timestamp: {payload.get('timestamp')}")
                    # Verify signature
                    payload_json = json.dumps(payload, sort_keys=True)
                    expected_signature = hmac.new(
                        WEBHOOK_SECRET.encode(),
                        payload_json.encode(),
                        hashlib.sha256
                    ).hexdigest()
                    print(f"Signature Match: {signature == expected_signature}")
                if not received_creation_webhook:
                     print("[WARNING] No webhook received for order creation")


            # 4. Update order status through valid transitions (should trigger order_update webhooks)
            if order_id:
                print("\n--- Step 4: Update Order Status (Triggers order_update) ---")
                status_transitions = ["processing", "shipped", "completed"]
                for new_status in status_transitions:
                    print(f"\n--- Updating status to: {new_status} ---")
                    make_request(client, "PATCH", f"/api/orders/{order_id}/status", json_data={"status": new_status})
                    print("[INFO] Waiting for order_update webhook (increased wait)...")
                    time.sleep(3) # Further increased wait time

                    # Check for webhook(s) received after this update
                    received_update_webhook = False
                    while not webhook_requests.empty():
                        headers, payload = webhook_requests.get()
                        received_update_webhook = True
                        signature = headers.get('X-Webhook-Signature', '')
                        print(f"\n[WEBHOOK] Received notification (after {new_status}):")
                        print(f"Event Type: {payload.get('event_type')}")
                        print(f"Order Status: {payload.get('status')}")
                        print(f"Timestamp: {payload.get('timestamp')}")

                        # Verify signature
                        payload_json = json.dumps(payload, sort_keys=True)
                        expected_signature = hmac.new(
                            WEBHOOK_SECRET.encode(),
                            payload_json.encode(),
                            hashlib.sha256
                        ).hexdigest()
                        print(f"Signature Match: {signature == expected_signature}")

                    if not received_update_webhook:
                        print(f"[WARNING] No webhook received for status update to {new_status}")

            # 5. Delete Webhook
            print(f"\n--- Step 5: Delete Webhook (ID: {webhook_id}) ---")
            make_request(client, "DELETE", f"/api/webhooks/{webhook_id}")

            # 6. Verify webhook is deleted by attempting another status update
            if order_id:
                print("\n--- Step 6: Verify No More Webhooks ---")
                make_request(client, "PATCH", f"/api/orders/{order_id}/status", json_data={"status": "cancelled"})
                print("[INFO] Waiting to verify no webhook is received (increased wait)...")
                time.sleep(3) # Further increased wait time
                # Acknowledge potential race condition: a webhook might still arrive if sent just before deletion
                if not webhook_requests.empty():
                    print("[WARNING] Still receiving webhooks after deletion (potential race condition)!")
                    while not webhook_requests.empty():
                        _, payload = webhook_requests.get()
                        print(f"Unexpected webhook: {payload}")
                else:
                    print("[INFO] No webhooks received after deletion (correct)")

            print("\n--- Webhook Management Simulation Complete ---")

    finally:
        # Stop the webhook server
        print("\n--- Stopping Mock Webhook Server ---")
        server.shutdown()
        server.server_close()

if __name__ == "__main__":
    print("Ensure the FastAPI server (uvicorn inventory_prototype.main:app --reload) is running.") # Updated comment
    print(f"Targeting API Base URL: {BASE_URL}")
    print(f"Using API Key: {'*' * (len(API_KEY) - 4)}{API_KEY[-4:]}" if len(API_KEY) > 4 else "(Key too short to mask)")
    time.sleep(1)
    run_simulation()