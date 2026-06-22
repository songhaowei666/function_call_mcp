"""MCP 长连接管理，供 agent 等运行时复用。"""

from __future__ import annotations

from contextlib import AsyncExitStack, suppress
from typing import Any

from mcp import ClientSession

from .discover import discover_capabilities
from .transport import connection_display, open_session
from .types import ServerCapabilities, ServerConfig, TransportType


class MCPConnection:
    """单个 MCP Server 的长连接句柄。"""

    def __init__(
        self,
        name: str,
        stack: AsyncExitStack,
        session: ClientSession,
        transport: TransportType,
        cfg: ServerConfig,
    ) -> None:
        self.name = name
        self.stack = stack
        self.session = session
        self.transport = transport
        self.cfg = cfg
        self._closed = False

    async def discover(self) -> ServerCapabilities:
        """发现当前连接上的能力。"""
        return await discover_capabilities(self.session)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用 MCP 工具。"""
        return await self.session.call_tool(name, arguments=arguments or {})

    async def read_resource(self, uri: str) -> Any:
        """读取 MCP 资源。"""
        return await self.session.read_resource(uri)

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """获取 MCP Prompt 模板。"""
        return await self.session.get_prompt(name, arguments=arguments or {})

    async def close(self) -> None:
        """释放连接资源。"""
        if self._closed:
            return
        self._closed = True
        with suppress(Exception):
            await self.stack.aclose()

    @property
    def display(self) -> dict[str, Any]:
        """连接展示信息。"""
        info = connection_display(self.cfg, self.transport)
        return {
            "name": self.name,
            "transport": self.transport,
            **info,
        }

    async def __aenter__(self) -> MCPConnection:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


async def connect_server(cfg: ServerConfig) -> MCPConnection:
    """建立单个 MCP Server 长连接。"""
    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        session, transport = await open_session(stack, cfg)
    except Exception:
        with suppress(Exception):
            await stack.aclose()
        raise
    return MCPConnection(cfg.name, stack, session, transport, cfg)


async def connect_servers(
    servers: dict[str, ServerConfig],
) -> dict[str, MCPConnection]:
    """批量建立 MCP 长连接，单点失败不影响其他 Server。"""
    connections: dict[str, MCPConnection] = {}
    for name, cfg in servers.items():
        try:
            connections[name] = await connect_server(cfg)
        except Exception:
            continue
    return connections


async def close_connections(connections: dict[str, MCPConnection]) -> None:
    """关闭一批 MCP 长连接。"""
    for connection in connections.values():
        await connection.close()
