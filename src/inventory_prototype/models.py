from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text # Removed Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

# Import Base from the database module
from .database import Base

# ---------- DATA MODELS ----------
# These models are intentionally simple for prototyping
# Add fields as needed by uncommenting examples or adding your own

class Product(Base): # type: ignore
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    unit = Column(String, nullable=False)  # kg, liter, case, etc.
    price_per_unit = Column(Float, nullable=False)

    # Extensibility: Uncomment or add fields as needed
    # category = Column(String, nullable=True)
    # sku = Column(String, nullable=True, unique=True)
    # barcode = Column(String, nullable=True)
    # is_active = Column(Boolean, default=True)
    # min_order_quantity = Column(Float, default=1)
    # image_url = Column(String, nullable=True)

    # Optional: Add custom JSON field for flexible properties
    custom_properties = Column(Text, nullable=True)  # Stored as JSON string

class Inventory(Base): # type: ignore
    __tablename__ = "inventory"

    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    quantity = Column(Float, nullable=False, default=0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Extensibility: Uncomment or add fields as needed
    # warehouse_location = Column(String, nullable=True)
    # reorder_level = Column(Float, nullable=True)
    # expiry_date = Column(DateTime, nullable=True)
    # lot_number = Column(String, nullable=True)

    product = relationship("Product")

class Order(Base): # type: ignore
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String, index=True, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Extensibility: Uncomment or add fields as needed
    # shipping_address = Column(String, nullable=True)
    # payment_method = Column(String, nullable=True)
    # notes = Column(Text, nullable=True)
    # priority = Column(Integer, default=0)
    # reference_number = Column(String, nullable=True)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base): # type: ignore
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    price_at_order = Column(Float, nullable=False)

    # Extensibility: Uncomment or add fields as needed
    # discount = Column(Float, default=0)
    # notes = Column(String, nullable=True)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

class Webhook(Base): # type: ignore
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    secret = Column(String, nullable=False)
    events = Column(String, nullable=False, default="order_update")  # Comma-separated event types