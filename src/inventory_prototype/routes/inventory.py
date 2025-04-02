import io # Added for CSV generation
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File # Added UploadFile and File
from fastapi.responses import StreamingResponse # Added for CSV download
from sqlalchemy.orm import Session
from typing import List, Dict, Any # Added Dict, Any for status endpoint

# Import local modules
from .. import crud, schemas # Removed models import
from ..crud import get_all_products_with_inventory, bulk_update_inventory # Added for CSV download & upload
from ..services.csv_service import generate_inventory_csv, parse_inventory_csv, CSVUploadResponse, CSVUploadError # Added for CSV download & upload
from ..database import get_db
from ..dependencies import verify_api_key

router = APIRouter(
    prefix="/api/inventory",
    tags=["Inventory"],
    dependencies=[Depends(verify_api_key)] # Apply API key verification
) # Added closing parenthesis

@router.patch("/{product_id}", response_model=schemas.InventoryResponse)
def update_inventory_endpoint(
    product_id: int,
    update: schemas.InventoryUpdate,
    db: Session = Depends(get_db)
):
    """
    Set the inventory quantity for a specific product.
    Creates an inventory record if one doesn't exist for a valid product.
    """
    # crud.update_inventory_quantity handles checking if product exists
    inventory = crud.update_inventory_quantity(db, product_id=product_id, quantity=update.quantity)
    if inventory is None:
        # This happens if the product itself doesn't exist
        raise HTTPException(status_code=404, detail="Product not found, cannot update inventory")
    return inventory

@router.get("/status/{product_id}", response_model=Dict[str, Any]) # Custom response
def get_inventory_status_endpoint(
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the inventory status (in_stock, low_stock, out_of_stock) and quantity for a product.
    """
    inventory = crud.get_inventory(db, product_id=product_id)
    if inventory is None:
         # Check if product exists at all before returning out_of_stock
         product = crud.get_product(db, product_id=product_id)
         if product is None:
             raise HTTPException(status_code=404, detail="Product not found")
         # Product exists, but no inventory record yet
         return {"status": "out_of_stock", "quantity": 0}

    # Determine status based on quantity
    quantity = inventory.quantity
    if quantity <= 0:
        status = "out_of_stock"
    elif quantity < 10: # Assuming low stock threshold is 10 (as per original code)
        status = "low_stock"
    else:
        status = "in_stock"

    return {"status": status, "quantity": quantity}

@router.get("", response_model=List[schemas.InventoryResponse])
def list_inventory_endpoint(
    db: Session = Depends(get_db)
):
    """
    List all inventory items.
    """
    inventory_items = crud.list_all_inventory(db)
    return inventory_items

# IMPORTANT: Define specific paths like /download BEFORE paths with parameters like /{product_id}
@router.get("/download", response_class=StreamingResponse)
def download_inventory_csv_endpoint(
    db: Session = Depends(get_db)
):
    """
    Download the current inventory status as a CSV file.
    Includes product details along with inventory quantity.
    """
    # Fetch data using the CRUD function
    inventory_data = get_all_products_with_inventory(db)

    # Generate CSV content using the service function
    csv_file_like = generate_inventory_csv(inventory_data)

    # Define headers for file download
    headers = {
        'Content-Disposition': 'attachment; filename="inventory.csv"'
    }

    # Return as a streaming response
    return StreamingResponse(
        iter([csv_file_like.getvalue()]),
        media_type="text/csv",
        headers=headers
    ) # Closing parenthesis for StreamingResponse


@router.get("/{product_id}", response_model=schemas.InventoryResponse)
def get_product_inventory_endpoint(
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Get inventory details for a specific product.
    """
    inventory = crud.get_inventory(db, product_id=product_id)
    if inventory is None:
        # Check if product exists before raising 404 for inventory
        product = crud.get_product(db, product_id=product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        # Product exists, but no inventory record
        raise HTTPException(status_code=404, detail="Inventory not found for this product")
    return inventory


@router.post("/upload", response_model=CSVUploadResponse)
async def upload_inventory_csv_endpoint(
    file: UploadFile = File(...), # Correct way to declare file upload dependency
    db: Session = Depends(get_db)
):
    """
    Upload a CSV file to bulk update inventory quantities.
    Expects columns: product_id, quantity.
    Creates inventory records if they don't exist for valid products.
    """
    # Check file content type
    if file.content_type not in ['text/csv', 'application/vnd.ms-excel']:
         raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV file.")

    try:
        # Parse the CSV file using the service
        # Note: parse_inventory_csv raises ValueError on format/type errors
        parsed_data = await parse_inventory_csv(file)
    except ValueError as e:
        # Handle CSV parsing errors (invalid format, headers, data types)
        raise HTTPException(status_code=400, detail=f"CSV Parsing Error: {e}")
    except Exception as e:
        # Catch unexpected errors during parsing
        # Log the error e for debugging
        print(f"Unexpected error during CSV parsing: {e}") # Basic logging
        raise HTTPException(status_code=500, detail=f"Internal Server Error during CSV parsing.")

    if not parsed_data:
        # Handle empty CSV or CSV with only headers
        # Need to adjust CSVUploadResponse model if created_count is needed
        return CSVUploadResponse(processed_rows=0, updated_count=0, errors=[])

    try:
        # Perform bulk update using the CRUD function
        # bulk_update_inventory handles product existence checks and DB operations
        result = bulk_update_inventory(db, updates=parsed_data)
        # Check if the result object needs adjustment based on CSVUploadResponse definition
        # Assuming bulk_update_inventory returns an object compatible with CSVUploadResponse
        return result
    except Exception as e:
        # Catch unexpected errors during database update
        # Log the error e for debugging
        print(f"Error during bulk inventory update: {e}") # Basic logging
        raise HTTPException(status_code=500, detail=f"Internal Server Error during database update.")
