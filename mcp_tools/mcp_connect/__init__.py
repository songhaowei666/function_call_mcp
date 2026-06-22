"""MCP 连接层库：配置、连接、发现、探测。"""

from .config import build_stdio_env, load_dotenv_for_project, load_mcp_config
from .connect import MCPConnection, close_connections, connect_server, connect_servers
from .discover import discover_capabilities
from .probe import probe_server, probe_servers
from .types import (
    PromptArgumentInfo,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerConfig,
    ServerProbeResult,
    ToolInfo,
)

__all__ = [
    "MCPConnection",
    "PromptArgumentInfo",
    "PromptInfo",
    "ResourceInfo",
    "ServerCapabilities",
    "ServerConfig",
    "ServerProbeResult",
    "ToolInfo",
    "build_stdio_env",
    "close_connections",
    "connect_server",
    "connect_servers",
    "discover_capabilities",
    "load_dotenv_for_project",
    "load_mcp_config",
    "probe_server",
    "probe_servers",
]
