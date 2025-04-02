import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta

from inventory_prototype.main import app # Updated import
from inventory_prototype.database import Base, get_db # Updated import

# Create test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_unit.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = None
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        if db is not None:
            db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

API_KEY = "prototype_key_change_me"

# Helper to create a product
def create_test_product(client: TestClient, name: str = "Test Product", unit: str = "piece", price: float = 10.0) -> int:
    """Helper function to create a product and return its ID."""
    response = client.post(
        f"/api/products?api_key={API_KEY}",
        json={"name": name, "unit": unit, "price_per_unit": price}
    )
    assert response.status_code == 201
    return response.json()["id"]

def test_initial_inventory_status(client: TestClient):
    """Test that a newly created product has 'out_of_stock' status"""
    product_id = create_test_product(client)
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "out_of_stock"
    assert data["quantity"] == 0

def test_inventory_status_before_creation(client: TestClient):
    """Test getting status for a product before inventory record exists"""
    # Create product but don't update inventory
    product_id = create_test_product(client, name="No Inventory Yet")
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "out_of_stock"
    assert data["quantity"] == 0

def test_update_inventory_quantity(client: TestClient):
    """Test updating inventory quantity for a product"""
    product_id = create_test_product(client)
    response = client.patch(
        f"/api/inventory/{product_id}?api_key={API_KEY}",
        json={"quantity": 50.5}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == product_id
    assert data["quantity"] == 50.5

    # Verify status reflects the update
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    assert response.json()["status"] == "in_stock"
    assert response.json()["quantity"] == 50.5

def test_update_inventory_quantity_zero(client: TestClient):
    """Test updating inventory quantity to exactly zero"""
    product_id = create_test_product(client)
    # Set initial quantity
    client.patch(f"/api/inventory/{product_id}?api_key={API_KEY}", json={"quantity": 10})

    # Update to zero
    response = client.patch(
        f"/api/inventory/{product_id}?api_key={API_KEY}",
        json={"quantity": 0}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == product_id
    assert data["quantity"] == 0

    # Verify status
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    assert response.json()["status"] == "out_of_stock"
    assert response.json()["quantity"] == 0

def test_update_inventory_with_negative_quantity(client: TestClient):
    """Test that updating inventory with negative quantity fails"""
    product_id = create_test_product(client)
    response = client.patch(
        f"/api/inventory/{product_id}?api_key={API_KEY}",
        json={"quantity": -10}
    )
    assert response.status_code == 422

def test_update_inventory_timestamp(client: TestClient):
    """Test that updating inventory updates the last_updated timestamp"""
    product_id = create_test_product(client)
    time_before_update = datetime.now(timezone.utc) - timedelta(seconds=1)

    response = client.patch(
        f"/api/inventory/{product_id}?api_key={API_KEY}",
        json={"quantity": 20}
    )
    assert response.status_code == 200
    data = response.json()
    # Make the comparison timezone-aware
    last_updated = datetime.fromisoformat(data["last_updated"]).replace(tzinfo=timezone.utc)

    assert last_updated > time_before_update # time_before_update is already timezone-aware
    assert last_updated <= datetime.now(timezone.utc) + timedelta(seconds=1)

def test_inventory_status_transitions(client: TestClient):
    """Test inventory status transitions: in_stock -> low_stock -> out_of_stock"""
    product_id = create_test_product(client)

    # 1. Set to in_stock (e.g., 20 units)
    client.patch(f"/api/inventory/{product_id}?api_key={API_KEY}", json={"quantity": 20})
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    assert response.json()["status"] == "in_stock"
    assert response.json()["quantity"] == 20

    # 2. Update to low_stock (e.g., 5 units, threshold is < 10)
    client.patch(f"/api/inventory/{product_id}?api_key={API_KEY}", json={"quantity": 5})
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    assert response.json()["status"] == "low_stock"
    assert response.json()["quantity"] == 5

    # 3. Update to out_of_stock (e.g., 0 units)
    client.patch(f"/api/inventory/{product_id}?api_key={API_KEY}", json={"quantity": 0})
    response = client.get(f"/api/inventory/status/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    assert response.json()["status"] == "out_of_stock"
    assert response.json()["quantity"] == 0

def test_inventory_for_nonexistent_product(client: TestClient):
    """Test handling inventory operations for non-existent products"""
    # Test GET status for non-existent product
    response = client.get(f"/api/inventory/status/999?api_key={API_KEY}")
    assert response.status_code == 404

    # Test PATCH for non-existent product
    response = client.patch(
        f"/api/inventory/999?api_key={API_KEY}",
        json={"quantity": 100}
    )
    assert response.status_code == 404

    # Test GET inventory for non-existent product
    response = client.get(f"/api/inventory/999?api_key={API_KEY}")
    assert response.status_code == 404

def test_list_all_inventory(client: TestClient):
    """Test listing all inventory items"""
    # Create some products and inventory
    p1_id = create_test_product(client, name="P1")
    p2_id = create_test_product(client, name="P2")
    client.patch(f"/api/inventory/{p1_id}?api_key={API_KEY}", json={"quantity": 10})
    client.patch(f"/api/inventory/{p2_id}?api_key={API_KEY}", json={"quantity": 20})

    response = client.get(f"/api/inventory?api_key={API_KEY}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    product_ids_in_response = {item["product_id"] for item in data}
    assert product_ids_in_response == {p1_id, p2_id}

def test_get_specific_product_inventory(client: TestClient):
    """Test getting inventory for a specific product"""
    product_id = create_test_product(client)
    client.patch(f"/api/inventory/{product_id}?api_key={API_KEY}", json={"quantity": 33})

    response = client.get(f"/api/inventory/{product_id}?api_key={API_KEY}")
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == product_id
    assert data["quantity"] == 33
    assert data["product"]["id"] == product_id

def test_authentication_inventory_endpoints(client: TestClient):
    """Test authentication requirement for inventory endpoints."""
    # Create a product first for testing PATCH/GET specific
    product_id = create_test_product(client)

    # Missing API key
    response = client.get("/api/inventory/status/1") # Assuming 1 might exist
    assert response.status_code == 401 # Auth check happens first
    response = client.patch(f"/api/inventory/{product_id}", json={"quantity": 10})
    assert response.status_code == 401 # Auth check happens first
    response = client.get("/api/inventory")
    assert response.status_code == 401 # Auth check happens first
    response = client.get(f"/api/inventory/{product_id}")
    assert response.status_code == 401 # Auth check happens first

    # Invalid API key
    response = client.get("/api/inventory/status/1?api_key=invalid")
    assert response.status_code == 401
    response = client.patch(f"/api/inventory/{product_id}?api_key=invalid", json={"quantity": 10})
    assert response.status_code == 401
    response = client.get("/api/inventory?api_key=invalid")
    assert response.status_code == 401
    response = client.get(f"/api/inventory/{product_id}?api_key=invalid")
    assert response.status_code == 401
