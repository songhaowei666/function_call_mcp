"""MCP 配置加载与环境变量解析。"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .types import ServerConfig, TransportType

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")
_VALID_TRANSPORTS = {"stdio", "sse", "streamableHttp"}


def load_dotenv_for_project(project_root: Path | None = None) -> Path:
    """加载项目根目录 .env，返回根目录路径。"""
    root = project_root or Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=root / ".env", override=True)
    return root


def substitute_env(value: str) -> str:
    """将字符串中的 ${VAR} 替换为环境变量值。"""
    return _ENV_VAR_PATTERN.sub(
        lambda match: os.environ.get(match.group(1), ""),
        value,
    )


def resolve_str(value: Any) -> str:
    """解析并替换字符串中的环境变量。"""
    return substitute_env(str(value))


def resolve_path(value: str, config_dir: Path) -> str:
    """将相对路径解析为基于配置文件目录的绝对路径。"""
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((config_dir / path).resolve())


def resolve_command(command: str) -> str:
    """将通用 python 命令解析为当前解释器路径。"""
    if command in {"python", "python3"}:
        return sys.executable
    return command


def _parse_transport(raw: Any) -> TransportType | None:
    if raw is None:
        return None
    transport = str(raw).strip()
    if transport in _VALID_TRANSPORTS:
        return transport  # type: ignore[return-value]
    raise ValueError(f"不支持的 transport 类型: {transport}")


def resolve_server_config(name: str, raw_cfg: dict[str, Any], config_dir: Path) -> ServerConfig:
    """解析单个 MCP Server 配置，替换 env 占位符并解析相对路径。"""
    cfg = dict(raw_cfg)
    command = resolve_str(cfg["command"]) if cfg.get("command") else ""
    args = [resolve_str(arg) for arg in cfg.get("args", [])]
    resolved_args: list[str] = []
    for arg in args:
        if arg.endswith(".py"):
            resolved_args.append(resolve_path(arg, config_dir))
        else:
            resolved_args.append(arg)

    env = {resolve_str(k): resolve_str(v) for k, v in (cfg.get("env") or {}).items()}
    cwd = resolve_path(resolve_str(cfg["cwd"]), config_dir) if cfg.get("cwd") else ""
    headers = {resolve_str(k): resolve_str(v) for k, v in (cfg.get("headers") or {}).items()}

    return ServerConfig(
        name=name,
        transport=_parse_transport(cfg.get("type") or cfg.get("transport")),
        command=resolve_command(command) if command else "",
        args=resolved_args,
        env=env,
        cwd=cwd,
        url=resolve_str(cfg["url"]) if cfg.get("url") else "",
        headers=headers,
        disabled=bool(cfg.get("disabled")),
    )


def load_mcp_config(config_path: Path) -> dict[str, ServerConfig]:
    """从 JSON 文件加载 mcpServers 配置。"""
    config_path = config_path.expanduser().resolve()
    config_dir = config_path.parent
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("配置文件根节点必须是 JSON 对象")

    servers = data.get("mcpServers", data)
    if not isinstance(servers, dict) or not servers:
        raise ValueError("配置中未找到 mcpServers 或其为空")

    resolved: dict[str, ServerConfig] = {}
    for name, raw_cfg in servers.items():
        if not isinstance(raw_cfg, dict):
            raise ValueError(f"MCP Server '{name}' 的配置必须是对象")
        server_cfg = resolve_server_config(name, raw_cfg, config_dir)
        if server_cfg.disabled:
            continue
        resolved[name] = server_cfg
    return resolved


def build_stdio_env(cfg: ServerConfig) -> dict[str, str] | None:
    """合并系统环境变量与配置中的 env。"""
    if not cfg.env:
        return None
    merged = dict(os.environ)
    merged.update(cfg.env)
    return merged
