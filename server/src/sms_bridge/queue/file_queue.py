"""
File-based message queue.

Messages are stored as JSON files. State transitions use os.rename()
which is atomic on POSIX filesystems — a message cannot be claimed twice.

Directory layout:
  data/
  ├── outbound/
  │   ├── pending/      Queued by agent, waiting for Android
  │   ├── sending/      Android received it, SMS dispatch in progress
  │   ├── done/         Confirmed sent — deleted after retention period
  │   └── failed/       Max retries exceeded — never auto-deleted
  └── inbound/
      ├── pending/      Received from Android, agent not yet notified
      ├── processing/   MCP notification in flight
      ├── done/         Agent acknowledged — deleted after retention period
      └── failed/       Agent never consumed — never auto-deleted
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

OUTBOUND_STATES = ["pending", "sending", "done", "failed"]
INBOUND_STATES  = ["pending", "processing", "done", "failed"]


class FileQueue:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._init_dirs()

    # ── Initialisation ──────────────────────────────────────────────────────

    def _init_dirs(self):
        for state in OUTBOUND_STATES:
            (self.data_dir / "outbound" / state).mkdir(parents=True, exist_ok=True)
        for state in INBOUND_STATES:
            (self.data_dir / "inbound" / state).mkdir(parents=True, exist_ok=True)

    def recover_on_startup(self):
        """
        On startup, move any messages stuck in transient states back to
        pending (they were in-flight when the server last crashed).
        """
        for stuck in (self.data_dir / "outbound" / "sending").glob("*.json"):
            self._increment_attempts_and_requeue("outbound", stuck)

        for stuck in (self.data_dir / "inbound" / "processing").glob("*.json"):
            dest = self.data_dir / "inbound" / "pending" / stuck.name
            os.rename(stuck, dest)
            log.info(f"Recovered inbound message {stuck.name} → pending")

    # ── Outbound (agent → Android → external) ───────────────────────────────

    def enqueue_outbound(self, to: str, body: str, device_id: str = "any") -> dict:
        """Called by MCP send_sms tool. Writes message to outbound/pending/."""
        msg = {
            "id": str(uuid.uuid4()),
            "created_at": _now_iso(),
            "created_ts": _now_ms(),
            "to": to,
            "body": body,
            "device_id": device_id,
            "attempts": 0,
            "max_attempts": 5,
            "last_attempt_at": None,
            "error": None,
        }
        self._write("outbound", "pending", msg)
        log.info(f"Enqueued outbound {msg['id']} → {to}")
        return msg

    def claim_next_outbound(self, device_id: str) -> dict | None:
        """
        Atomically claims the next pending outbound message for a device.
        Returns the message dict or None if the queue is empty.
        """
        pending = self.data_dir / "outbound" / "pending"
        for filepath in sorted(pending.glob("*.json")):
            msg = json.loads(filepath.read_text())
            if msg["device_id"] not in (device_id, "any"):
                continue
            dest = self.data_dir / "outbound" / "sending" / filepath.name
            try:
                os.rename(filepath, dest)
                msg["last_attempt_at"] = _now_iso()
                dest.write_text(json.dumps(msg, indent=2))
                log.info(f"Claimed outbound {msg['id']} for device {device_id}")
                return msg
            except FileNotFoundError:
                continue  # another coroutine claimed it first
        return None

    def mark_outbound_sent(self, message_id: str):
        """Move outbound message from sending/ → done/."""
        self._move_by_id("outbound/sending", "outbound/done", message_id)
        log.info(f"Outbound {message_id} → done")

    def mark_outbound_failed(self, message_id: str, error: str):
        """Increment attempts. Retry (→ pending) or dead-letter (→ failed)."""
        src = self._find_by_id("outbound/sending", message_id)
        if not src:
            log.warning(f"mark_outbound_failed: {message_id} not found in sending/")
            return
        self._increment_attempts_and_requeue("outbound", src, error=error)

    # ── Inbound (external → Android → gateway → agent) ──────────────────────

    def store_inbound(self, from_: str, body: str, device_id: str) -> dict:
        """Called when Android sends sms.received. Writes to inbound/pending/."""
        msg = {
            "id": str(uuid.uuid4()),
            "received_at": _now_iso(),
            "received_ts": _now_ms(),
            "from": from_,
            "body": body,
            "device_id": device_id,
        }
        self._write("inbound", "pending", msg)
        log.info(f"Stored inbound {msg['id']} from {from_}")
        return msg

    def claim_inbound_for_processing(self, message_id: str) -> dict | None:
        """Move inbound message from pending/ → processing/ (MCP notification in flight)."""
        src = self._find_by_id("inbound/pending", message_id)
        if not src:
            return None
        dest = self.data_dir / "inbound" / "processing" / src.name
        os.rename(src, dest)
        return json.loads(dest.read_text())

    def mark_inbound_done(self, message_id: str):
        """Agent acknowledged the message. Move processing/ → done/."""
        self._move_by_id("inbound/processing", "inbound/done", message_id)
        log.info(f"Inbound {message_id} → done")

    # ── Queries (for MCP get_messages / list_conversations) ─────────────────

    def get_messages(self, from_number: str, limit: int = 20) -> list[dict]:
        """Return recent inbound messages from a specific number."""
        results = []
        for folder in ["pending", "processing", "done"]:
            for f in (self.data_dir / "inbound" / folder).glob("*.json"):
                msg = json.loads(f.read_text())
                if msg["from"] == from_number:
                    results.append({**msg, "direction": "inbound", "status": folder})
        # Also check outbound done for sent messages to this number
        for f in (self.data_dir / "outbound" / "done").glob("*.json"):
            msg = json.loads(f.read_text())
            if msg["to"] == from_number:
                results.append({**msg, "direction": "outbound", "status": "done"})
        results.sort(key=lambda m: m.get("received_ts") or m.get("created_ts", 0), reverse=True)
        return results[:limit]

    def list_conversations(self, limit: int = 20) -> list[dict]:
        """Return recent conversations grouped by contact number."""
        contacts: dict[str, dict] = {}
        for folder in ["pending", "processing", "done"]:
            for f in sorted((self.data_dir / "inbound" / folder).glob("*.json")):
                msg = json.loads(f.read_text())
                number = msg["from"]
                if number not in contacts:
                    contacts[number] = {
                        "contact": number,
                        "last_message": msg["body"],
                        "last_message_at": msg["received_at"],
                        "direction": "inbound",
                        "unread": folder == "pending",
                    }
        return sorted(contacts.values(), key=lambda c: c["last_message_at"], reverse=True)[:limit]

    # ── Cleanup ──────────────────────────────────────────────────────────────

    async def run_cleanup_scheduler(self, retention_days: int):
        """Runs cleanup once daily."""
        while True:
            self._cleanup(retention_days)
            await asyncio.sleep(86_400)  # 24 hours

    def _cleanup(self, retention_days: int):
        cutoff = time.time() - (retention_days * 86_400)
        deleted = 0
        expired = 0

        # Delete completed messages older than retention period
        for folder in ["outbound/done", "inbound/done"]:
            for f in (self.data_dir / folder).glob("*.json"):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1

        # Expire stuck messages → failed/ (not deleted)
        for folder in ["outbound/pending", "outbound/sending",
                       "inbound/pending",  "inbound/processing"]:
            for f in (self.data_dir / folder).glob("*.json"):
                if f.stat().st_mtime < cutoff:
                    msg = json.loads(f.read_text())
                    msg["error"] = f"expired after {retention_days} days"
                    direction = folder.split("/")[0]
                    dest = self.data_dir / direction / "failed" / f.name
                    f.write_text(json.dumps(msg, indent=2))
                    os.rename(f, dest)
                    expired += 1

        log.info(f"Cleanup: deleted {deleted} completed, expired {expired} stuck messages")

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _write(self, direction: str, state: str, msg: dict):
        ts = msg.get("created_ts") or msg.get("received_ts") or _now_ms()
        filename = f"{ts}_{msg['id']}.json"
        path = self.data_dir / direction / state / filename
        path.write_text(json.dumps(msg, indent=2))

    def _find_by_id(self, rel_path: str, message_id: str) -> Path | None:
        for f in (self.data_dir / rel_path).glob("*.json"):
            if message_id in f.name:
                return f
        return None

    def _move_by_id(self, src_rel: str, dest_rel: str, message_id: str):
        src = self._find_by_id(src_rel, message_id)
        if src:
            dest = self.data_dir / dest_rel / src.name
            os.rename(src, dest)

    def _increment_attempts_and_requeue(self, direction: str, filepath: Path, error: str = "crash recovery"):
        msg = json.loads(filepath.read_text())
        msg["attempts"] = msg.get("attempts", 0) + 1
        msg["error"] = error
        dest_state = "failed" if msg["attempts"] >= msg.get("max_attempts", 5) else "pending"
        dest = self.data_dir / direction / dest_state / filepath.name
        filepath.write_text(json.dumps(msg, indent=2))
        os.rename(filepath, dest)
        log.info(f"Requeued {filepath.name} → {dest_state} (attempt {msg['attempts']})")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
