"""
MCP server — agent-facing.

Exposes SMS capabilities as MCP tools over SSE transport.
Agents connect to wss://your-server/mcp and discover tools automatically.
"""

import json
import logging

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp import types
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from sms_bridge.router.message_router import MessageRouter
from sms_bridge.mcp.qr import make_qr_route

log = logging.getLogger(__name__)


def build_mcp_app(router: MessageRouter, api_key: str, ws_url: str = "") -> Starlette:
    """Build and return the MCP Starlette ASGI app."""

    mcp = Server("agentic-sms-gateway")

    # ── Tool definitions ─────────────────────────────────────────────────────

    @mcp.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="send_sms",
                description="Send an SMS message via the connected Android device.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "to":        {"type": "string", "description": "Destination phone number in E.164 format e.g. +14155551234"},
                        "body":      {"type": "string", "description": "SMS message text"},
                        "device_id": {"type": "string", "description": "Target device ID (optional if only one device is connected)"},
                    },
                    "required": ["to", "body"],
                },
            ),
            types.Tool(
                name="get_messages",
                description="Retrieve recent SMS messages from a specific phone number.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "from_number": {"type": "string", "description": "Phone number in E.164 format"},
                        "limit":       {"type": "integer", "description": "Maximum messages to return (default 20, max 100)"},
                    },
                    "required": ["from_number"],
                },
            ),
            types.Tool(
                name="list_conversations",
                description="List recent SMS conversations grouped by contact.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum conversations to return (default 20)"},
                    },
                },
            ),
            types.Tool(
                name="list_devices",
                description="List connected Android devices and their status.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    # ── Tool handlers ────────────────────────────────────────────────────────

    @mcp.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if name == "send_sms":
            result = await router.send_sms(
                to=arguments["to"],
                body=arguments["body"],
                device_id=arguments.get("device_id", "any"),
            )
            return [types.TextContent(type="text", text=f"Queued: {result['message_id']}")]

        elif name == "get_messages":
            messages = router.queue.get_messages(
                from_number=arguments["from_number"],
                limit=min(arguments.get("limit", 20), 100),
            )
            return [types.TextContent(type="text", text=json.dumps(messages, indent=2))]

        elif name == "list_conversations":
            convos = router.queue.list_conversations(
                limit=arguments.get("limit", 20),
            )
            return [types.TextContent(type="text", text=json.dumps(convos, indent=2))]

        elif name == "list_devices":
            devices = router.list_devices()
            return [types.TextContent(type="text", text=json.dumps(devices, indent=2))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    # ── SSE transport ────────────────────────────────────────────────────────

    sse = SseServerTransport("/mcp/messages")

    async def handle_sse(request):
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {api_key}":
            return Response("Unauthorized", status_code=401)
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp.run(streams[0], streams[1], mcp.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    async def handle_health(request):
        return JSONResponse({"status": "ok", "devices_connected": len(router._devices)})

    return Starlette(routes=[
        Route("/mcp",          handle_sse,                       methods=["GET"]),
        Route("/mcp/messages", handle_messages,                  methods=["POST"]),
        Route("/health",       handle_health,                    methods=["GET"]),
        Route("/setup/qr",     make_qr_route(ws_url, api_key),   methods=["GET"]),
    ])


class MCPServer:
    def __init__(self, router: MessageRouter, port: int, api_key: str, ws_url: str = ""):
        self.router = router
        self.port = port
        self.api_key = api_key
        self.ws_url = ws_url

    async def serve(self):
        import uvicorn
        app = build_mcp_app(self.router, self.api_key, self.ws_url)
        log.info(f"MCP server listening on http://0.0.0.0:{self.port}/mcp")
        cfg = uvicorn.Config(app, host="0.0.0.0", port=self.port, log_level="info")
        server = uvicorn.Server(cfg)
        await server.serve()
