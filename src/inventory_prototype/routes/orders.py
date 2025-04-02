from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List, Optional

# Import local modules
from .. import crud, schemas, models, tasks
from ..database import get_db
from ..dependencies import verify_api_key

router = APIRouter(
    prefix="/api/orders",
    tags=["Orders"],
    dependencies=[Depends(verify_api_key)] # Apply API key verification
)

def _calculate_order_total(order: models.Order) -> float:
    """Helper to calculate total based on items."""
    if not order.items:
        return 0.0
    return sum(item.quantity * item.price_at_order for item in order.items)

@router.post("", status_code=201, response_model=schemas.OrderResponse)
async def create_order_endpoint(
    order: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a new order. Validates product existence and inventory levels.
    Adjusts inventory upon successful order creation.
    Triggers 'order_created' webhook.
    """
    order_items_to_create = []
    inventory_adjustments = {} # product_id: quantity_change

    # --- Phase 1: Validation ---
    for item in order.items:
        # Check product existence
        db_product = crud.get_product(db, item.product_id)
        if not db_product:
            raise HTTPException(status_code=404, detail=f"Product with ID {item.product_id} not found.")

        # Check inventory
        inventory = crud.get_inventory(db, item.product_id)
        available_quantity = inventory.quantity if inventory else 0
        if available_quantity < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient inventory for product ID {item.product_id}. Available: {available_quantity}, Requested: {item.quantity}"
            )

        # Prepare data for creation
        order_items_to_create.append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "price": db_product.price_per_unit # Use current price
        })
        inventory_adjustments[item.product_id] = inventory_adjustments.get(item.product_id, 0) - item.quantity

    # --- Phase 2: Creation & Inventory Adjustment ---
    # Create the main order record first
    db_order = crud.create_db_order(db, order_data=order)

    # Add items to the order
    created_items = []
    for item_data in order_items_to_create:
        db_item = crud.add_order_item(
            db=db,
            order_id=db_order.id,
            product_id=item_data["product_id"],
            quantity=item_data["quantity"],
            price=item_data["price"]
        )
        created_items.append(db_item)

    # Adjust inventory levels
    for product_id, change in inventory_adjustments.items():
        # We already validated inventory, so adjustment should succeed
        crud.adjust_inventory(db, product_id=product_id, quantity_change=change)

    # Commit all changes (order, items, inventory)
    db.commit()
    db.refresh(db_order) # Refresh to load items relationship if needed

    # Eagerly load items and product details for the response
    db_order_loaded = crud.get_order(db, db_order.id)
    if not db_order_loaded: # Should not happen
         raise HTTPException(status_code=500, detail="Failed to load created order details")

    # Calculate total for the response
    total = _calculate_order_total(db_order_loaded)
    response_data = schemas.OrderResponse.model_validate(db_order_loaded)
    response_data.total = total

    # --- Phase 3: Webhook ---
    # Send webhook in the background
    webhook_payload = response_data.model_dump(mode='json')
    background_tasks.add_task(tasks.send_webhook, db, "order_created", webhook_payload)

    return response_data


@router.get("/{order_id}", response_model=schemas.OrderResponse)
def get_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db)
):
    """
    Get details for a specific order by ID.
    """
    db_order = crud.get_order(db, order_id=order_id)
    if db_order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Calculate total
    total = _calculate_order_total(db_order)
    response_data = schemas.OrderResponse.model_validate(db_order)
    response_data.total = total
    return response_data

@router.get("", response_model=List[schemas.OrderResponse])
def list_orders_endpoint(
    customer_id: Optional[str] = Query(None, description="Filter orders by customer ID"),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    List orders with pagination, optionally filtering by customer ID.
    """
    db_orders = crud.list_orders(db, customer_id=customer_id, skip=skip, limit=limit)
    # Calculate total for each order
    response_list = []
    for order in db_orders:
        total = _calculate_order_total(order)
        order_data = schemas.OrderResponse.model_validate(order)
        order_data.total = total
        response_list.append(order_data)
    return response_list


@router.patch("/{order_id}/status", response_model=schemas.OrderResponse)
async def update_order_status_endpoint(
    order_id: int,
    status_update: schemas.OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Update the status of an order (e.g., 'processing', 'shipped', 'completed').
    Triggers 'order_update' webhook.
    """
    # Basic validation - more complex state transitions could be added
    valid_statuses = ["pending", "processing", "shipped", "completed", "cancelled"] # Include cancelled for completeness
    if status_update.status not in valid_statuses:
         raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    db_order = crud.update_order_status(db, order_id=order_id, status=status_update.status)
    if db_order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    # Reload with items for response and webhook
    db_order_loaded = crud.get_order(db, order_id)
    if not db_order_loaded: # Should not happen
         raise HTTPException(status_code=500, detail="Failed to load updated order details")

    total = _calculate_order_total(db_order_loaded)
    response_data = schemas.OrderResponse.model_validate(db_order_loaded)
    response_data.total = total

    # Send webhook
    webhook_payload = response_data.model_dump(mode='json')
    background_tasks.add_task(tasks.send_webhook, db, "order_update", webhook_payload)

    return response_data


@router.put("/{order_id}/items", response_model=schemas.OrderResponse)
async def update_order_items_endpoint(
    order_id: int,
    items_update: schemas.OrderItemsUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Replace all items in a 'pending' order.
    Validates inventory and adjusts stock accordingly.
    Triggers 'order_update' webhook.
    """
    db_order = crud.get_order(db, order_id=order_id)
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    if db_order.status != "pending":
        raise HTTPException(status_code=400, detail="Order items can only be modified for 'pending' orders.")

    new_items_data = items_update.items
    if not new_items_data:
         raise HTTPException(status_code=400, detail="Cannot update order with an empty item list.")

    # --- Phase 1: Validation and Inventory Calculation ---
    inventory_adjustments = {} # product_id: quantity_change
    new_order_items_to_create = []
    current_items = db_order.items # Already loaded by crud.get_order

    # Calculate inventory restoration from current items
    for current_item in current_items:
        inventory_adjustments[current_item.product_id] = inventory_adjustments.get(current_item.product_id, 0) + current_item.quantity

    # Validate new items and calculate deductions
    # No need for temp_inventory_check, validate against current DB state
    for new_item in new_items_data:
        db_product = crud.get_product(db, new_item.product_id)
        if not db_product:
            raise HTTPException(status_code=404, detail=f"Product with ID {new_item.product_id} not found.")

        # Check against *current* inventory in the database
        inventory = crud.get_inventory(db, new_item.product_id)
        available_quantity = inventory.quantity if inventory else 0
        if available_quantity < new_item.quantity:
             raise HTTPException(
                 status_code=400,
                 # Updated error message slightly for clarity
                 detail=f"Insufficient inventory for product ID {new_item.product_id}. Available: {available_quantity}, Requested: {new_item.quantity}"
             )

        # Update final adjustments and prepare creation data
        # Note: The inventory_adjustments dict now correctly reflects the *net* change needed
        # (e.g., +old_quantity - new_quantity)
        inventory_adjustments[new_item.product_id] = inventory_adjustments.get(new_item.product_id, 0) - new_item.quantity

        new_order_items_to_create.append({
            "product_id": new_item.product_id,
            "quantity": new_item.quantity,
            "price": db_product.price_per_unit
        })

    # --- Phase 2: Database Operations ---
    # Remove old items (cascade should handle this, but explicit can be safer depending on cascade config)
    # Alternatively, rely on relationship cascade:
    for item in current_items:
         db.delete(item)
    # db.query(models.OrderItem).filter(models.OrderItem.order_id == order_id).delete() # Alternative direct delete

    # Add new items
    for item_data in new_order_items_to_create:
        crud.add_order_item(
            db=db,
            order_id=order_id,
            product_id=item_data["product_id"],
            quantity=item_data["quantity"],
            price=item_data["price"]
        )

    # Apply final inventory adjustments
    for product_id, change in inventory_adjustments.items():
        if change != 0: # Only adjust if there's a net change
            crud.adjust_inventory(db, product_id=product_id, quantity_change=change)

    # Update order timestamp - Handled by model onupdate or commit trigger

    db.commit()

    # --- Phase 3: Response and Webhook ---
    db_order_loaded = crud.get_order(db, order_id) # Reload to get new items
    if not db_order_loaded:
         raise HTTPException(status_code=500, detail="Failed to load updated order details")

    total = _calculate_order_total(db_order_loaded)
    response_data = schemas.OrderResponse.model_validate(db_order_loaded)
    response_data.total = total

    webhook_payload = response_data.model_dump(mode='json')
    background_tasks.add_task(tasks.send_webhook, db, "order_update", webhook_payload)

    return response_data


@router.post("/{order_id}/cancel", response_model=schemas.OrderResponse)
async def cancel_order_endpoint(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Cancel a 'pending' order and restore inventory.
    Triggers 'order_update' webhook.
    """
    db_order = crud.get_order(db, order_id=order_id) # Eager loads items
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    if db_order.status != "pending":
        raise HTTPException(status_code=400, detail="Only 'pending' orders can be cancelled.")

    # Restore inventory
    for item in db_order.items:
        crud.adjust_inventory(db, product_id=item.product_id, quantity_change=item.quantity)

    # Update status using CRUD function (handles commit and timestamp)
    updated_order = crud.update_order_status(db, order_id=order_id, status="cancelled")
    if not updated_order:
         # This shouldn't happen if get_order succeeded, but handle defensively
         raise HTTPException(status_code=500, detail="Failed to update order status after inventory restoration.")
    db_order = updated_order # Use the updated order object

    # db.commit() # Commit is handled by crud.update_order_status
    # db.refresh(db_order) # Refresh is handled by crud.update_order_status

    # Prepare response
    total = _calculate_order_total(db_order) # Should be 0 if items are removed by cascade, or calculated before status change? Let's keep calculation consistent.
    response_data = schemas.OrderResponse.model_validate(db_order)
    response_data.total = total # Keep total as it was at time of order? Or set to 0? Let's keep it.

    # Send webhook
    webhook_payload = response_data.model_dump(mode='json')
    # Consider adding a specific 'order_cancelled' event type? For now, use 'order_update'.
    background_tasks.add_task(tasks.send_webhook, db, "order_update", webhook_payload)

    return response_data


@router.post("/quick", status_code=201, response_model=schemas.OrderResponse)
async def quick_order_endpoint(
    # Dependencies first (non-default before default)
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    # Query parameters next
    customer_id: str = Query(..., description="Customer ID for the order"),
    product_id: int = Query(..., description="ID of the product to order"),
    quantity: float = Query(1.0, gt=0, description="Quantity of the product to order (defaults to 1.0)") # Made optional, default 1.0
):
    """
    Quickly create an order for a single product.
    Validates product and inventory, adjusts stock, triggers webhook.
    """
    # Validation
    db_product = crud.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found.")

    inventory = crud.get_inventory(db, product_id)
    available_quantity = inventory.quantity if inventory else 0
    if available_quantity < quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient inventory for product ID {product_id}. Available: {available_quantity}, Requested: {quantity}"
        )

    # Create Order and Item
    order_data = schemas.OrderCreate(customer_id=customer_id, items=[]) # Dummy items list initially
    db_order = crud.create_db_order(db, order_data=order_data)

    crud.add_order_item(
        db=db,
        order_id=db_order.id,
        product_id=product_id,
        quantity=quantity,
        price=float(db_product.price_per_unit) # Explicitly cast to float
    )

    # Adjust Inventory
    crud.adjust_inventory(db, product_id=product_id, quantity_change=-quantity)

    db.commit()

    # Response and Webhook
    db_order_loaded = crud.get_order(db, db_order.id)
    if not db_order_loaded:
         raise HTTPException(status_code=500, detail="Failed to load created order details")

    total = _calculate_order_total(db_order_loaded)
    response_data = schemas.OrderResponse.model_validate(db_order_loaded)
    response_data.total = total

    webhook_payload = response_data.model_dump(mode='json')
    background_tasks.add_task(tasks.send_webhook, db, "order_created", webhook_payload)

    return response_data


@router.get("/history/{customer_id}", response_model=List[schemas.OrderResponse])
def get_customer_order_history_endpoint(
    customer_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Get the order history for a specific customer.
    """
    # Use the existing list_orders function with customer_id filter
    db_orders = crud.list_orders(db, customer_id=customer_id, skip=skip, limit=limit)
    response_list = []
    for order in db_orders:
        total = _calculate_order_total(order)
        order_data = schemas.OrderResponse.model_validate(order)
        order_data.total = total
        response_list.append(order_data)
    return response_list