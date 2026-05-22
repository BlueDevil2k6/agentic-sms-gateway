"""
Entry point — starts the WebSocket server, MCP server, and cleanup scheduler.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sms_bridge.config import Config
from sms_bridge.queue.file_queue import FileQueue
from sms_bridge.router.message_router import MessageRouter
from sms_bridge.websocket.server import WebSocketServer
from sms_bridge.mcp.server import MCPServer
from sms_bridge.fcm.client import FcmClient


async def run(cfg: Config) -> None:
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger(__name__)
    log.info("Starting Agentic SMS Gateway v0.1.4")
    log.info("  MCP  → http://0.0.0.0:%d/mcp", cfg.mcp_port)
    log.info("  WS   → %s", cfg.ws_url)
    log.info("  Data → %s", cfg.data_dir)

    queue = FileQueue(data_dir=cfg.data_dir)
    queue.recover_on_startup()

    fcm = FcmClient(service_account_path=cfg.fcm_service_account_path)
    router = MessageRouter(queue=queue, fcm=fcm)

    ws_server = WebSocketServer(
        router=router,
        port=cfg.ws_port,
        api_key=cfg.api_key,
    )
    mcp_server = MCPServer(
        router=router,
        port=cfg.mcp_port,
        api_key=cfg.api_key,
        ws_url=cfg.ws_url,
    )

    await asyncio.gather(
        ws_server.serve(),
        mcp_server.serve(),
        queue.run_cleanup_scheduler(retention_days=cfg.message_retention_days),
    )


def _load_config() -> Config:
    """
    Config resolution order:
      1. CLI config store  (~/.config/sms-bridge/config.json)
      2. Environment variables / .env file
    """
    from sms_bridge.config_store import ConfigStore
    cfg = ConfigStore().load()
    if cfg is not None:
        return cfg
    try:
        return Config.from_env()
    except KeyError:
        print(
            "Error: no configuration found.\n"
            "Run  sms-bridge setup  to configure the server.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """Legacy entry point — also called by `sms-bridge start`."""
    asyncio.run(run(_load_config()))


if __name__ == "__main__":
    main()
