import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from pydantic import BaseModel

from ..models import Product  # Assuming Product model exists


class CSVUploadError(BaseModel):
    row_number: int
    error_message: str


class CSVUploadResponse(BaseModel):
    processed_rows: int
    updated_count: int
    errors: List[CSVUploadError]


async def parse_inventory_csv(file: UploadFile) -> List[Dict[str, Any]]:
    """
    Parses an uploaded CSV file expecting 'product_id' and 'quantity' columns.

    Args:
        file: The uploaded CSV file.

    Returns:
        A list of dictionaries, each representing a row with 'product_id' and 'quantity'.
        Raises ValueError for parsing errors (e.g., non-numeric quantity).
    """
    # Implementation needed
    updates: List[Dict[str, Any]] = []
    content = await file.read()
    decoded_content = content.decode('utf-8')
    csv_reader = csv.reader(io.StringIO(decoded_content))

    header = next(csv_reader, None)
    if not header or header != ['product_id', 'quantity']:
        raise ValueError("Invalid CSV header. Expected 'product_id,quantity'.")

    for i, row in enumerate(csv_reader, start=2): # Start row count from 2 (after header)
        if len(row) != 2:
            raise ValueError(f"Row {i}: Invalid number of columns. Expected 2, got {len(row)}.")
        product_id_str, quantity_str = row
        try:
            # Basic validation - more robust validation in CRUD
            product_id = int(product_id_str)
            quantity = float(quantity_str) # Changed to float to allow decimals
            if quantity < 0:
                 raise ValueError(f"Row {i}: Quantity cannot be negative.")
            updates.append({"product_id": product_id, "quantity": quantity, "row_number": i})
        except ValueError as e:
            raise ValueError(f"Row {i}: Invalid data type - {e}") from e

    return updates


def generate_inventory_csv(products_with_inventory: List[Dict[str, Any]]) -> io.StringIO:
    """
    Generates an in-memory CSV file from product and inventory data.

    Args:
        products_with_inventory: A list of dictionaries containing product and inventory details.
                                 Expected keys: 'product_id', 'name', 'unit', 'price_per_unit',
                                                'quantity', 'last_updated'.

    Returns:
        An io.StringIO object containing the CSV data.
    """
    # Implementation needed
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    header = ['product_id', 'name', 'unit', 'price_per_unit', 'quantity', 'last_updated']
    writer.writerow(header)

    # Write data rows
    for item in products_with_inventory:
        writer.writerow([
            item.get('product_id'),
            item.get('name'),
            item.get('unit'),
            item.get('price_per_unit'),
            item.get('quantity'),
            item.get('last_updated') # Ensure this is formatted appropriately if needed
        ])

    output.seek(0)
    return output