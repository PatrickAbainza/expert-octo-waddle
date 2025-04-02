import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine.base import Transaction # Import Transaction for type hinting
from sqlalchemy.pool import StaticPool # To ensure single connection for :memory:
# Removed unused os import
from typing import Generator, Any, Dict, List, Callable # Added Dict, List, Callable, Removed Optional
from unittest.mock import patch, AsyncMock # Added patch, AsyncMock

# Import from the new package structure
from inventory_prototype.main import app
from inventory_prototype.database import Base, get_db

# Use an in-memory SQLite database configured for single connection
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool, # Use StaticPool for :memory: DB with TestClient
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_database_schema():
    """
    Creates the database schema once for the entire test session.
    """
    # Create tables using the engine directly
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after the session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session_override() -> Generator[Session, Any, None]:
    """
    Provides a transactional session for tests, overriding the app's get_db.
    Ensures tests run in isolation within a transaction that's rolled back.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # Begin nested transaction for savepoints
    nested = connection.begin_nested()

    # Define the event listener function with type hints
    def end_savepoint(session: Session, transaction: Transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    # Attach the listener
    event.listen(session, "after_transaction_end", end_savepoint)

    # Override the app's dependency
    original_override = app.dependency_overrides.get(get_db)
    def override_get_db_test() -> Generator[Session, Any, None]:
        yield session
    app.dependency_overrides[get_db] = override_get_db_test

    try:
        yield session # Provide the session to the test function
    finally:
        # Clean up session and transaction
        session.close()
        transaction.rollback() # Rollback the outer transaction
        connection.close()
        # Restore original override
        if original_override:
            app.dependency_overrides[get_db] = original_override
        else:
            # Ensure key exists before deleting
            if get_db in app.dependency_overrides:
                 del app.dependency_overrides[get_db]


@pytest.fixture(scope="function")
def integration_client(db_session_override: Session) -> Generator[TestClient, Any, None]:
    """
    Provides a TestClient configured for integration tests.
    Relies on db_session_override fixture for transactional DB setup.
    """
    # db_session_override handles the transaction and dependency override
    with TestClient(app) as client:
        yield client
    # db_session_override handles cleanup


@pytest.fixture(scope="function")
def db_session(db_session_override: Session) -> Session:
    """
    Provides the same transactional SQLAlchemy session used by the override
    for direct test setup/assertions.
    """
    # The db_session_override fixture already provides the correctly scoped session
    return db_session_override


# Define the API key used in tests
API_KEY = "prototype_key_change_me"

@pytest.fixture(scope="session")
def api_key() -> str:
    """Provides the API key for tests."""
    return API_KEY


# --- Shared Helper Fixtures ---

@pytest.fixture(scope='function')
def create_product(integration_client: TestClient, api_key: str) -> Callable[..., int]:
    """Provides a callable function to create a product within a test."""
    def _create_product_helper(name: str, unit: str, price: float, description: str | None = None, custom_properties: Dict[str, Any] | None = None) -> int:
        client = integration_client
        payload: Dict[str, Any] = {"name": name, "unit": unit, "price_per_unit": price}
        if description:
            payload["description"] = description
        if custom_properties:
            payload["custom_properties"] = custom_properties
        prod_response = client.post(f"/api/products?api_key={api_key}", json=payload)
        assert prod_response.status_code == 201, f"Failed to create product {name}: {prod_response.text}"
        return prod_response.json()["id"]
    return _create_product_helper

@pytest.fixture(scope='function')
def set_inventory(integration_client: TestClient, api_key: str) -> Callable[..., None]:
    """Provides a callable function to set inventory for a product."""
    def _set_inventory_helper(product_id: int, quantity: float):
        client = integration_client
        inv_response = client.patch(f"/api/inventory/{product_id}?api_key={api_key}", json={"quantity": quantity})
        assert inv_response.status_code == 200, f"Failed to set inventory for {product_id}: {inv_response.text}"
    return _set_inventory_helper

@pytest.fixture(scope='function')
def create_order(integration_client: TestClient, api_key: str) -> Callable[..., int]:
    """Provides a callable function to create an order within a test."""
    def _create_order_helper(customer_id: str, items: List[Dict[str, Any]]) -> int:
        client = integration_client
        order_data = {"customer_id": customer_id, "items": items}
        # Mock webhook during order creation for integration tests
        with patch('inventory_prototype.tasks.send_webhook', new_callable=AsyncMock): # Updated patch target
            response = client.post(f"/api/orders?api_key={api_key}", json=order_data)
        assert response.status_code == 201, f"Failed to create order for {customer_id}: {response.text}"
        return response.json()["id"]
    return _create_order_helper

# Removed extra return API_KEY


# --- Chatbot Specific Fixtures ---

@pytest.fixture(scope='function')
def chatbot_products(create_product: Callable[..., int], set_inventory: Callable[..., None]) -> Dict[str, int]:
    """Creates standard products needed for chatbot flow tests."""
    products = {}
    products["Test Flour"] = create_product(name="Test Flour", unit="kg", price=50.0, description="Premium All-Purpose Flour")
    products["Test Sugar"] = create_product(name="Test Sugar", unit="kg", price=40.0, description="Refined White Sugar")
    products["Test Coffee"] = create_product(name="Test Coffee", unit="bag", price=250.0, description="Whole Bean Arabica Coffee (250g)")

    # Set initial inventory
    set_inventory(product_id=products["Test Flour"], quantity=100.0)
    set_inventory(product_id=products["Test Sugar"], quantity=50.0)
    set_inventory(product_id=products["Test Coffee"], quantity=20.0)

    return products


@pytest.fixture(scope='function')
def chatbot_order_history(chatbot_products: Dict[str, int], create_order: Callable[..., int]) -> str:
    """Creates a customer and order history for chatbot reorder tests."""
    customer_id = "chatbot_test_customer_123"
    flour_id = chatbot_products["Test Flour"]
    sugar_id = chatbot_products["Test Sugar"]

    # Order 1: Flour x 2kg
    create_order(customer_id=customer_id, items=[{"product_id": flour_id, "quantity": 2}])
    # Order 2: Sugar x 5kg, Flour x 1kg
    create_order(customer_id=customer_id, items=[{"product_id": sugar_id, "quantity": 5}, {"product_id": flour_id, "quantity": 1}])
    # Order 3: Flour x 3kg
    create_order(customer_id=customer_id, items=[{"product_id": flour_id, "quantity": 3}])

    return customer_id

    # Removed duplicate return products

