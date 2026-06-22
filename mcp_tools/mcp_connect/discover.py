"""MCP 能力发现：tools / resources / prompts。"""

from __future__ import annotations

from typing import Any

from mcp import ClientSession

from .types import (
    PromptArgumentInfo,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ToolInfo,
)


def _tool_info(tool_def: Any) -> ToolInfo:
    return ToolInfo(
        name=tool_def.name,
        description=tool_def.description or "",
        input_schema=tool_def.inputSchema
        or {
            "type": "object",
            "properties": {},
        },
    )


def _resource_info(resource_def: Any) -> ResourceInfo:
    return ResourceInfo(
        name=resource_def.name,
        uri=resource_def.uri,
        description=resource_def.description or "",
    )


def _prompt_info(prompt_def: Any) -> PromptInfo:
    arguments: list[PromptArgumentInfo] = []
    for arg in prompt_def.arguments or []:
        arguments.append(
            PromptArgumentInfo(
                name=arg.name,
                description=getattr(arg, "description", None) or "",
                required=bool(getattr(arg, "required", False)),
            )
        )
    return PromptInfo(
        name=prompt_def.name,
        description=prompt_def.description or "",
        arguments=arguments,
    )


async def discover_capabilities(session: ClientSession) -> ServerCapabilities:
    """发现 MCP Server 暴露的全部能力。"""
    tools_result = await session.list_tools()
    tools = [_tool_info(tool_def) for tool_def in tools_result.tools]

    resources: list[ResourceInfo] = []
    resources_error: str | None = None
    try:
        resources_result = await session.list_resources()
        resources = [_resource_info(resource) for resource in resources_result.resources]
    except Exception as exc:
        resources_error = f"{type(exc).__name__}: {exc}"

    prompts: list[PromptInfo] = []
    prompts_error: str | None = None
    try:
        prompts_result = await session.list_prompts()
        prompts = [_prompt_info(prompt) for prompt in prompts_result.prompts]
    except Exception as exc:
        prompts_error = f"{type(exc).__name__}: {exc}"

    return ServerCapabilities(
        tools=tools,
        resources=resources,
        prompts=prompts,
        resources_error=resources_error,
        prompts_error=prompts_error,
    )
