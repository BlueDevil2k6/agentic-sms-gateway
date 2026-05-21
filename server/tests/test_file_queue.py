"""
Tests for the file-based message queue.
"""

import json
import time
import pytest
from pathlib import Path

from sms_bridge.queue.file_queue import FileQueue


@pytest.fixture
def queue(tmp_path):
    """Fresh queue backed by a temp directory for each test."""
    return FileQueue(data_dir=tmp_path)


# ── Outbound ──────────────────────────────────────────────────────────────────

def test_enqueue_outbound_creates_file(queue, tmp_path):
    msg = queue.enqueue_outbound(to="+14155551234", body="Hello", device_id="dev-1")
    pending = list((tmp_path / "outbound" / "pending").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text())
    assert data["to"] == "+14155551234"
    assert data["body"] == "Hello"
    assert data["id"] == msg["id"]


def test_claim_next_outbound_is_atomic(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="msg1", device_id="dev-1")
    queue.enqueue_outbound(to="+2222", body="msg2", device_id="dev-1")

    claimed = queue.claim_next_outbound("dev-1")
    assert claimed is not None
    assert claimed["body"] == "msg1"  # FIFO — oldest first

    sending = list((tmp_path / "outbound" / "sending").glob("*.json"))
    pending = list((tmp_path / "outbound" / "pending").glob("*.json"))
    assert len(sending) == 1
    assert len(pending) == 1


def test_claim_returns_none_when_empty(queue):
    assert queue.claim_next_outbound("dev-1") is None


def test_claim_respects_device_id(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="for dev-1", device_id="dev-1")
    queue.enqueue_outbound(to="+2222", body="for dev-2", device_id="dev-2")

    claimed = queue.claim_next_outbound("dev-2")
    assert claimed["body"] == "for dev-2"

    # dev-1 message still in pending
    pending = list((tmp_path / "outbound" / "pending").glob("*.json"))
    assert len(pending) == 1


def test_claim_any_device_id(queue):
    queue.enqueue_outbound(to="+1111", body="any", device_id="any")
    claimed = queue.claim_next_outbound("dev-99")
    assert claimed is not None
    assert claimed["body"] == "any"


def test_mark_outbound_sent_moves_to_done(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="hi", device_id="dev-1")
    claimed = queue.claim_next_outbound("dev-1")
    queue.mark_outbound_sent(claimed["id"])

    assert len(list((tmp_path / "outbound" / "done").glob("*.json"))) == 1
    assert len(list((tmp_path / "outbound" / "sending").glob("*.json"))) == 0


def test_mark_outbound_failed_retries_then_dead_letters(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="hi", device_id="dev-1")

    # Exhaust all attempts
    for _ in range(5):
        claimed = queue.claim_next_outbound("dev-1")
        assert claimed is not None
        queue.mark_outbound_failed(claimed["id"], "network error")

    # Should now be in failed/
    assert len(list((tmp_path / "outbound" / "failed").glob("*.json"))) == 1
    assert len(list((tmp_path / "outbound" / "pending").glob("*.json"))) == 0


# ── Inbound ───────────────────────────────────────────────────────────────────

def test_store_inbound_creates_file(queue, tmp_path):
    msg = queue.store_inbound(from_="+14155551234", body="Hey", device_id="dev-1")
    pending = list((tmp_path / "inbound" / "pending").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text())
    assert data["from"] == "+14155551234"
    assert data["id"] == msg["id"]


def test_inbound_processing_flow(queue, tmp_path):
    msg = queue.store_inbound(from_="+1111", body="hello", device_id="dev-1")
    queue.claim_inbound_for_processing(msg["id"])

    assert len(list((tmp_path / "inbound" / "processing").glob("*.json"))) == 1
    assert len(list((tmp_path / "inbound" / "pending").glob("*.json"))) == 0

    queue.mark_inbound_done(msg["id"])
    assert len(list((tmp_path / "inbound" / "done").glob("*.json"))) == 1
    assert len(list((tmp_path / "inbound" / "processing").glob("*.json"))) == 0


# ── Queries ───────────────────────────────────────────────────────────────────

def test_get_messages_filters_by_number(queue):
    queue.store_inbound(from_="+1111", body="from 1111", device_id="dev-1")
    queue.store_inbound(from_="+2222", body="from 2222", device_id="dev-1")

    results = queue.get_messages(from_number="+1111")
    assert len(results) == 1
    assert results[0]["body"] == "from 1111"


def test_list_conversations_groups_by_contact(queue):
    queue.store_inbound(from_="+1111", body="msg1", device_id="dev-1")
    queue.store_inbound(from_="+1111", body="msg2", device_id="dev-1")
    queue.store_inbound(from_="+2222", body="msg3", device_id="dev-1")

    convos = queue.list_conversations()
    assert len(convos) == 2
    contacts = {c["contact"] for c in convos}
    assert contacts == {"+1111", "+2222"}


# ── Cleanup ───────────────────────────────────────────────────────────────────

def test_cleanup_deletes_old_done_messages(queue, tmp_path):
    msg = queue.store_inbound(from_="+1111", body="old", device_id="dev-1")
    queue.claim_inbound_for_processing(msg["id"])
    queue.mark_inbound_done(msg["id"])

    # Backdate the file's mtime to 8 days ago
    done_file = next((tmp_path / "inbound" / "done").glob("*.json"))
    old_time = time.time() - (8 * 86400)
    import os
    os.utime(done_file, (old_time, old_time))

    queue._cleanup(retention_days=7)
    assert len(list((tmp_path / "inbound" / "done").glob("*.json"))) == 0


def test_cleanup_expires_stuck_pending_to_failed(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="stuck", device_id="dev-1")

    # Backdate to 8 days ago
    pending_file = next((tmp_path / "outbound" / "pending").glob("*.json"))
    old_time = time.time() - (8 * 86400)
    import os
    os.utime(pending_file, (old_time, old_time))

    queue._cleanup(retention_days=7)
    assert len(list((tmp_path / "outbound" / "failed").glob("*.json"))) == 1
    assert len(list((tmp_path / "outbound" / "pending").glob("*.json"))) == 0


def test_cleanup_never_deletes_failed(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="stuck", device_id="dev-1")
    pending_file = next((tmp_path / "outbound" / "pending").glob("*.json"))

    # Age it past retention
    old_time = time.time() - (10 * 86400)
    import os
    os.utime(pending_file, (old_time, old_time))
    queue._cleanup(retention_days=7)

    # Now age the failed file too
    failed_file = next((tmp_path / "outbound" / "failed").glob("*.json"))
    os.utime(failed_file, (old_time, old_time))
    queue._cleanup(retention_days=7)

    # Failed messages must never be auto-deleted
    assert len(list((tmp_path / "outbound" / "failed").glob("*.json"))) == 1


# ── Crash recovery ────────────────────────────────────────────────────────────

def test_recover_on_startup_rescues_sending(queue, tmp_path):
    queue.enqueue_outbound(to="+1111", body="in-flight", device_id="dev-1")
    queue.claim_next_outbound("dev-1")  # moves to sending/

    # Simulate crash: sending/ still has the file
    assert len(list((tmp_path / "outbound" / "sending").glob("*.json"))) == 1

    queue.recover_on_startup()

    # Should be back in pending/ (attempt count incremented)
    pending = list((tmp_path / "outbound" / "pending").glob("*.json"))
    assert len(pending) == 1
    data = json.loads(pending[0].read_text())
    assert data["attempts"] == 1
