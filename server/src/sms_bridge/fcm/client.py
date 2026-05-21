"""
FCM client — sends high-priority wake-up pushes to Android devices.

FCM payloads carry ONLY a wake signal. No SMS content is sent through
Google's infrastructure.
"""

import logging

log = logging.getLogger(__name__)


class FcmClient:
    def __init__(self, service_account_path: str):
        self._app = None
        self._service_account_path = service_account_path
        self._init()

    def _init(self):
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
                android=messaging.AndroidConfig(
                    priority="high",
                ),
                data={
                    "action": "wake_connect",
                },
            )
            response = messaging.send(message)
            log.info(f"FCM wake sent: {response}")
            return True
        except Exception as e:
            log.error(f"FCM send failed: {e}")
            return False
