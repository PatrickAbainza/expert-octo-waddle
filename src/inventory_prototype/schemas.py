import json
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import models for relationships if needed for response models (e.g., ProductResponse in InventoryResponse)
# We will define ProductResponse first, then use it.

# ---------- PYDANTIC MODELS ----------
# For API request/response validation

# --- Product Schemas ---

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    unit: str
    price_per_unit: float = Field(gt=0, description="Price per unit must be greater than 0")
    custom_properties: Optional[Dict[str, Any]] = None

    @field_validator("custom_properties", mode='before')
    def validate_custom_properties(cls, v: Any):
        if v is not None:
            # Ensure it's a valid JSON serializable dict
            if not isinstance(v, dict):
                 raise ValueError("Custom properties must be a dictionary")
            try:
                json.dumps(v) # Check serializability
            except TypeError:
                raise ValueError("Custom properties must be JSON serializable")
        return v

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    price_per_unit: Optional[float] = None
    custom_properties: Optional[Dict[str, Any]] = None

class ProductResponse(ProductBase):
    id: int

    model_config = {
        "from_attributes": True
    }

    # Add validator to parse custom_properties JSON string back to dict
    @field_validator("custom_properties", mode='before')
    def parse_custom_properties(cls, v: Any):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string for custom_properties")
        return v # Return as is if already a dict or None

# --- Inventory Schemas ---

class InventoryUpdate(BaseModel):
    quantity: float = Field(ge=0, description="Quantity must be non-negative") # Allow 0, but not negative

class InventoryResponse(BaseModel):
    product_id: int
    product: ProductResponse # Use the defined ProductResponse schema
    quantity: float
    last_updated: datetime

    model_config = {
        "from_attributes": True
    }

# --- Order Schemas ---

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: float = Field(gt=0, description="Quantity must be greater than 0")

class OrderCreate(BaseModel):
    customer_id: str
    items: List[OrderItemCreate]

    # Extensibility: Uncomment or add fields as needed
    # shipping_address: Optional[str] = None
    # payment_method: Optional[str] = None
    # notes: Optional[str] = None
    # reference_number: Optional[str] = None


class OrderItemUpdate(BaseModel):
    product_id: int
    quantity: float = Field(gt=0, description="Quantity must be greater than 0")

class OrderItemsUpdateRequest(BaseModel):
    items: List[OrderItemUpdate]


class OrderItemResponse(BaseModel):
    product_id: int
    quantity: float
    price_at_order: float

    model_config = {
        "from_attributes": True
    }

class OrderResponse(BaseModel):
    id: int
    customer_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse]
    total: float = 0  # Calculated field

    model_config = {
        "from_attributes": True
    }

class OrderStatusUpdate(BaseModel):
    status: str

# --- Webhook Schemas ---

VALID_WEBHOOK_EVENTS = ["order_created", "order_update"]

class WebhookCreate(BaseModel):
    url: HttpUrl # Already validates URL format
    secret: str = Field(min_length=1, description="Webhook secret cannot be empty")
    events: Optional[List[str]] = ["order_update"]  # Default to order updates

    @field_validator("events")
    def validate_events(cls, v: Optional[List[str]]):
        if v is None: # Allow None if Optional
             return v # Return None if events are not provided, default will be used
        if not v: # Check for empty list explicitly
             raise ValueError("Events list cannot be empty if provided")
        if not all(event in VALID_WEBHOOK_EVENTS for event in v):
            raise ValueError(f"Invalid event type. Valid events are: {', '.join(VALID_WEBHOOK_EVENTS)}")
        return v

class WebhookResponse(BaseModel): # Added for consistency
    id: int
    url: HttpUrl
    events: str # Stored as comma-separated string in DB

    model_config = {
        "from_attributes": True
    }