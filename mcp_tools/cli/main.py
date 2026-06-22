"""MCP 工具 CLI 入口（薄封装）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp_tools.mcp_connect import load_dotenv_for_project, load_mcp_config, probe_servers

from mcp_tools.cli.formatters import format_human_readable, results_to_json_payload


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="读取 MCP JSON 配置，连接 Server 并列出 tools/resources/prompts",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="MCP 配置文件路径（JSON，含 mcpServers 字段）",
    )
    parser.add_argument(
        "--server",
        action="append",
        dest="servers",
        help="仅查询指定 Server，可重复传入；默认查询配置中全部 Server",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="仅输出 JSON，不打印人类可读内容",
    )
    parser.add_argument(
        "--human-only",
        action="store_true",
        help="仅输出人类可读内容，不打印 JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口。"""
    load_dotenv_for_project()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.json_only and args.human_only:
        print("不能同时使用 --json-only 与 --human-only", file=sys.stderr)
        return 1

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.is_file():
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        return 1

    try:
        servers = load_mcp_config(config_path)
        if not servers:
            print("配置中没有可用的 MCP Server（可能全部被 disabled）", file=sys.stderr)
            return 1
        results = asyncio.run(probe_servers(servers, args.servers))
    except Exception as exc:
        print(f"获取 MCP 能力失败: {exc}", file=sys.stderr)
        return 1

    show_human = not args.json_only
    show_json = not args.human_only
    if show_human:
        print(format_human_readable(results), end="")
    if show_json:
        print(json.dumps(results_to_json_payload(results), ensure_ascii=False, indent=2))

    has_failure = any(item.status == "failed" for item in results)
    has_success = any(item.status == "connected" for item in results)
    if has_failure and not has_success:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
