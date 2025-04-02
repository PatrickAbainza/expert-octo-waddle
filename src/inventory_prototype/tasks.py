import json
import httpx
import hmac
import hashlib
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Dict, Any

# Import the Webhook model
from .models import Webhook

# ---------- WEBHOOK FUNCTION ----------

async def send_webhook(db: Session, event_type: str, payload: Dict[str, Any]):
    """
    Asynchronously send webhook notifications to all registered endpoints
    subscribed to the given event type.
    """
    # Query webhooks directly using the provided session
    # Note: Consider potential performance implications if many webhooks exist.
    # Could optimize by querying only for webhooks subscribed to event_type.
    webhooks = db.query(Webhook).all()

    # Add event_type and timestamp to the payload before sending
    payload_to_send = payload.copy() # Avoid modifying original payload dict
    payload_to_send["event_type"] = event_type
    payload_to_send["timestamp"] = datetime.now(timezone.utc).isoformat()

    for webhook in webhooks:
        # Check if this webhook is subscribed to this event
        subscribed_events = webhook.events.split(",")
        if event_type not in subscribed_events:
            continue

        # Create signature for verification
        # Ensure payload_to_send is consistently serialized for signature generation and sending
        try:
            payload_json = json.dumps(payload_to_send, sort_keys=True) # Use payload_to_send
        except TypeError:
            print(f"Error serializing payload_to_send for webhook {webhook.id} to {str(webhook.url)}. Skipping.")
            continue # Skip if payload cannot be serialized

        signature = hmac.new(
            webhook.secret.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()

        # Send webhook
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    str(webhook.url),  # Ensure URL is a string
                    content=payload_json, # Send the correctly serialized payload_to_send
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature
                    },
                    timeout=5.0 # Set a reasonable timeout
                )
                # Optional: Log webhook send status based on response
                if response.status_code >= 400:
                     print(f"Webhook to {str(webhook.url)} failed with status {response.status_code}")
                # else:
                #     print(f"Webhook to {str(webhook.url)} sent successfully.")

        except httpx.RequestError as e:
            # More specific error handling for network/request issues
            print(f"Error sending webhook to {str(webhook.url)}: Request failed - {str(e)}")
        except Exception as e:
            # Catch broader exceptions during sending
            print(f"Unexpected error sending webhook to {str(webhook.url)}: {str(e)}")