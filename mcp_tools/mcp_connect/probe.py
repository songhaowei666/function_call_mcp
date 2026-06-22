"""MCP 短连接探测，供 CLI 与诊断使用。"""

from __future__ import annotations

from contextlib import AsyncExitStack, suppress

from .discover import discover_capabilities
from .transport import connection_display, open_session, validate_server_config
from .types import ServerCapabilities, ServerConfig, ServerProbeResult


def _stdio_pollution_hint(exc: BaseException) -> str:
    """根据异常信息给出 stdio 协议污染提示。"""
    text = str(exc).lower()
    markers = (
        "parse error",
        "invalid json",
        "unexpected token",
        "jsonrpc",
        "content-length",
    )
    if any(marker in text for marker in markers):
        return (
            " 提示: 可能是 stdio 协议污染，请确保 MCP Server 只向 stdout 写 JSON-RPC，"
            "日志输出到 stderr。"
        )
    return ""


async def probe_server(cfg: ServerConfig) -> ServerProbeResult:
    """短连接探测单个 MCP Server 并发现能力。"""
    try:
        transport = validate_server_config(cfg)
    except ValueError as exc:
        return ServerProbeResult(
            name=cfg.name,
            status="failed",
            transport=cfg.resolved_transport() or "unknown",
            error=str(exc),
        )

    display = connection_display(cfg, transport)
    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        session, resolved_transport = await open_session(stack, cfg)
        capabilities = await discover_capabilities(session)
        return ServerProbeResult(
            name=cfg.name,
            status="connected",
            transport=resolved_transport,
            command=display["command"],
            args=display["args"],
            url=display["url"],
            capabilities=capabilities,
        )
    except Exception as exc:
        hint = _stdio_pollution_hint(exc)
        return ServerProbeResult(
            name=cfg.name,
            status="failed",
            transport=transport,
            error=f"{type(exc).__name__}: {exc}{hint}",
            command=display["command"],
            args=display["args"],
            url=display["url"],
            capabilities=ServerCapabilities(),
        )
    finally:
        with suppress(Exception):
            await stack.aclose()


async def probe_servers(
    servers: dict[str, ServerConfig],
    server_names: list[str] | None = None,
) -> list[ServerProbeResult]:
    """批量短连接探测，单点失败不抛异常。"""
    targets = server_names or list(servers.keys())
    results: list[ServerProbeResult] = []
    for name in targets:
        if name not in servers:
            raise ValueError(f"配置中不存在 MCP Server: {name}")
        results.append(await probe_server(servers[name]))
    return results
