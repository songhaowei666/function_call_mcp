# mcp_connect 库使用说明

## 目录结构（C 方案：库 + 薄 CLI）

```
mcp_tools/
  mcp_connect/          # 连接层库（可被 import）
    config.py           # 配置加载、环境变量解析
    types.py            # 数据类型
    transport.py        # stdio / sse / streamableHttp 传输
    discover.py         # list_tools / list_resources / list_prompts
    connect.py          # 长连接 MCPConnection（供 agent 使用）
    probe.py            # 短连接探测（供 CLI / 诊断）
  cli/                  # 薄 CLI
    main.py             # 参数解析 + 调用库 + 打印
    formatters.py       # 人类可读 / JSON 格式化
  list_mcp_tools.py     # 兼容入口
```

## 库 API 速览

### 配置

```python
from pathlib import Path
from mcp_tools.mcp_connect import load_dotenv_for_project, load_mcp_config

load_dotenv_for_project()
servers = load_mcp_config(Path("mcp_tools/mcp.json"))
```

### 短连接探测（CLI 同款）

```python
import asyncio
from mcp_tools.mcp_connect import probe_server, probe_servers

async def main():
    cfg = servers["txt-counter"]
    result = await probe_server(cfg)
    print(result.status, result.tool_count)

asyncio.run(main())
```

### 长连接（agent 运行时）

```python
import asyncio
from mcp_tools.mcp_connect import connect_server, close_connections

async def main():
    conn = await connect_server(servers["txt-counter"])
    try:
        caps = await conn.discover()
        result = await conn.call_tool("count_desktop_txt_files", {})
        print(caps.tools, result)
    finally:
        await conn.close()

asyncio.run(main())
```

## CLI 用法

```bash
# 兼容旧入口
python mcp_tools/list_mcp_tools.py --config mcp_tools/mcp.json --server txt-counter

# 模块入口
python -m mcp_tools.cli --config mcp_tools/mcp.json --human-only
```

## 与 nanobot connect_mcp_servers 的对应关系

| nanobot | mcp_connect |
|---------|-------------|
| `connect_mcp_servers` + `_mcp_stacks` | `connect_servers` + `MCPConnection` |
| `list_tools/resources/prompts` | `discover_capabilities` |
| 一次性列工具（无） | `probe_server` / `probe_servers` |
| `MCPServerConfig` | `ServerConfig` + `load_mcp_config` |

## 边界说明

- **库**：负责连接、发现、长连接管理
- **CLI**：只负责参数、输出、退出码；单 server 失败不拖垮整批（全部失败才 exit 1）
- **resources / prompts**：失败降级，不算连接失败
- **安全**：v1 未做 SSRF 校验（URL 型传输需自行信任 endpoint）
