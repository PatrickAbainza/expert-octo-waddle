import httpx
import os
import time
import json
import io # Added for CSV upload simulation
from typing import Dict, Any, Optional # Removed List

# --- Configuration ---
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY", "prototype_key_change_me")
# --- End Configuration ---

def make_request(
    client: httpx.Client,
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None, # Added files parameter
) -> Optional[Any]: # Return type can be dict, list, or str (for CSV)
    """Helper function to make API requests and handle basic errors."""
    if params is None:
        params = {}
    # Ensure api_key is always included, even if params is initially None
    params["api_key"] = API_KEY

    print(f"\n> {method.upper()} {BASE_URL}{endpoint}")
    # Filter out api_key for cleaner logging
    log_params = {k: v for k, v in params.items() if k != 'api_key'}
    if log_params:
        print(f"  Params: {log_params}")
    if json_data:
        print(f"  Payload: {json.dumps(json_data)}")
    if files:
        # Don't print file content, just indicate files are being sent
        print(f"  Files: {list(files.keys())}")

    try:
        response = client.request(
            method,
            f"{BASE_URL}{endpoint}",
            params=params,
            json=json_data,
            files=files, # Pass files if provided
            timeout=10.0
        )
        response.raise_for_status() # Raise exception for 4xx/5xx errors
        print(f"< {response.status_code} {response.reason_phrase}")

        if response.content:
            # Try to decode JSON, otherwise return text (for CSV)
            try:
                result = response.json()
                # Truncate long list responses for cleaner output
                if isinstance(result, list) and len(result) > 3:
                     print(f"  Response (truncated): {json.dumps(result[:3])} ... ({len(result)} items total)")
                else:
                     print(f"  Response: {json.dumps(result)}")
                return result
            except json.JSONDecodeError:
                print(f"  Response: (Non-JSON, likely CSV or text)")
                # Limit printing large CSVs
                content_preview = response.text[:200] + ('...' if len(response.text) > 200 else '')
                print(f"  Content Preview: {content_preview}")
                return response.text # Return raw text for CSV
        else:
            print("  Response: (No Content)")
            return None
    except httpx.RequestError as exc:
        print(f"[ERROR] Request failed: {exc}")
        return None
    except httpx.HTTPStatusError as exc:
        print(f"[ERROR] HTTP Error: {exc.response.status_code} {exc.response.reason_phrase}")
        try:
            # Try to parse error detail as JSON
            error_detail = exc.response.json()
            print(f"  Error Detail: {json.dumps(error_detail)}")
            return error_detail # Return parsed error detail
        except json.JSONDecodeError:
            # If error detail is not JSON, print raw text
            print(f"  Error Detail: {exc.response.text}")
            return exc.response.text # Return raw error text


def run_simulation():
    """Runs the Inventory Check simulation."""
    existing_product_id: Optional[int] = None

    with httpx.Client() as client:
        print("--- Starting Inventory Check Simulation ---")

        # 1. List All Inventory (to find an existing product if possible)
        print("\n--- Step 1: List All Inventory ---")
        inventory_list = make_request(client, "GET", "/api/inventory")
        if isinstance(inventory_list, list) and inventory_list:
            # Try to use the first product found in the inventory list
            existing_product_id = inventory_list[0].get("product_id")
            print(f"[INFO] Found existing product in inventory with ID: {existing_product_id}")
        else:
            print("[INFO] Inventory list is empty or failed to retrieve. Attempting to create a product.")
            # Create a product if none found
            prod_data = {"name": "InvCheck Product", "unit": "item", "price_per_unit": 5.0}


        # 6. Download Inventory CSV
        print("\n--- Step 6: Download Inventory as CSV ---")
        csv_download_result = make_request(client, "GET", "/api/inventory/download")
        if isinstance(csv_download_result, str):
            print("[INFO] CSV Download successful (content preview shown above).")
        else:
            print("[WARN] CSV Download did not return expected string content.")

        # 7. Upload Inventory CSV
        print("\n--- Step 7: Upload Inventory via CSV ---")
        if existing_product_id:
            new_quantity = 99.5
            print(f"[INFO] Preparing CSV to update product ID {existing_product_id} to quantity {new_quantity}")
            csv_upload_data = (
                "product_id,quantity\n"
                f"{existing_product_id},{new_quantity}\n"
            )
            csv_file_obj = io.BytesIO(csv_upload_data.encode('utf-8'))
            upload_files = {'file': ('sim_upload.csv', csv_file_obj, 'text/csv')}
            upload_summary = make_request(client, "POST", "/api/inventory/upload", files=upload_files)
            if upload_summary:
                print("[INFO] CSV Upload request sent. Summary received (printed above).")
            else:
                print("[WARN] CSV Upload request failed or returned no summary.")

            # 8. Verify Upload by checking specific inventory again
            print(f"\n--- Step 8: Verify Inventory Update (ID: {existing_product_id}) ---")
            make_request(client, "GET", f"/api/inventory/{existing_product_id}")
        else:
            print("[SKIP] Skipping CSV Upload/Verification as no product ID was available.")

            created = make_request(client, "POST", "/api/products", json_data=prod_data)
            if created and isinstance(created, dict) and "id" in created:
                existing_product_id = created["id"]
                print(f"[INFO] Created product with ID: {existing_product_id}")
                # Set some inventory for it
                make_request(client, "PATCH", f"/api/inventory/{existing_product_id}", json_data={"quantity": 25})
            else:
                print("[FATAL] Failed to find or create a product for inventory checks. Aborting.")
                return

        # 2. Get Specific Inventory (Existing Product)
        print(f"\n--- Step 2: Get Specific Inventory (ID: {existing_product_id}) ---")
        make_request(client, "GET", f"/api/inventory/{existing_product_id}")

        # 3. Check Inventory Status (Existing Product)
        print(f"\n--- Step 3: Check Inventory Status (ID: {existing_product_id}) ---")
        make_request(client, "GET", f"/api/inventory/status/{existing_product_id}")

        # 4. Get Specific Inventory (Non-existent Product)
        non_existent_id = 999999
        print(f"\n--- Step 4: Get Specific Inventory (Non-existent ID: {non_existent_id}) ---")
        make_request(client, "GET", f"/api/inventory/{non_existent_id}") # Expect 404

        # 5. Check Inventory Status (Non-existent Product)
        print(f"\n--- Step 5: Check Inventory Status (Non-existent ID: {non_existent_id}) ---")
        make_request(client, "GET", f"/api/inventory/status/{non_existent_id}") # Expect 404

        print("\n--- Inventory Check Simulation Complete ---")

if __name__ == "__main__":
    print("Ensure the FastAPI server (uvicorn inventory_prototype.main:app --reload) is running.") # Updated comment
    print(f"Targeting API Base URL: {BASE_URL}")
    print(f"Using API Key: {'*' * (len(API_KEY) - 4)}{API_KEY[-4:]}" if len(API_KEY) > 4 else "(Key too short to mask)")
    time.sleep(1)
    run_simulation()