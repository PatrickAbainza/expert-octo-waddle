import httpx
import os
import time
import json
from typing import Dict, Any, Optional, List

# --- Configuration ---
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "prototype_key_change_me")
# --- End Configuration ---

# Store created product IDs
product_ids: List[int] = []

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
        return None

def run_simulation():
    """Runs the Product List/Search/Update simulation."""
    global product_ids

    with httpx.Client() as client:
        print("--- Starting Product List/Search/Update Simulation ---")

        # 1. Create Multiple Products
        print("\n--- Step 1: Create Multiple Products ---")
        products_to_create = [
            {"name": "Simulation Apple", "unit": "kg", "price_per_unit": 2.50, "description": "Fresh red apples"},
            {"name": "Simulation Banana", "unit": "kg", "price_per_unit": 1.80},
            {"name": "Simulation Carrot", "unit": "kg", "price_per_unit": 1.20, "description": "Organic carrots"},
            {"name": "Simulation Durian", "unit": "piece", "price_per_unit": 15.00, "description": "Smelly but tasty"},
        ]
        for prod_data in products_to_create:
             created = make_request(client, "POST", "/api/products", json_data=prod_data)
             if created and isinstance(created, dict) and "id" in created:
                  product_ids.append(created["id"])
        if len(product_ids) != len(products_to_create):
             print("[WARN] Not all products may have been created successfully.")
        else:
             print(f"[INFO] Created product IDs: {product_ids}")

        if not product_ids:
             print("[FATAL] No products created. Aborting simulation.")
             return

        # 2. List Products (Default Pagination)
        print("\n--- Step 2: List Products (Default) ---")
        make_request(client, "GET", "/api/products")

        # 3. List Products (Custom Pagination)
        print("\n--- Step 3: List Products (Skip=1, Limit=2) ---")
        make_request(client, "GET", "/api/products", params={"skip": 1, "limit": 2})

        # 4. Search Products
        print("\n--- Step 4: Search Products (query='Carrot') ---")
        make_request(client, "GET", "/api/products/search/", params={"query": "Carrot"})

        # 5. Get Specific Product
        target_id = product_ids[0]
        print(f"\n--- Step 5: Get Specific Product (ID: {target_id}) ---")
        make_request(client, "GET", f"/api/products/{target_id}")

        # 6. Update Product
        target_id_update = product_ids[1] # Update Banana
        print(f"\n--- Step 6: Update Product (ID: {target_id_update}) ---")
        update_data = {"description": "Ripe Cavendish Bananas", "price_per_unit": 1.95}
        make_request(client, "PATCH", f"/api/products/{target_id_update}", json_data=update_data)
        # Verify update
        print(f"--- Verifying Update for Product ID: {target_id_update} ---")
        make_request(client, "GET", f"/api/products/{target_id_update}")

        # 7. Get Featured Products
        print("\n--- Step 7: Get Featured Products ---")
        # Need to set some inventory first for the featured logic (highest inventory)
        print("--- Setting some inventory for featured products ---")
        if len(product_ids) >= 2:
             make_request(client, "PATCH", f"/api/inventory/{product_ids[0]}", json_data={"quantity": 100}) # Apple
             make_request(client, "PATCH", f"/api/inventory/{product_ids[2]}", json_data={"quantity": 150}) # Carrot
        # Call without limit parameter to use default
        make_request(client, "GET", "/api/products/featured")


        print("\n--- Product List/Search/Update Simulation Complete ---")

if __name__ == "__main__":
    print("Ensure the FastAPI server (uvicorn inventory_prototype.main:app --reload) is running.") # Updated comment
    print(f"Targeting API Base URL: {BASE_URL}")
    print(f"Using API Key: {'*' * (len(API_KEY) - 4)}{API_KEY[-4:]}" if len(API_KEY) > 4 else "(Key too short to mask)")
    time.sleep(1)
    run_simulation()