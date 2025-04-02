import os

# Load API key from environment variable or use a default
# IMPORTANT: The default key is insecure and should NOT be used in production.
# Set the API_KEY environment variable for deployment.
API_KEY = os.environ.get("API_KEY", "prototype_key_change_me")

# You can add other configuration variables here as needed,
# e.g., database URL, logging settings, external service URLs.

# Example:
# LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")