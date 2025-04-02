# Inventory Prototype API

A simple, extensible inventory API system using FastAPI and SQLAlchemy, designed for chatbot integration and rapid prototyping.

## Project Structure

This project uses a standard `src` layout:

- `src/inventory_prototype/`: Contains the main application code (models, schemas, routes, etc.)
- `tests/`: Contains unit and integration tests.
- `scripts/`: Contains simulation scripts for testing API endpoints.
- `docs/`: Contains project documentation.
- `pyproject.toml`: Defines project dependencies and metadata (Poetry).

## Setup

1.  **Prerequisites:**

    - Python 3.8+
    - Poetry (>=1.2 recommended)

2.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd inventory_chatbot
    ```

3.  **Install dependencies:**

    ```bash
    poetry install
    ```

4.  **Environment Variables:**
    - (Optional) Create a `.env` file in the project root.
    - Set the `API_KEY` environment variable (or use the default `prototype_key_change_me` for development).
    ```dotenv
    # .env
    API_KEY=your_secure_api_key_here
    # DATABASE_URL=sqlite:///./your_database_name.db # Optional: Override default DB name
    ```
    - Poetry should automatically load variables from `.env` if `python-dotenv` is installed (or you can load manually).

## Running the Application

Use `uvicorn` to run the FastAPI application:

```bash
poetry run uvicorn inventory_prototype.main:app --reload --port 8000
```

The API will be available at `http://127.0.0.1:8000`.

## Running Tests

Ensure you have installed the development dependencies (`poetry install --with dev`).

Run tests using `pytest`:

```bash
poetry run pytest
```

## Running Simulation Scripts

Various scripts are available in the `scripts/` directory to simulate API interactions:

```bash
poetry run python scripts/simulate_workflow.py
poetry run python scripts/simulate_order_endpoints.py
# etc.
```

Ensure the API server is running before executing the simulation scripts.
