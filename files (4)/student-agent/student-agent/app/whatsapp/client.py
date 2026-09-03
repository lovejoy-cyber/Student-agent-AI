import httpx

from app.config import settings

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


def send_whatsapp_text(to_wa_id: str, body: str) -> dict:
    """
    Sends a plain text message via the official WhatsApp Business Cloud API.
    Requires WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID to be set.

    If you're actually using a different integration (Twilio, 360dialog,
    whatsapp-web.js, etc.), this is the only file you need to rewrite —
    everything else in the system talks to WhatsApp only through this function.
    """
    url = f"{GRAPH_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body},
    }
    with httpx.Client(timeout=15) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
