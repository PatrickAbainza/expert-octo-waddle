import httpx
import os
import time
import json
from typing import Dict, Any, Optional

# --- Configuration ---
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "prototype_key_change_me")
CUSTOMER_ID_ORDERS = "sim_customer_orders"
# --- End Configuration ---

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
            # Truncate long list responses for cleaner output
            if isinstance(result, list) and len(result) > 3:
                 print(f"  Response (truncated): {json.dumps(result[:3])} ... ({len(result)} items total)")
            else:
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
    """Runs the Order Endpoints simulation."""
    product_id: Optional[int] = None
    product_id_b: Optional[int] = None
    order_id: Optional[int] = None
    quick_order_id: Optional[int] = None

    with httpx.Client() as client:
        print("--- Starting Order Endpoints Simulation ---")

        # 1. Create Products and Set Inventory (Prerequisites)
        print("\n--- Step 1: Create Products & Set Inventory ---")
        prod_data = {"name": "OrderSim Product A", "unit": "pack", "price_per_unit": 9.95}
        prod_data_b = {"name": "OrderSim Product B", "unit": "item", "price_per_unit": 24.50}

        created_product = make_request(client, "POST", "/api/products", json_data=prod_data)
        if created_product and isinstance(created_product, dict) and "id" in created_product:
            product_id = created_product["id"]
            print(f"[INFO] Product A created with ID: {product_id}")
            # Set inventory for Product A
            make_request(client, "PATCH", f"/api/inventory/{product_id}", json_data={"quantity": 100})

            # Create second product (Product B)
            created_product_b = make_request(client, "POST", "/api/products", json_data=prod_data_b)
            if created_product_b and isinstance(created_product_b, dict) and "id" in created_product_b:
                product_id_b = created_product_b["id"]
                print(f"[INFO] Product B created with ID: {product_id_b}")
                # Set inventory for Product B
                make_request(client, "PATCH", f"/api/inventory/{product_id_b}", json_data={"quantity": 50})
            else:
                print("[WARN] Failed to create second product (Product B). Modification step will fail.")
        else:
            print("[FATAL] Failed to create prerequisite product (Product A). Aborting simulation.")
            return # Cannot proceed without Product A

        # 2. Create an Initial Order (using Product A)
        print("\n--- Step 2: Create Initial Order ---")
        if not product_id:
             print("[ERROR] Cannot create order, Product A ID is missing.")
        else:
            order_data = {
                "customer_id": CUSTOMER_ID_ORDERS,
                "items": [{"product_id": product_id, "quantity": 5}]
            }
            created_order = make_request(client, "POST", "/api/orders", json_data=order_data)
            if created_order and isinstance(created_order, dict) and "id" in created_order:
                order_id = created_order["id"]
                print(f"[INFO] Initial order created with ID: {order_id}")
            else:
                print("[ERROR] Failed to create initial order. Some steps might fail.")
                # Continue if possible

        # 3. Get Specific Order (Initial State)
        if order_id:
            print(f"\n--- Step 3: Get Specific Order (Initial State - ID: {order_id}) ---")
            make_request(client, "GET", f"/api/orders/{order_id}")
        else:
            print("\n--- Step 3: Get Specific Order (Skipped - No Order ID) ---")

        # 4. Modify Order Items (Change to Product B)
        if order_id and product_id_b:
            print(f"\n--- Step 4: Modify Order Items (ID: {order_id}) ---")
            modify_data = {"items": [{"product_id": product_id_b, "quantity": 2}]} # Change to 2 of Product B
            make_request(client, "PUT", f"/api/orders/{order_id}/items", json_data=modify_data)
        else:
            print("\n--- Step 4: Modify Order Items (Skipped - Missing Order ID or Product B ID) ---")

        # 5. Verify Modification (Get Order and Inventory)
        if order_id and product_id and product_id_b:
            print(f"\n--- Step 5: Verify Modification (Order ID: {order_id}) ---")
            print("  Getting modified order details...")
            make_request(client, "GET", f"/api/orders/{order_id}")
            print("  Getting inventory for original product (A)...")
            make_request(client, "GET", f"/api/inventory/{product_id}") # Should be restored
            print("  Getting inventory for new product (B)...")
            make_request(client, "GET", f"/api/inventory/{product_id_b}") # Should be deducted
        else:
            print("\n--- Step 5: Verify Modification (Skipped) ---")

        # 6. List Orders (Unfiltered)
        print("\n--- Step 6: List Orders (Unfiltered) ---")
        make_request(client, "GET", "/api/orders", params={"limit": 5}) # Limit for brevity

        # 7. List Orders (Filtered by Customer)
        print(f"\n--- Step 7: List Orders (Filtered by Customer: {CUSTOMER_ID_ORDERS}) ---")
        make_request(client, "GET", "/api/orders", params={"customer_id": CUSTOMER_ID_ORDERS})

        # 8. Place Quick Order (using Product A)
        print("\n--- Step 8: Place Quick Order ---")
        if not product_id:
             print("[ERROR] Cannot place quick order, Product A ID is missing.")
        else:
            quick_order_params = {
                "customer_id": CUSTOMER_ID_ORDERS,
                "product_id": product_id,
                "quantity": 3
            }
            created_quick_order = make_request(client, "POST", "/api/orders/quick", params=quick_order_params)
            if created_quick_order and isinstance(created_quick_order, dict) and "id" in created_quick_order:
                quick_order_id = created_quick_order["id"]
                print(f"[INFO] Quick order created with ID: {quick_order_id}")
            else:
                print("[ERROR] Failed to create quick order. Cancellation step will fail.")

        # 9. Cancel Quick Order
        if quick_order_id:
            print(f"\n--- Step 9: Cancel Quick Order (ID: {quick_order_id}) ---")
            make_request(client, "POST", f"/api/orders/{quick_order_id}/cancel")
        else:
            print("\n--- Step 9: Cancel Quick Order (Skipped - No Quick Order ID) ---")

        # 10. Verify Cancellation (Get Order and Inventory)
        if quick_order_id and product_id:
            print(f"\n--- Step 10: Verify Cancellation (Order ID: {quick_order_id}) ---")
            print("  Getting cancelled order details...")
            make_request(client, "GET", f"/api/orders/{quick_order_id}")
            print("  Getting inventory for cancelled product (A)...")
            make_request(client, "GET", f"/api/inventory/{product_id}") # Should be restored
        else:
            print("\n--- Step 10: Verify Cancellation (Skipped) ---")

        # 11. List Orders Again (Filtered - check final state)
        print(f"\n--- Step 11: List Orders Again (Filtered by Customer: {CUSTOMER_ID_ORDERS}) ---")
        make_request(client, "GET", "/api/orders", params={"customer_id": CUSTOMER_ID_ORDERS})


        print("\n--- Order Endpoints Simulation Complete ---")

if __name__ == "__main__":
    print("Ensure the FastAPI server (uvicorn inventory_prototype.main:app --reload) is running.") # Updated comment
    print(f"Targeting API Base URL: {BASE_URL}")
    print(f"Using API Key: {'*' * (len(API_KEY) - 4)}{API_KEY[-4:]}" if len(API_KEY) > 4 else "(Key too short to mask)")
    time.sleep(1)
    run_simulation()