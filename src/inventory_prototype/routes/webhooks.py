from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
# Removed unused List import

# Import local modules
from .. import crud, schemas
from ..database import get_db
from ..dependencies import verify_api_key

router = APIRouter(
    prefix="/api/webhooks",
    tags=["Webhooks"],
    dependencies=[Depends(verify_api_key)] # Apply API key verification
)

@router.post("", status_code=201, response_model=schemas.WebhookResponse)
def register_webhook_endpoint(
    webhook: schemas.WebhookCreate,
    db: Session = Depends(get_db)
):
    """
    Register a new webhook endpoint for event notifications.
    """
    # Basic validation for URL uniqueness could be added here or in CRUD
    # db_existing = db.query(models.Webhook).filter(models.Webhook.url == str(webhook.url)).first()
    # if db_existing:
    #     raise HTTPException(status_code=400, detail="Webhook URL already registered")

    return crud.create_webhook(db=db, webhook_data=webhook)

@router.delete("/{webhook_id}", status_code=204) # No content response
def delete_webhook_endpoint(
    webhook_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a webhook registration by its ID.
    """
    deleted = crud.delete_webhook(db=db, webhook_id=webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    # No return needed for 204

# Optional: Add an endpoint to list registered webhooks
# @router.get("", response_model=List[schemas.WebhookResponse])
# def list_webhooks_endpoint(db: Session = Depends(get_db)):
#     """List all registered webhooks."""
#     webhooks = db.query(models.Webhook).all() # Or create crud.get_webhooks()
#     return webhooks