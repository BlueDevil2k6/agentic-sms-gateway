"""
Configuration — loaded from environment variables / .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Authentication
    API_KEY: str = os.environ["API_KEY"]

    # Server ports
    MCP_PORT: int = int(os.getenv("MCP_PORT", "8080"))
    WS_PORT: int = int(os.getenv("WS_PORT", "8765"))

    # Public WebSocket URL embedded in the setup QR code.
    # Must be the externally reachable address of this server.
    # Defaults to localhost for local development.
    WS_URL: str = os.getenv("WS_URL", f"ws://localhost:{int(os.getenv('WS_PORT', '8765'))}")

    # FCM
    FCM_SERVICE_ACCOUNT_PATH: str = os.getenv(
        "FCM_SERVICE_ACCOUNT_PATH", "/secrets/fcm-service-account.json"
    )

    # Message queue
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data"))
    MESSAGE_RETENTION_DAYS: int = int(os.getenv("MESSAGE_RETENTION_DAYS", "7"))
    MAX_SEND_ATTEMPTS: int = int(os.getenv("MAX_SEND_ATTEMPTS", "5"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()
