"""列出 MCP 配置文件中的工具（stdio 传输，仅 list_tools）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 项目根目录，用于加载 .env
ROOT_DIR = Path(__file__).resolve().parent.parent
_ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')


def _load_dotenv() -> None:
    """加载项目根目录 .env，便于 JSON 中引用环境变量。"""
    load_dotenv(dotenv_path=ROOT_DIR / '.env', override=True)


def _substitute_env(value: str) -> str:
    """将字符串中的 ${VAR} 替换为环境变量值。"""
    def _replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), '')

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_str(value: Any) -> str:
    """解析并替换字符串中的环境变量。"""
    return _substitute_env(str(value))


def _resolve_path(value: str, config_dir: Path) -> str:
    """将相对路径解析为基于配置文件目录的绝对路径。"""
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((config_dir / path).resolve())


def _resolve_command(command: str) -> str:
    """将通用 python 命令解析为当前解释器路径。"""
    if command in {'python', 'python3'}:
        return sys.executable
    return command


def _resolve_server_config(raw_cfg: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    """解析单个 MCP Server 配置，替换 env 占位符并解析相对路径。"""
    cfg = dict(raw_cfg)
    if cfg.get('command'):
        cfg['command'] = _resolve_command(_resolve_str(cfg['command']))
    if cfg.get('args'):
        resolved_args: list[str] = []
        for arg in cfg['args']:
            arg_text = _resolve_str(arg)
            if arg_text.endswith('.py'):
                resolved_args.append(_resolve_path(arg_text, config_dir))
            else:
                resolved_args.append(arg_text)
        cfg['args'] = resolved_args
    if cfg.get('cwd'):
        cfg['cwd'] = _resolve_path(_resolve_str(cfg['cwd']), config_dir)
    if cfg.get('env'):
        cfg['env'] = {_resolve_str(k): _resolve_str(v) for k, v in cfg['env'].items()}
    return cfg


def _load_mcp_config(config_path: Path) -> dict[str, dict[str, Any]]:
    """从 JSON 文件加载 mcpServers 配置。"""
    config_dir = config_path.parent
    with config_path.open('r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError('配置文件根节点必须是 JSON 对象')

    servers = data.get('mcpServers', data)
    if not isinstance(servers, dict) or not servers:
        raise ValueError('配置中未找到 mcpServers 或其为空')

    resolved: dict[str, dict[str, Any]] = {}
    for name, raw_cfg in servers.items():
        if not isinstance(raw_cfg, dict):
            raise ValueError(f"MCP Server '{name}' 的配置必须是对象")
        if raw_cfg.get('disabled'):
            continue
        resolved[name] = _resolve_server_config(raw_cfg, config_dir)
    return resolved


def _build_stdio_env(cfg: dict[str, Any]) -> dict[str, str] | None:
    """合并系统环境变量与配置中的 env。"""
    cfg_env = cfg.get('env')
    if not cfg_env:
        return None
    merged = dict(os.environ)
    merged.update(cfg_env)
    return merged


def _validate_stdio_config(server_name: str, cfg: dict[str, Any]) -> None:
    """校验 stdio 配置是否完整。"""
    if cfg.get('url') and not cfg.get('command'):
        raise ValueError(
            f"MCP Server '{server_name}' 使用 URL 传输，"
            '当前脚本仅支持 stdio（需配置 command）'
        )
    if not cfg.get('command'):
        raise ValueError(f"MCP Server '{server_name}' 缺少 command 配置")


async def _list_tools_for_server(server_name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """连接单个 stdio MCP Server 并列出工具。"""
    _validate_stdio_config(server_name, cfg)

    async with AsyncExitStack() as stack:
        params = StdioServerParameters(
            command=cfg['command'],
            args=cfg.get('args', []),
            env=_build_stdio_env(cfg),
            cwd=cfg.get('cwd') or None,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()

        tools = [
            {
                'name': tool_def.name,
                'description': tool_def.description or '',
                'inputSchema': tool_def.inputSchema or {
                    'type': 'object',
                    'properties': {},
                },
            }
            for tool_def in result.tools
        ]

        return {
            'name': server_name,
            'transport': 'stdio',
            'command': cfg['command'],
            'args': cfg.get('args', []),
            'tool_count': len(tools),
            'tools': tools,
        }


async def _collect_tools(
    servers: dict[str, dict[str, Any]],
    server_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """批量连接 MCP Server 并收集工具列表。"""
    targets = server_names or list(servers.keys())
    results: list[dict[str, Any]] = []

    for name in targets:
        if name not in servers:
            raise ValueError(f"配置中不存在 MCP Server: {name}")
        server_result = await _list_tools_for_server(name, servers[name])
        results.append(server_result)

    return results


def _format_human_readable(results: list[dict[str, Any]]) -> str:
    """将工具列表格式化为人类可读文本。"""
    lines: list[str] = []

    for item in results:
        lines.append(f"=== MCP Server: {item['name']} ===")
        lines.append(f"Transport: {item['transport']}")
        cmd = item['command']
        args = ' '.join(item.get('args', []))
        lines.append(f"Command: {cmd} {args}".rstrip())
        lines.append(f"Tools ({item['tool_count']}):")

        if not item['tools']:
            lines.append("  (无工具)")
        else:
            for index, tool in enumerate(item['tools'], start=1):
                lines.append(f"{index}. {tool['name']}")
                if tool['description']:
                    lines.append(f"   Description: {tool['description']}")
                schema_text = json.dumps(tool['inputSchema'], ensure_ascii=False)
                lines.append(f"   inputSchema: {schema_text}")
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description='读取 MCP JSON 配置，连接 stdio Server 并列出工具',
    )
    parser.add_argument(
        '--config',
        required=True,
        help='MCP 配置文件路径（JSON，含 mcpServers 字段）',
    )
    parser.add_argument(
        '--server',
        action='append',
        dest='servers',
        help='仅查询指定 Server，可重复传入；默认查询配置中全部 Server',
    )
    parser.add_argument(
        '--json-only',
        action='store_true',
        help='仅输出 JSON，不打印人类可读内容',
    )
    parser.add_argument(
        '--human-only',
        action='store_true',
        help='仅输出人类可读内容，不打印 JSON',
    )
    return parser


def main() -> int:
    """脚本入口。"""
    _load_dotenv()
    parser = _build_parser()
    args = parser.parse_args()

    if args.json_only and args.human_only:
        print('不能同时使用 --json-only 与 --human-only', file=sys.stderr)
        return 1

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.is_file():
        print(f'配置文件不存在: {config_path}', file=sys.stderr)
        return 1

    try:
        servers = _load_mcp_config(config_path)
        if not servers:
            print('配置中没有可用的 MCP Server（可能全部被 disabled）', file=sys.stderr)
            return 1

        results = asyncio.run(_collect_tools(servers, args.servers))
    except Exception as exc:
        print(f'获取 MCP 工具失败: {exc}', file=sys.stderr)
        return 1

    payload = {'servers': results}
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)

    show_human = not args.json_only
    show_json = not args.human_only

    if show_human:
        print(_format_human_readable(results), end='')

    if show_json:
        print(json_text)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
