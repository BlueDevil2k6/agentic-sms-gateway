"""
CLI config store — persists configuration to ~/.config/sms-bridge/config.json.

The file is readable only by the current user (chmod 600) because it contains
the API key.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from sms_bridge.config import Config

_CONFIG_DIR  = Path.home() / ".config" / "sms-bridge"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def generate_api_key() -> str:
    return "sk-bridge-" + secrets.token_urlsafe(24)


class ConfigStore:
    def __init__(self, path: Path = _CONFIG_FILE) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> Config | None:
        """Return a Config loaded from disk, or None if no config file exists."""
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text())
            return Config.from_dict(data)
        except Exception:
            return None

    def load_raw(self) -> dict | None:
        """Return the raw config dict, or None."""
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return None

    def save(self, cfg: Config) -> None:
        """Write config to disk with user-only permissions."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(cfg.to_dict(), indent=2))
        self.path.chmod(0o600)

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()
