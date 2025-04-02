import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any

# Import local modules
from .. import crud, schemas, models
from ..database import get_db
from ..dependencies import verify_api_key

router = APIRouter(
    prefix="/api/products",
    tags=["Products"],
    dependencies=[Depends(verify_api_key)] # Apply API key verification to all routes in this router
)

@router.post("", status_code=201, response_model=schemas.ProductResponse)
def create_product_endpoint(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new product.
    """
    return crud.create_product(db=db, product=product)

@router.get("/featured", response_model=List[Dict[str, Any]]) # Using Dict for custom response structure
def get_featured_products_endpoint(
    limit: int = Query(5, ge=1, le=50, description="Number of featured products to return"),
    db: Session = Depends(get_db)
):
    """
    Get featured/popular products.
    (Simplified: based on highest inventory quantity)
    """
    # This logic remains somewhat complex and might be better suited for a dedicated service layer later,
    # but for now, we adapt the original logic using CRUD functions.
    top_inventory = db.query(models.Inventory).order_by(models.Inventory.quantity.desc()).limit(limit).all()
    product_ids = [inv.product_id for inv in top_inventory]

    if not product_ids:
        return []

    products = db.query(models.Product).filter(models.Product.id.in_(product_ids)).all()
    # inventory_map = {inv.product_id: inv for inv in top_inventory} # Unused variable
    product_map = {prod.id: prod for prod in products}

    result = []
    # Maintain the order from top_inventory
    for inv in top_inventory:
        product = product_map.get(inv.product_id)
        if not product:
            continue # Should not happen if DB is consistent

        custom_props = {}
        if product.custom_properties:
            try:
                custom_props = json.loads(product.custom_properties)
            except json.JSONDecodeError:
                pass # Ignore invalid JSON

        result.append({
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "unit": product.unit,
            "price_per_unit": product.price_per_unit,
            "available": inv.quantity > 0,
            "quantity": inv.quantity,
            "custom_properties": custom_props
        })

    return result


@router.get("/{product_id}", response_model=schemas.ProductResponse)
def get_product_endpoint(
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Get details for a specific product by ID.
    """
    db_product = crud.get_product(db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

@router.patch("/{product_id}", response_model=schemas.ProductResponse)
def update_product_endpoint(
    product_id: int,
    update: schemas.ProductUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing product. Only provided fields will be updated.
    """
    db_product = crud.update_product(db, product_id=product_id, update_data=update)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

@router.get("", response_model=List[schemas.ProductResponse])
def list_products_endpoint(
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    List products with pagination.
    """
    products = crud.get_products(db, skip=skip, limit=limit)
    return products

@router.get("/search/", response_model=List[schemas.ProductResponse])
def search_products_endpoint(
    query: str = Query(..., min_length=1, description="Search query string for product name"),
    db: Session = Depends(get_db)
):
    """
    Search for products by name (case-insensitive).
    """
    products = crud.search_products(db, query=query)
    return products


@router.delete("/{product_id}", status_code=204)
def delete_product_endpoint(
    product_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a product by its ID.
    Also deletes the associated inventory record, if it exists.
    Returns 204 No Content on success.
    Returns 404 Not Found if the product does not exist.
    """
    deleted = crud.delete_product(db, product_id=product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    # No return value needed, FastAPI handles 204
