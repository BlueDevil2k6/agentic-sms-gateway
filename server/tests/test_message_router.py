"""
Tests for the message router.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sms_bridge.queue.file_queue import FileQueue
from sms_bridge.fcm.client import FcmClient
from sms_bridge.router.message_router import DeviceConnection, MessageRouter


@pytest.fixture
def queue(tmp_path):
    return FileQueue(data_dir=tmp_path)


@pytest.fixture
def fcm():
    mock = MagicMock(spec=FcmClient)
    mock.send_wake = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def router(queue, fcm):
    return MessageRouter(queue=queue, fcm=fcm)


def make_device(device_id="dev-1", fcm_token="token-abc"):
    send_fn = AsyncMock()
    return DeviceConnection(
        device_id=device_id,
        device_name="Test Phone",
        fcm_token=fcm_token,
        send_fn=send_fn,
    )


# ── Device lifecycle ──────────────────────────────────────────────────────────

def test_register_and_unregister_device(router):
    device = make_device()
    router.register_device(device)
    assert router.is_device_connected("dev-1")

    router.unregister_device("dev-1")
    assert not router.is_device_connected("dev-1")


def test_register_persists_fcm_token(router, tmp_path):
    device = make_device(fcm_token="my-fcm-token")
    router.register_device(device)

    # Token should be persisted to disk
    assert router._fcm_tokens.get("dev-1") == "my-fcm-token"
    assert (tmp_path / "fcm_tokens.json").exists()


def test_fcm_token_survives_disconnect(router):
    device = make_device(fcm_token="persistent-token")
    router.register_device(device)
    router.unregister_device("dev-1")

    # Token still available for wake-up after disconnect
    token = router._get_fcm_token("dev-1")
    assert token == "persistent-token"


def test_fcm_tokens_loaded_on_init(queue, fcm, tmp_path):
    # Pre-populate a token file
    import json
    (tmp_path / "fcm_tokens.json").write_text(json.dumps({"dev-saved": "saved-token"}))

    new_router = MessageRouter(queue=queue, fcm=fcm)
    assert new_router._get_fcm_token("dev-saved") == "saved-token"


def test_list_devices_shows_connected_and_offline(router):
    device = make_device(device_id="dev-1", fcm_token="t1")
    router.register_device(device)
    router._fcm_tokens["dev-offline"] = "t2"  # simulate previously seen device

    devices = router.list_devices()
    device_map = {d["device_id"]: d for d in devices}

    assert device_map["dev-1"]["connected"] is True
    assert device_map["dev-offline"]["connected"] is False


# ── Inbound ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_incoming_sms_notifies_agents(router):
    notifications = []

    async def notifier(msg):
        notifications.append(msg)

    router.register_mcp_notifier(notifier)
    await router.handle_incoming_sms(from_="+1111", body="Hello", device_id="dev-1")

    assert len(notifications) == 1
    assert notifications[0]["from"] == "+1111"
    assert notifications[0]["body"] == "Hello"


@pytest.mark.asyncio
async def test_incoming_sms_stored_then_marked_done(router, queue, tmp_path):
    await router.handle_incoming_sms(from_="+1111", body="Hi", device_id="dev-1")

    # Should end up in done/
    done = list((tmp_path / "inbound" / "done").glob("*.json"))
    assert len(done) == 1


# ── Outbound ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_sms_dispatches_immediately_when_connected(router):
    device = make_device()
    router.register_device(device)

    result = await router.send_sms(to="+2222", body="Test", device_id="dev-1")
    assert "message_id" in result

    # Device's send_fn should have been called with sms.send
    device.send_fn.assert_awaited_once()
    call_args = device.send_fn.call_args[0][0]
    assert call_args["type"] == "sms.send"
    assert call_args["to"] == "+2222"


@pytest.mark.asyncio
async def test_send_sms_triggers_fcm_when_disconnected(router, fcm):
    # Register token but no live connection
    router._fcm_tokens["dev-1"] = "fcm-token-xyz"

    await router.send_sms(to="+2222", body="Test", device_id="dev-1")

    fcm.send_wake.assert_awaited_once_with("fcm-token-xyz")


@pytest.mark.asyncio
async def test_send_sms_warns_when_no_fcm_token(router, fcm):
    # No device, no token
    result = await router.send_sms(to="+2222", body="Test", device_id="dev-unknown")

    # Message still queued even though we can't wake
    assert "message_id" in result
    fcm.send_wake.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_reconnect_flushes_queue(router, queue):
    # Queue two messages while device is offline
    queue.enqueue_outbound(to="+1111", body="msg1", device_id="dev-1")
    queue.enqueue_outbound(to="+2222", body="msg2", device_id="dev-1")

    # Device connects
    device = make_device()
    router.register_device(device)
    await router.handle_device_reconnect("dev-1")

    # Both messages should have been dispatched
    assert device.send_fn.await_count == 2


# ── Delivery status ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_sent_marks_done(router, tmp_path):
    device = make_device()
    router.register_device(device)
    result = await router.send_sms(to="+1111", body="hi", device_id="dev-1")

    router.handle_sms_status(ref_id=result["message_id"], status="sent")

    done = list((tmp_path / "outbound" / "done").glob("*.json"))
    assert len(done) == 1


@pytest.mark.asyncio
async def test_status_failed_retries(router, tmp_path):
    device = make_device()
    router.register_device(device)
    result = await router.send_sms(to="+1111", body="hi", device_id="dev-1")

    router.handle_sms_status(
        ref_id=result["message_id"],
        status="failed",
        error="no signal",
    )

    # Should be back in pending for retry
    pending = list((tmp_path / "outbound" / "pending").glob("*.json"))
    assert len(pending) == 1
