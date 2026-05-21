"""
Entry point — starts the WebSocket server, MCP server, and cleanup scheduler.
"""

import asyncio
import logging

from sms_bridge.config import config
from sms_bridge.queue.file_queue import FileQueue
from sms_bridge.router.message_router import MessageRouter
from sms_bridge.websocket.server import WebSocketServer
from sms_bridge.mcp.server import MCPServer
from sms_bridge.fcm.client import FcmClient

logging.basicConfig(level=config.LOG_LEVEL)
log = logging.getLogger(__name__)


async def run():
    log.info("Starting Agentic SMS Gateway v0.1.0")

    # Initialise components
    queue = FileQueue(data_dir=config.DATA_DIR)
    queue.recover_on_startup()  # rescue any in-flight messages from a previous crash

    fcm = FcmClient(service_account_path=config.FCM_SERVICE_ACCOUNT_PATH)
    router = MessageRouter(queue=queue, fcm=fcm)

    ws_server = WebSocketServer(
        router=router,
        port=config.WS_PORT,
        api_key=config.API_KEY,
    )
    mcp_server = MCPServer(
        router=router,
        port=config.MCP_PORT,
        api_key=config.API_KEY,
    )

    # Run all servers concurrently
    await asyncio.gather(
        ws_server.serve(),
        mcp_server.serve(),
        queue.run_cleanup_scheduler(retention_days=config.MESSAGE_RETENTION_DAYS),
    )


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
