import httpx
import os
import time
import json
from typing import Dict, Any, Optional, Union, TypeAlias

# Type alias for API responses
JsonResponse: TypeAlias = Union[Dict[str, Any], list[Any]]

# --- Configuration ---
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "prototype_key_change_me")
CUSTOMER_ID = "sim_customer_001"
PRODUCT_NAME = "Simulated Widget"
PRODUCT_UNIT = "piece"
INITIAL_PRICE = 19.99
INITIAL_QUANTITY = 50.0
ORDER_QUANTITY = 10.0
# --- End Configuration ---

def make_request(
    client: httpx.Client,
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any] | list[Any]]:
    """Helper function to make API requests and handle basic errors. Returns dict or list depending on endpoint."""
    if params is None:
        params = {}
    params["api_key"] = API_KEY # Add API key to all requests

    print(f"\n> {method.upper()} {BASE_URL}{endpoint}")
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
        return None

def run_simulation():
    """Runs the API workflow simulation."""
    product_id: Optional[int] = None
    order_id: Optional[int] = None

    with httpx.Client() as client:
        print("--- Starting API Workflow Simulation ---")

        # 1. Create Product
        print("\n--- Step 1: Create Product ---")
        product_data = {
            "name": PRODUCT_NAME,
            "unit": PRODUCT_UNIT,
            "price_per_unit": INITIAL_PRICE,
            "description": "A widget created by the simulation script."
        }
        created_product = make_request(client, "POST", "/api/products", json_data=product_data)
        if isinstance(created_product, dict) and "id" in created_product:
            product_id = created_product["id"]
            print(f"[INFO] Product created with ID: {product_id}")
        else:
            print("[FATAL] Failed to create product. Aborting simulation.")
            return

        # 2. Set Inventory
        print("\n--- Step 2: Set Inventory ---")
        inventory_data = {"quantity": INITIAL_QUANTITY}
        make_request(client, "PATCH", f"/api/inventory/{product_id}", json_data=inventory_data)

        # 3. Check Inventory Status (Initial)
        print("\n--- Step 3: Check Inventory Status (Initial) ---")
        make_request(client, "GET", f"/api/inventory/status/{product_id}")

        # 4. Create Order
        print("\n--- Step 4: Create Order ---")
        order_data = {
            "customer_id": CUSTOMER_ID,
            "items": [{"product_id": product_id, "quantity": ORDER_QUANTITY}]
        }
        created_order = make_request(client, "POST", "/api/orders", json_data=order_data)
        if isinstance(created_order, dict) and "id" in created_order:
            order_id = created_order["id"]
            print(f"[INFO] Order created with ID: {order_id}")
        else:
            print("[ERROR] Failed to create order.")
            # Continue simulation if possible

        # 5. Check Inventory Status (After Order)
        print("\n--- Step 5: Check Inventory Status (After Order) ---")
        make_request(client, "GET", f"/api/inventory/status/{product_id}")

        # 6. Update Order Status
        if order_id:
            print("\n--- Step 6: Update Order Status ---")
            status_data = {"status": "shipped"}
            make_request(client, "PATCH", f"/api/orders/{order_id}/status", json_data=status_data)
        else:
            print("\n--- Step 6: Update Order Status (Skipped - No Order ID) ---")


        # 7. Get Customer History (Returns a list of orders)
        print("\n--- Step 7: Get Customer History ---")
        make_request(client, "GET", "/api/orders", params={"customer_id": CUSTOMER_ID})



        # 8. Delete Product
        if product_id:
            print("\n--- Step 8: Delete Product ---")
            make_request(client, "DELETE", f"/api/products/{product_id}")
        else:
            print("\n--- Step 8: Delete Product (Skipped - No Product ID) ---")

        # 9. Verify Product Deletion
        if product_id:
            print("\n--- Step 9: Verify Product Deletion ---")
            make_request(client, "GET", f"/api/products/{product_id}") # Expect 404
        else:
            print("\n--- Step 9: Verify Product Deletion (Skipped - No Product ID) ---")

        print("\n--- Simulation Complete ---")

if __name__ == "__main__":
    print("Ensure the FastAPI server (uvicorn inventory_prototype.main:app --reload) is running.") # Updated comment
    print(f"Targeting API Base URL: {BASE_URL}")
    print(f"Using API Key: {'*' * (len(API_KEY) - 4)}{API_KEY[-4:]}" if len(API_KEY) > 4 else "(Key too short to mask)")
    time.sleep(2) # Brief pause before starting
    run_simulation()