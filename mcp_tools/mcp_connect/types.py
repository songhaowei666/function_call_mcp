"""MCP 连接层公共数据类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TransportType = Literal["stdio", "sse", "streamableHttp"]
ProbeStatus = Literal["connected", "failed"]


@dataclass(slots=True)
class ServerConfig:
    """解析后的单个 MCP Server 配置。"""

    name: str
    transport: TransportType | None = None
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    disabled: bool = False

    def resolved_transport(self) -> TransportType | None:
        """按 nanobot 规则推断传输类型。"""
        if self.transport:
            return self.transport
        if self.command:
            return "stdio"
        if self.url:
            if self.url.rstrip("/").endswith("/sse"):
                return "sse"
            return "streamableHttp"
        return None


@dataclass(slots=True)
class ToolInfo:
    """MCP 工具元数据。"""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class ResourceInfo:
    """MCP 资源元数据。"""

    name: str
    uri: str
    description: str


@dataclass(slots=True)
class PromptArgumentInfo:
    """MCP Prompt 参数元数据。"""

    name: str
    description: str
    required: bool


@dataclass(slots=True)
class PromptInfo:
    """MCP Prompt 元数据。"""

    name: str
    description: str
    arguments: list[PromptArgumentInfo] = field(default_factory=list)


@dataclass(slots=True)
class ServerCapabilities:
    """单个 Server 的能力发现结果。"""

    tools: list[ToolInfo] = field(default_factory=list)
    resources: list[ResourceInfo] = field(default_factory=list)
    prompts: list[PromptInfo] = field(default_factory=list)
    resources_error: str | None = None
    prompts_error: str | None = None


@dataclass(slots=True)
class ServerProbeResult:
    """短连接探测结果，供 CLI 与诊断使用。"""

    name: str
    status: ProbeStatus
    transport: str
    error: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    capabilities: ServerCapabilities = field(default_factory=ServerCapabilities)

    @property
    def tool_count(self) -> int:
        return len(self.capabilities.tools)

    @property
    def resource_count(self) -> int:
        return len(self.capabilities.resources)

    @property
    def prompt_count(self) -> int:
        return len(self.capabilities.prompts)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好结构。"""
        caps = self.capabilities
        return {
            "name": self.name,
            "status": self.status,
            "transport": self.transport,
            "error": self.error,
            "command": self.command,
            "args": self.args,
            "url": self.url,
            "tool_count": self.tool_count,
            "resource_count": self.resource_count,
            "prompt_count": self.prompt_count,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
                for tool in caps.tools
            ],
            "resources": [
                {
                    "name": resource.name,
                    "uri": resource.uri,
                    "description": resource.description,
                }
                for resource in caps.resources
            ],
            "prompts": [
                {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": [
                        {
                            "name": arg.name,
                            "description": arg.description,
                            "required": arg.required,
                        }
                        for arg in prompt.arguments
                    ],
                }
                for prompt in caps.prompts
            ],
            "resources_error": caps.resources_error,
            "prompts_error": caps.prompts_error,
        }
