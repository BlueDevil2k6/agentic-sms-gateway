"""
FCM client — sends high-priority wake-up pushes to Android devices.

FCM payloads carry ONLY a wake signal. No SMS content is sent through
Google's infrastructure.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _is_stub(path: str) -> bool:
    """Return True if the service account file is the placeholder stub."""
    try:
        data = json.loads(Path(path).read_text())
        return bool(data.get("_stub")) or data.get("project_id") == "YOUR_PROJECT_ID"
    except Exception:
        return False


class FcmClient:
    def __init__(self, service_account_path: str):
        self._app = None
        self._service_account_path = service_account_path
        self._init()

    def _init(self):
        if not self._service_account_path:
            log.info("FCM service account not configured — wake-up pushes disabled")
            return

        if not Path(self._service_account_path).exists():
            log.warning(
                f"FCM service account file not found: {self._service_account_path} "
                "— wake-up pushes disabled"
            )
            return

        if _is_stub(self._service_account_path):
            log.info(
                "FCM service account is a placeholder stub — wake-up pushes disabled. "
                f"Replace {self._service_account_path} with your real Firebase credentials."
            )
            return

        try:
            import firebase_admin
            from firebase_admin import credentials
            cred = credentials.Certificate(self._service_account_path)
            self._app = firebase_admin.initialize_app(cred)
            log.info("FCM client initialised")
        except Exception as e:
            log.warning(f"FCM init failed — wake-up pushes will be unavailable: {e}")

    async def send_wake(self, fcm_token: str) -> bool:
        """
        Send a high-priority FCM data message to wake the Android app.
        Returns True on success, False on failure.
        """
        if not self._app:
            log.warning("FCM not available — skipping wake push")
            return False

        try:
            from firebase_admin import messaging
            message = messaging.Message(
                token=fcm_token,
                android=messaging.AndroidConfig(priority="high"),
                data={"action": "wake_connect"},
            )
            response = messaging.send(message)
            log.info(f"FCM wake sent: {response}")
            return True
        except Exception as e:
            log.error(f"FCM send failed: {e}")
            return False
