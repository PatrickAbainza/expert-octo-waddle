from fastapi import Query, HTTPException # Removed Depends
# Removed Session import

# Import config
from .config import API_KEY
# Removed get_db import

# API Key Verification Dependency
def verify_api_key(api_key: str = Query(None, alias="api_key")):
    """
    FastAPI dependency to verify the provided API key against the configured key.
    Raises HTTPException 401 if the key is missing or invalid.
    """
    if api_key and api_key == API_KEY:
        return True
    raise HTTPException(status_code=401, detail="Invalid or missing API key")

# Re-export get_db for convenience if desired, or import directly from database elsewhere
# Example: If you want all dependencies in one place:
# def get_database_session() -> Session:
#     return Depends(get_db)