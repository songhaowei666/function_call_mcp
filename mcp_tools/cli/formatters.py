"""CLI 输出格式化。"""

from __future__ import annotations

import json
from typing import Any

from mcp_tools.mcp_connect.types import ServerProbeResult


def format_human_readable(results: list[ServerProbeResult]) -> str:
    """将探测结果格式化为人类可读文本。"""
    lines: list[str] = []

    for item in results:
        lines.append(f"=== MCP Server: {item.name} ===")
        lines.append(f"Status: {item.status}")
        lines.append(f"Transport: {item.transport}")
        if item.error:
            lines.append(f"Error: {item.error}")
        if item.command:
            args = " ".join(item.args)
            lines.append(f"Command: {item.command} {args}".rstrip())
        if item.url:
            lines.append(f"URL: {item.url}")

        caps = item.capabilities
        lines.append(f"Tools ({item.tool_count}):")
        if not caps.tools:
            lines.append("  (无工具)")
        else:
            for index, tool in enumerate(caps.tools, start=1):
                lines.append(f"{index}. {tool.name}")
                if tool.description:
                    lines.append(f"   Description: {tool.description}")
                schema_text = json.dumps(tool.input_schema, ensure_ascii=False)
                lines.append(f"   inputSchema: {schema_text}")

        lines.append(f"Resources ({item.resource_count}):")
        if caps.resources_error:
            lines.append(f"  (不可用: {caps.resources_error})")
        elif not caps.resources:
            lines.append("  (无资源)")
        else:
            for index, resource in enumerate(caps.resources, start=1):
                lines.append(f"{index}. {resource.name}")
                if resource.description:
                    lines.append(f"   Description: {resource.description}")
                lines.append(f"   URI: {resource.uri}")

        lines.append(f"Prompts ({item.prompt_count}):")
        if caps.prompts_error:
            lines.append(f"  (不可用: {caps.prompts_error})")
        elif not caps.prompts:
            lines.append("  (无 Prompt)")
        else:
            for index, prompt in enumerate(caps.prompts, start=1):
                lines.append(f"{index}. {prompt.name}")
                if prompt.description:
                    lines.append(f"   Description: {prompt.description}")
                if prompt.arguments:
                    arg_names = ", ".join(arg.name for arg in prompt.arguments)
                    lines.append(f"   Arguments: {arg_names}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def results_to_json_payload(results: list[ServerProbeResult]) -> dict[str, Any]:
    """将探测结果转为 JSON 输出结构。"""
    return {"servers": [item.to_dict() for item in results]}
