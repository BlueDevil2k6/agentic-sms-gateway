"""
Message Router — coordinates between the WebSocket server, MCP server,
FCM client, and file queue.
"""

import logging
from typing import Callable

from sms_bridge.queue.file_queue import FileQueue
from sms_bridge.fcm.client import FcmClient

log = logging.getLogger(__name__)


class DeviceConnection:
    """Represents a connected Android device."""
    def __init__(self, device_id: str, device_name: str, fcm_token: str, send_fn: Callable):
        self.device_id = device_id
        self.device_name = device_name
        self.fcm_token = fcm_token
        self.send_fn = send_fn  # async callable: send_fn(message: dict) -> None


class MessageRouter:
    def __init__(self, queue: FileQueue, fcm: FcmClient):
        self.queue = queue
        self.fcm = fcm
        self._devices: dict[str, DeviceConnection] = {}       # device_id → connection
        self._mcp_notifiers: list[Callable] = []              # MCP notification callbacks

    # ── Device lifecycle ─────────────────────────────────────────────────────

    def register_device(self, connection: DeviceConnection):
        """Called when an Android device connects and sends device.hello."""
        self._devices[connection.device_id] = connection
        log.info(f"Device registered: {connection.device_id} ({connection.device_name})")

    def unregister_device(self, device_id: str):
        """Called when an Android device disconnects."""
        self._devices.pop(device_id, None)
        log.info(f"Device disconnected: {device_id}")

    def is_device_connected(self, device_id: str) -> bool:
        return device_id in self._devices

    # ── Inbound (Android → Gateway → Agent) ─────────────────────────────────

    async def handle_incoming_sms(self, from_: str, body: str, device_id: str):
        """
        Called when Android sends sms.received over WebSocket.
        Stores to inbound/pending/ then notifies connected MCP agents.
        """
        msg = self.queue.store_inbound(from_=from_, body=body, device_id=device_id)
        self.queue.claim_inbound_for_processing(msg["id"])
        await self._notify_agents(msg)
        self.queue.mark_inbound_done(msg["id"])

    def register_mcp_notifier(self, callback: Callable):
        """MCP server registers a callback to receive inbound SMS notifications."""
        self._mcp_notifiers.append(callback)

    def unregister_mcp_notifier(self, callback: Callable):
        self._mcp_notifiers.remove(callback)

    async def _notify_agents(self, msg: dict):
        for notifier in self._mcp_notifiers:
            try:
                await notifier(msg)
            except Exception as e:
                log.warning(f"MCP notifier error: {e}")

    # ── Outbound (Agent → Gateway → Android) ────────────────────────────────

    async def send_sms(self, to: str, body: str, device_id: str = "any") -> dict:
        """
        Called by MCP send_sms tool.
        Queues the message and dispatches it to the device immediately if connected,
        or via FCM wake-up if not.
        """
        msg = self.queue.enqueue_outbound(to=to, body=body, device_id=device_id)

        # Resolve target device
        target_id = device_id if device_id != "any" else self._first_connected_device()

        if target_id and self.is_device_connected(target_id):
            await self._dispatch_to_device(target_id, msg)
        else:
            await self._wake_via_fcm(device_id, msg)

        return {"message_id": msg["id"], "status": "queued"}

    async def _dispatch_to_device(self, device_id: str, msg: dict):
        """Push sms.send command to the connected Android device."""
        claimed = self.queue.claim_next_outbound(device_id)
        if not claimed:
            return
        device = self._devices[device_id]
        await device.send_fn({
            "type": "sms.send",
            "id": claimed["id"],
            "to": claimed["to"],
            "body": claimed["body"],
        })
        log.info(f"Dispatched outbound {claimed['id']} to device {device_id}")

    async def _wake_via_fcm(self, device_id: str, msg: dict):
        """
        Device WebSocket is not open. Send an FCM high-priority push to wake the app.
        The device will reconnect via WebSocket and the pending message will be dispatched
        in handle_device_reconnect().
        """
        # Look up FCM token from last known registration
        token = self._get_fcm_token(device_id)
        if token:
            await self.fcm.send_wake(token)
            log.info(f"FCM wake sent to device {device_id} for message {msg['id']}")
        else:
            log.warning(f"No FCM token for device {device_id} — message {msg['id']} will wait in queue")

    async def handle_device_reconnect(self, device_id: str):
        """
        Called when a device reconnects (after FCM wake or network recovery).
        Flushes any pending outbound messages for this device.
        """
        while msg := self.queue.claim_next_outbound(device_id):
            device = self._devices.get(device_id)
            if not device:
                break
            await device.send_fn({
                "type": "sms.send",
                "id": msg["id"],
                "to": msg["to"],
                "body": msg["body"],
            })
            log.info(f"Flushed queued message {msg['id']} to {device_id}")

    # ── Delivery status ──────────────────────────────────────────────────────

    def handle_sms_status(self, ref_id: str, status: str, error: str | None = None):
        """Called when Android reports delivery status via sms.status WebSocket event."""
        if status in ("sent", "delivered"):
            self.queue.mark_outbound_sent(ref_id)
        else:
            self.queue.mark_outbound_failed(ref_id, error or "unknown error")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _first_connected_device(self) -> str | None:
        return next(iter(self._devices), None)

    def _get_fcm_token(self, device_id: str) -> str | None:
        # TODO: persist FCM tokens to disk so they survive server restarts
        device = self._devices.get(device_id)
        return device.fcm_token if device else None

    def list_devices(self) -> list[dict]:
        return [
            {
                "device_id": d.device_id,
                "name": d.device_name,
                "connected": True,
            }
            for d in self._devices.values()
        ]
