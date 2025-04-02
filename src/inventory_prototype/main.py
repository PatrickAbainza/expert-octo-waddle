from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers from the routes package
from .routes import products, inventory, orders, webhooks

# Import database utility (optional, for startup event)
from .database import create_db_and_tables # Removed engine import

# --- App Initialization ---
app = FastAPI(
    title="Inventory Prototype API",
    description="A simple, extensible inventory API system using FastAPI and SQLAlchemy.",
    version="0.2.0" # Increment version after refactor
)

# --- Middleware ---
# Enable CORS for development (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Replace with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Lifespan Event Handler (Replaces on_event) ---
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print("Starting up...")
    try:
        create_db_and_tables()
        print("Database tables checked/created.")
    except Exception as e:
        print(f"Error creating database tables during startup: {e}")
        # Consider raising the exception or handling it to prevent startup if critical
    yield
    # Code to run on shutdown
    print("Shutting down...")

# Assign the lifespan context manager to the app
app.router.lifespan_context = lifespan


# --- Include Routers ---
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(webhooks.router)

# --- Root Endpoint ---
@app.get("/", tags=["Health Check"])
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "message": "Inventory API is running"}

# Note: The uvicorn command should now point to this file:
# uvicorn inventory_prototype.main:app --reload --port 8000