"""
Configuration dataclass — can be loaded from environment variables, a .env file,
or the CLI config store (~/.config/sms-bridge/config.json).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


SMS_GATEWAY_DIR  = Path.home() / ".sms-gateway"
DEFAULT_DATA_DIR = SMS_GATEWAY_DIR / "data"


@dataclass
class Config:
    # Required
    api_key: str

    # Ports
    mcp_port: int = 8080
    ws_port: int = 8765

    # Public WebSocket URL embedded in the Android device pairing QR code.
    # Must be the externally reachable address of this server.
    ws_url: str = ""

    # FCM
    fcm_service_account_path: str = ""

    # Message queue
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)
    message_retention_days: int = 7
    max_send_attempts: int = 5

    # Logging
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if not isinstance(self.data_dir, Path):
            self.data_dir = Path(self.data_dir)
        # Auto-derive ws_url if not explicitly set
        if not self.ws_url:
            self.ws_url = f"ws://localhost:{self.ws_port}"

    # ── Loaders ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> Config:
        """Load from environment variables / .env file."""
        from dotenv import load_dotenv
        load_dotenv()
        return cls(
            api_key=os.environ["API_KEY"],
            mcp_port=int(os.getenv("MCP_PORT", "8080")),
            ws_port=int(os.getenv("WS_PORT", "8765")),
            ws_url=os.getenv("WS_URL", ""),
            fcm_service_account_path=os.getenv("FCM_SERVICE_ACCOUNT_PATH", ""),
            data_dir=Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR))),
            message_retention_days=int(os.getenv("MESSAGE_RETENTION_DAYS", "7")),
            max_send_attempts=int(os.getenv("MAX_SEND_ATTEMPTS", "5")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    @classmethod
    def from_dict(cls, d: dict) -> Config:
        """Load from a dictionary (CLI config store JSON)."""
        return cls(
            api_key=d["api_key"],
            mcp_port=int(d.get("mcp_port", 8080)),
            ws_port=int(d.get("ws_port", 8765)),
            ws_url=d.get("ws_url", ""),
            fcm_service_account_path=d.get("fcm_service_account_path", ""),
            data_dir=Path(d.get("data_dir", str(DEFAULT_DATA_DIR))),
            message_retention_days=int(d.get("message_retention_days", 7)),
            max_send_attempts=int(d.get("max_send_attempts", 5)),
            log_level=d.get("log_level", "INFO"),
        )

    def to_dict(self) -> dict:
        """Serialise to a dictionary for storage."""
        return {
            "api_key": self.api_key,
            "mcp_port": self.mcp_port,
            "ws_port": self.ws_port,
            "ws_url": self.ws_url,
            "fcm_service_account_path": self.fcm_service_account_path,
            "data_dir": str(self.data_dir),
            "message_retention_days": self.message_retention_days,
            "max_send_attempts": self.max_send_attempts,
            "log_level": self.log_level,
        }
