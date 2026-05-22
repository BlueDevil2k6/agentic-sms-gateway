"""
WebSocket server — Android-facing.

Handles device registration, inbound SMS forwarding, and outbound SMS dispatch.
All connections must present a valid API key in the Authorization header
during the WebSocket upgrade handshake.
"""

import asyncio
import json
import logging
import ssl
from pathlib import Path

import websockets
from websockets.asyncio.server import ServerConnection

from sms_bridge.router.message_router import DeviceConnection, MessageRouter

log = logging.getLogger(__name__)


class WebSocketServer:
    def __init__(
        self,
        router: MessageRouter,
        port: int,
        api_key: str,
        tls_cert_path: str = "",
        tls_key_path: str = "",
    ):
        self.router = router
        self.port = port
        self.api_key = api_key
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        if not (self.tls_cert_path and self.tls_key_path):
            return None
        cert = Path(self.tls_cert_path)
        key = Path(self.tls_key_path)
        if not cert.exists() or not key.exists():
            log.warning(
                "TLS cert or key file not found — falling back to plain ws://. "
                f"cert={self.tls_cert_path} key={self.tls_key_path}"
            )
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        return ctx

    async def serve(self):
        ssl_ctx = self._build_ssl_context()
        scheme = "wss" if ssl_ctx else "ws"
        log.info(f"WebSocket server listening on {scheme}://0.0.0.0:{self.port}")
        async with websockets.serve(self._handle, "0.0.0.0", self.port, ssl=ssl_ctx):
            await asyncio.get_running_loop().create_future()  # run forever

    async def _handle(self, ws: ServerConnection):
        # Authenticate via Authorization header
        auth = ws.request.headers.get("Authorization", "")
        if auth != f"Bearer {self.api_key}":
            await ws.close(1008, "Unauthorized")
            log.warning(f"Rejected unauthenticated connection from {ws.remote_address}")
            return

        device_id = ws.request.headers.get("X-Device-ID", "unknown")
        log.info(f"Device connected: {device_id} from {ws.remote_address}")

        # Register device with router (send_fn allows router to push messages)
        async def send_fn(message: dict):
            await ws.send(json.dumps(message))

        try:
            async for raw in ws:
                await self._dispatch(raw, device_id, send_fn)
        except websockets.ConnectionClosed:
            log.info(f"Device disconnected: {device_id}")
        finally:
            self.router.unregister_device(device_id)

    async def _dispatch(self, raw: str, device_id: str, send_fn):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"Invalid JSON from {device_id}: {raw[:100]}")
            return

        msg_type = msg.get("type")

        if msg_type == "device.hello":
            conn = DeviceConnection(
                device_id=msg.get("device_id", device_id),
                device_name=msg.get("device_name", device_id),
                fcm_token=msg.get("fcm_token", ""),
                send_fn=send_fn,
            )
            self.router.register_device(conn)
            await self.router.handle_device_reconnect(conn.device_id)

        elif msg_type == "sms.received":
            await self.router.handle_incoming_sms(
                from_=msg["from"],
                body=msg["body"],
                device_id=msg.get("device_id", device_id),
            )

        elif msg_type == "sms.status":
            self.router.handle_sms_status(
                ref_id=msg["ref_id"],
                status=msg["status"],
                error=msg.get("error"),
            )

        elif msg_type == "pong":
            pass  # heartbeat response — no action needed

        else:
            log.warning(f"Unknown message type from {device_id}: {msg_type}")


