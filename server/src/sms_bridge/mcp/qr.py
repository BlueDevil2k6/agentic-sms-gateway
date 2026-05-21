"""
QR code generation for Android app setup.

GET /setup/qr  →  PNG image encoding server URL + API key.
The Android app scans this to configure itself — no manual entry required.
"""

import json
import logging

import qrcode
import qrcode.image.svg
from io import BytesIO
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)


def generate_qr_png(ws_url: str, api_key: str, device_name: str = "SMS Gateway") -> bytes:
    """
    Generate a QR code PNG encoding the connection payload.

    Payload format (scanned by Android app):
    {
      "url":  "wss://your-server.com:8765",
      "key":  "sk-bridge-xxxxxxxx",
      "name": "SMS Gateway"
    }
    """
    payload = json.dumps({
        "url":  ws_url,
        "key":  api_key,
        "name": device_name,
    })

    qr = qrcode.QRCode(
        version=None,           # auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_qr_route(ws_url: str, api_key: str):
    """Returns a Starlette route handler for GET /setup/qr."""

    async def handle_qr(request: Request) -> Response:
        # Auth: same API key
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {api_key}":
            return Response("Unauthorized", status_code=401)

        png = generate_qr_png(ws_url=ws_url, api_key=api_key)
        log.info("QR code requested")
        return Response(content=png, media_type="image/png")

    return handle_qr
