"""MCP 传输层：stdio / sse / streamableHttp。"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import build_stdio_env
from .types import ServerConfig, TransportType


async def probe_http_url(url: str, timeout: float = 3.0) -> bool:
    """探测 HTTP MCP 端点端口是否可达。"""
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=0.2)
        except (OSError, asyncio.TimeoutError):
            pass
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def validate_server_config(cfg: ServerConfig) -> TransportType:
    """校验配置完整性并返回传输类型。"""
    transport = cfg.resolved_transport()
    if transport is None:
        raise ValueError(
            f"MCP Server '{cfg.name}' 缺少有效连接配置（需要 command 或 url）"
        )
    if transport == "stdio" and not cfg.command:
        raise ValueError(f"MCP Server '{cfg.name}' 使用 stdio 传输但缺少 command")
    if transport in {"sse", "streamableHttp"} and not cfg.url:
        raise ValueError(f"MCP Server '{cfg.name}' 使用 {transport} 传输但缺少 url")
    return transport


async def open_session(
    stack: AsyncExitStack,
    cfg: ServerConfig,
) -> tuple[ClientSession, TransportType]:
    """在已有 AsyncExitStack 上建立 MCP ClientSession。"""
    transport = validate_server_config(cfg)

    if transport == "stdio":
        params = StdioServerParameters(
            command=cfg.command,
            args=cfg.args,
            env=build_stdio_env(cfg),
            cwd=cfg.cwd or None,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
    elif transport == "sse":
        if not await probe_http_url(cfg.url):
            raise ConnectionError(f"MCP Server '{cfg.name}' 的 URL 不可达: {cfg.url}")

        def httpx_client_factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            merged_headers = {
                "Accept": "application/json, text/event-stream",
                **cfg.headers,
                **(headers or {}),
            }
            return httpx.AsyncClient(
                headers=merged_headers or None,
                follow_redirects=True,
                timeout=timeout,
                auth=auth,
            )

        read, write = await stack.enter_async_context(
            sse_client(cfg.url, httpx_client_factory=httpx_client_factory)
        )
    else:
        if not await probe_http_url(cfg.url):
            raise ConnectionError(f"MCP Server '{cfg.name}' 的 URL 不可达: {cfg.url}")

        http_client = await stack.enter_async_context(
            httpx.AsyncClient(
                headers=cfg.headers or None,
                follow_redirects=True,
                timeout=None,
            )
        )
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(cfg.url, http_client=http_client)
        )

    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session, transport


def connection_display(cfg: ServerConfig, transport: TransportType) -> dict[str, Any]:
    """返回用于展示/序列化的连接信息。"""
    if transport == "stdio":
        return {
            "command": cfg.command,
            "args": cfg.args,
            "url": None,
        }
    return {
        "command": None,
        "args": [],
        "url": cfg.url,
    }
