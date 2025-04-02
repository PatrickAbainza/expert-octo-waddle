import json
from sqlalchemy.orm import Session
from sqlalchemy.orm import Session, selectinload # Added selectinload
from typing import List, Optional, Dict, Any # Keep only used types
from typing import List, Optional # Keep only used types
from datetime import datetime, timezone # Added datetime, timezone

# Import local modules
from . import models, schemas
from .services.csv_service import CSVUploadResponse, CSVUploadError # Import response models

# ---------- PRODUCT CRUD ----------

def get_product(db: Session, product_id: int) -> Optional[models.Product]:
    """Retrieve a single product by its ID."""
    return db.query(models.Product).filter(models.Product.id == product_id).first()

def get_products(db: Session, skip: int = 0, limit: int = 100) -> List[models.Product]:
    """Retrieve a list of products with pagination."""
    return db.query(models.Product).offset(skip).limit(limit).all()

def search_products(db: Session, query: str) -> List[models.Product]:
    """Search for products by name (case-insensitive)."""
    # Using ilike for case-insensitive search (adjust based on DB capabilities if needed)
    return db.query(models.Product).filter(models.Product.name.ilike(f"%{query}%")).all()

def create_product(db: Session, product: schemas.ProductCreate) -> models.Product:
    """Create a new product in the database."""
    # Convert custom_properties dict to JSON string if provided
    custom_props_json = json.dumps(product.custom_properties) if product.custom_properties else None
    db_product = models.Product(
        name=product.name,
        description=product.description,
        unit=product.unit,
        price_per_unit=product.price_per_unit,
        custom_properties=custom_props_json
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def update_product(db: Session, product_id: int, update_data: schemas.ProductUpdate) -> Optional[models.Product]:
    """Update an existing product."""
    db_product = get_product(db, product_id)
    if not db_product:
        return None

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field == 'custom_properties':
            # Handle setting to None explicitly, otherwise serialize
            setattr(db_product, field, json.dumps(value) if value is not None else None)
        else:
            # Keep original logic for other fields (only update if value is not None)
            # If you want to allow setting other fields to None, remove this elif
            if value is not None:
                setattr(db_product, field, value)

    db.commit()
    db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int) -> bool:
    """Deletes a product and its associated inventory record.

    Returns:
        True if deletion was successful, False otherwise.
    """
    # First, delete associated inventory if it exists
    inventory = get_inventory(db, product_id)
    if inventory:
        db.delete(inventory)
        # Commit inventory deletion separately or together with product?
        # Let's commit together for atomicity.

    # Then, delete the product
    db_product = get_product(db, product_id)
    if db_product:
        db.delete(db_product)
        db.commit() # Commit both deletions (or rollback both on error)
        return True
    else:
        # If product wasn't found, but inventory might have been deleted,
        # rollback the inventory deletion if it happened.
        # However, get_product was called after get_inventory, so if product
        # is None here, it means it didn't exist to begin with.
        # If inventory existed for a non-existent product (data inconsistency),
        # the inventory deletion might have been committed if we did it separately.
        # Committing together is safer.
        db.rollback() # Rollback if product not found after potential inventory delete attempt
        return False

# Placeholder for delete_product if needed
# def delete_product(db: Session, product_id: int) -> Optional[models.Product]:
#     db_product = get_product(db, product_id)
#     if db_product:
#         # Consider related inventory/orders before deleting
#         db.delete(db_product)
#         db.commit()
#         return db_product
#     return None

# ---------- INVENTORY CRUD ----------

def get_inventory(db: Session, product_id: int) -> Optional[models.Inventory]:
    """Retrieve inventory for a specific product ID."""
    return db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()

def list_all_inventory(db: Session) -> List[models.Inventory]:
    """Retrieve all inventory items."""
    # Eager load product details to avoid N+1 queries if product info is needed later
    return db.query(models.Inventory).options(selectinload(models.Inventory.product)).all()

def update_inventory_quantity(db: Session, product_id: int, quantity: float) -> Optional[models.Inventory]:
    """Update inventory quantity for a product. Creates record if none exists."""
    inventory = get_inventory(db, product_id)
    if not inventory:
        # Check if product exists before creating inventory
        product = get_product(db, product_id)
        if not product:
            return None # Cannot create inventory for non-existent product
        inventory = models.Inventory(product_id=product_id, quantity=quantity)
        db.add(inventory)
    else:
        inventory.quantity = quantity # type: ignore

    inventory.last_updated = datetime.now(timezone.utc) # type: ignore
    db.commit()
    db.refresh(inventory)
    return inventory

def adjust_inventory(db: Session, product_id: int, quantity_change: float) -> Optional[models.Inventory]:
    """Adjust inventory by a relative amount (positive or negative)."""
    inventory = get_inventory(db, product_id)
    if not inventory:
         # If no inventory record, assume starting from 0, but only if product exists
         product = get_product(db, product_id)
         if not product:
             return None # Cannot adjust inventory for non-existent product
         # If adjusting positively, create record. If negatively, it's an error (can't go below 0).
         if quantity_change < 0:
              # Or raise an error? For now, return None indicating failure.
              print(f"Warning: Attempted negative adjustment for non-existent inventory (product_id: {product_id})")
              return None
         inventory = models.Inventory(product_id=product_id, quantity=quantity_change)
         db.add(inventory)
    else:
        new_quantity = inventory.quantity + quantity_change # type: ignore
        if new_quantity < 0:
            # Or raise an error? For now, return None indicating failure.
            print(f"Warning: Inventory adjustment for product {product_id} resulted in negative quantity ({new_quantity}). Adjustment not applied.")
            return None # Indicate failure due to insufficient stock for negative adjustment
        inventory.quantity = new_quantity # type: ignore

    inventory.last_updated = datetime.now(timezone.utc) # type: ignore
    # Commit happens here, assuming adjustment is valid
    db.commit()
    db.refresh(inventory)
    return inventory

def bulk_update_inventory(db: Session, updates: List[Dict[str, Any]]) -> CSVUploadResponse:
    """Updates inventory quantities based on a list of updates (e.g., from CSV).

    Args:
        db: The database session.
        updates: A list of dictionaries, each containing 'product_id', 'quantity',
                 and 'row_number'.

    Returns:
        A CSVUploadResponse object summarizing the results.
    """
    processed_rows = len(updates)
    updated_count = 0
    errors: List[CSVUploadError] = []

    for update in updates:
        product_id = update['product_id']
        quantity = update['quantity']
        row_number = update['row_number']

        product = get_product(db, product_id)
        if not product:
            errors.append(CSVUploadError(row_number=row_number, error_message=f"Product ID {product_id} not found."))
            continue

        inventory = get_inventory(db, product_id)
        try:
            if not inventory:
                # Create new inventory record
                inventory = models.Inventory(
                    product_id=product_id,
                    quantity=quantity,
                    last_updated=datetime.now(timezone.utc)
                )
                db.add(inventory)
            else:
                # Update existing inventory record
                inventory.quantity = quantity # type: ignore
                inventory.last_updated = datetime.now(timezone.utc) # type: ignore

            db.commit() # Commit after each successful update/creation
            db.refresh(inventory)
            updated_count += 1
        except Exception as e:
            db.rollback() # Rollback on error for this specific update
            errors.append(CSVUploadError(row_number=row_number, error_message=f"DB error updating product {product_id}: {e}"))

    return CSVUploadResponse(processed_rows=processed_rows, updated_count=updated_count, errors=errors)

def get_all_products_with_inventory(db: Session) -> List[Dict[str, Any]]:
    """Retrieves all products joined with their inventory data.

    Returns:
        A list of dictionaries, each containing product and inventory details.
    """
    results = db.query(
        models.Product.id.label('product_id'),
        models.Product.name,
        models.Product.unit,
        models.Product.price_per_unit,
        models.Inventory.quantity,
        models.Inventory.last_updated
    ).outerjoin(models.Inventory, models.Product.id == models.Inventory.product_id).all()

    # Convert Row objects to dictionaries
    return [row._asdict() for row in results]



# ---------- ORDER CRUD ----------

def get_order(db: Session, order_id: int) -> Optional[models.Order]:
    """Retrieve a single order by ID, eagerly loading items and their products."""
    return db.query(models.Order).options(
        selectinload(models.Order.items).selectinload(models.OrderItem.product)
    ).filter(models.Order.id == order_id).first()

def list_orders(db: Session, customer_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[models.Order]:
    """Retrieve a list of orders with pagination, optionally filtered by customer ID."""
    query = db.query(models.Order).options(
        selectinload(models.Order.items).selectinload(models.OrderItem.product)
    ).order_by(models.Order.created_at.desc()) # Order by most recent

    if customer_id:
        query = query.filter(models.Order.customer_id == customer_id)

    return query.offset(skip).limit(limit).all()


def create_db_order(db: Session, order_data: schemas.OrderCreate) -> models.Order:
    """Creates the main Order record."""
    db_order = models.Order(customer_id=order_data.customer_id)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

def add_order_item(db: Session, order_id: int, product_id: int, quantity: float, price: float) -> models.OrderItem:
    """Adds an item to an existing order."""
    db_item = models.OrderItem(
        order_id=order_id,
        product_id=product_id,
        quantity=quantity,
        price_at_order=price
    )
    db.add(db_item)
    # Commit might happen after all items are added in the calling function
    return db_item

def update_order_status(db: Session, order_id: int, status: str) -> Optional[models.Order]:
    """Update the status of an existing order."""
    db_order = get_order(db, order_id) # Use get_order to ensure it exists
    if not db_order:
        return None
    db_order.status = status # type: ignore
    db_order.updated_at = datetime.now(timezone.utc) # type: ignore
    db.commit()
    db.refresh(db_order)
    return db_order

def remove_order_item(db: Session, item_id: int):
    """Removes an item from an order by its ID."""
    item = db.query(models.OrderItem).filter(models.OrderItem.id == item_id).first()
    if item:
        db.delete(item)
        # Commit might happen later

def get_order_items(db: Session, order_id: int) -> List[models.OrderItem]:
     """Gets all items associated with an order."""
     return db.query(models.OrderItem).filter(models.OrderItem.order_id == order_id).all()


# ---------- WEBHOOK CRUD ----------

def create_webhook(db: Session, webhook_data: schemas.WebhookCreate) -> models.Webhook:
    """Register a new webhook endpoint."""
    events_str = ",".join(webhook_data.events) if webhook_data.events else ""
    db_webhook = models.Webhook(
        url=str(webhook_data.url), # Ensure URL is string
        secret=webhook_data.secret,
        events=events_str
    )
    db.add(db_webhook)
    db.commit()
    db.refresh(db_webhook)
    return db_webhook

def delete_webhook(db: Session, webhook_id: int) -> bool:
    """Delete a webhook registration."""
    db_webhook = db.query(models.Webhook).filter(models.Webhook.id == webhook_id).first()
    if db_webhook:
        db.delete(db_webhook)
        db.commit()
        return True
    return False

def get_webhooks_for_event(db: Session, event_type: str) -> List[models.Webhook]:
     """Get all webhooks subscribed to a specific event type."""
     # This might be less efficient than filtering in the send_webhook task,
     # but provides a dedicated CRUD function if needed elsewhere.
     # Use LIKE for comma-separated list matching.
     return db.query(models.Webhook).filter(
         models.Webhook.events.like(f"%{event_type}%")
     ).all()



# ---------- INVENTORY CRUD (to be added) ----------

# ---------- ORDER CRUD (to be added) ----------

# ---------- WEBHOOK CRUD (to be added) ----------