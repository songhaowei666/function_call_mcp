# MCP 连接、Session 与三种能力详解

> 基于 nanobot 源码（`nanobot/agent/tools/mcp.py`）的讨论整理。  
> 参考项目：[nanobot-main](https://github.com/nanobot-ai/nanobot)

---

## 目录

1. [MCP 连接的本质](#1-mcp-连接的本质)
2. [为什么要提前连接、又要释放](#2-为什么要提前连接又要释放)
3. [Session 是什么，能长期存活吗](#3-session-是什么能长期存活吗)
4. [MCP Session 与 HTTP Session 的区别](#4-mcp-session-与-http-session-的区别)
5. [AsyncExitStack 的作用](#5-asyncexitstack-的作用)
6. [配置 vs 运行时连接](#6-配置-vs-运行时连接)
7. [三种能力：Tool、Resource、Prompt](#7-三种能力toolresourceprompt)
8. [应用场景与具体示例](#8-应用场景与具体示例)
9. [与 nanobot Skill 的对比](#9-与-nanobot-skill-的对比)
10. [上层展示 vs 底层连接状态](#10-上层展示-vs-底层连接状态)

---

## 1. MCP 连接的本质

**MCP 连接 ≠ 简单的 HTTP 调用。**

HTTP 只是 MCP 的一种底层传输载体。MCP 连接的本质是：**建立一条双向消息通道 + 协议会话（JSON-RPC）**。

在 nanobot 中，连接分三层：

| 层级 | 作用 |
|------|------|
| **Transport（传输层）** | 提供 `read` / `write` 字节流：子进程 stdio、SSE 长连接、Streamable HTTP |
| **ClientSession（协议层）** | 在字节流上跑 MCP JSON-RPC：`initialize`、`list_tools`、`call_tool` 等 |
| **Wrapper（nanobot 层）** | 把远端能力注册为 `mcp_{server}_{name}` 工具，供 LLM 调用 |

连接建立流程（简化）：

```
AsyncExitStack
  ├── transport（stdio_client / sse_client / streamable_http_client）
  ├── httpx.AsyncClient（HTTP 型才有）
  └── ClientSession(read, write)
        ├── initialize()        # 协议握手
        ├── list_tools()        # 发现工具
        ├── list_resources()    # 发现资源（可选）
        └── list_prompts()      # 发现提示词模板（可选）
```

真正调用工具时，走的是**同一个 session**，而不是每次新建 HTTP 请求：

```python
await self._session.call_tool(self._original_name, arguments=kwargs)
```

### 三种传输方式

| 传输 | 是否 HTTP | 说明 |
|------|-----------|------|
| **stdio** | 否 | 启动子进程，通过 stdin/stdout 传 JSON-RPC；stdout 只能写协议数据 |
| **sse** | 是 | HTTP 长连接 + Server-Sent Events，维持会话和后台任务 |
| **streamableHttp** | 是 | HTTP 客户端 + MCP streamable 协议，仍有 session 语义 |

---

## 2. 为什么要提前连接、又要释放

### 提前连接（connect）做了什么

连接阶段必须在第一次 tool call 之前完成：

1. **`session.initialize()`** — MCP 协议握手，协商版本与能力
2. **`list_tools()` / `list_resources()` / `list_prompts()`** — 发现远端能力，注册到 `ToolRegistry`
3. **维持存活的后端** — stdio 子进程、SSE 流、httpx client 等在后台运行
4. **性能** — 避免每次 tool call 都重新 spawn 进程、重新握手、重新 list tools

### 释放连接（close / aclose）的原因

1. **资源泄漏** — stdio 子进程不关闭会变成僵尸进程；SSE/HTTP 占用 socket 和后台 task
2. **配置热更新** — WebUI 修改 MCP 配置时需先关旧连接再连新的
3. **进程退出** — gateway/CLI 退出时 `close_mcp()` 做优雅 shutdown
4. **会话死亡** — server 重启或断连后，先 `_close_server` 再 `connect_mcp_servers` 重建

### 与普通 REST API 的对比

```
普通 REST API:
  每次: HTTP Request → Response → 结束（无会话）

MCP（以 stdio 为例）:
  连接: spawn 进程 → initialize → list_tools → 注册工具
  调用: session.call_tool() ──JSON-RPC──> 同一进程（可多次）
  释放: kill 进程 / 关流 / 关 client
```

---

## 3. Session 是什么，能长期存活吗

**`ClientSession` 不是 HTTP，而是 MCP SDK 的协议会话对象**，跑在抽象的 `read` / `write` 流上。

### 能长期存活吗？

**能，nanobot 按长期连接设计。**

- 连接成功后，每个 server 的 `AsyncExitStack` 存入 `state._mcp_stacks`
- 后续 `_connect_mcp()` 只补连缺失的 server，已有的不会重建
- nanobot **没有**给 MCP session 设 idle timeout；gateway 在跑，连接就一直留着

### 两类「超时」不要混淆

| 类型 | 默认值 | 作用范围 |
|------|--------|----------|
| **单次 tool call 超时** | `tool_timeout`（默认 30s） | 只限制这一次 `call_tool`，不关 session |
| **Session 本身** | 无 idle timeout | 直到 shutdown、热更新或 server/网络断连 |

### 什么会让 session 死掉

| 原因 | nanobot 处理 |
|------|-------------|
| 进程退出 / `close_mcp()` | 主动 `stack.aclose()` |
| WebUI 改 MCP 配置 | 热更新：关旧连新 |
| MCP server 重启 / 断连 | 捕获 `session terminated`，自动 reconnect |
| 网络瞬断 | transient error 重试一次 |

---

## 4. MCP Session 与 HTTP Session 的区别

名字都叫 session，但层级和用途完全不同。

| | **HTTP Session** | **MCP `ClientSession`** |
|--|------------------|-------------------------|
| 是什么 | 在「无状态 HTTP」上维持的**应用层会话** | MCP 协议里的**客户端会话对象** |
| 典型载体 | Cookie / `Session-ID` / JWT | `read` / `write` 字节流 |
| 管什么 | 用户登录、购物车、服务端业务状态 | `initialize`、JSON-RPC、`call_tool` |
| 是否一定是 HTTP | 是 | **不一定**（stdio 完全不走 HTTP） |

更准确的心智模型：

- **HTTP Session** = HTTP 之上 + Web 框架的「谁在用」
- **MCP Session** = 传输层之上 + MCP 协议的「怎么调工具」

MCP session 更接近 **WebSocket 连接 + 协议状态机**，或 **RPC 客户端长连接**，而不是浏览器里的 `JSESSIONID`。

---

## 5. AsyncExitStack 的作用

`AsyncExitStack`（`contextlib`）是 **异步版资源栈管理器**：运行时动态注册多个 async context manager，退出时按 **后进先出（LIFO）** 统一清理。

### 核心机制

```python
stack = AsyncExitStack()
await stack.__aenter__()

read, write = await stack.enter_async_context(stdio_client(params))
session = await stack.enter_async_context(ClientSession(read, write))

# 用完后
await stack.aclose()  # 先关 session，再关 transport，顺序自动正确
```

### 在 nanobot MCP 中的角色

每个 MCP server 对应一个 `AsyncExitStack`，存入 `_mcp_stacks`：

```
AsyncExitStack（server A）
  ├── stdio_client / sse_client / streamable_http_client
  ├── httpx.AsyncClient（HTTP 型）
  └── ClientSession
```

**Session 负责「说话」；ExitStack 负责「挂断并收拾干净」。**

nanobot 不用单个 `async with` 包住整个连接生命周期，是因为：

1. 连接要**长期持有**（存在 `_mcp_stacks` 里）
2. 连接方式**运行时才知道**（stdio / sse / streamableHttp 分支不同）
3. 失败时需要 **partial cleanup**（`await server_stack.aclose()`）
4. 每个 server **独立 stack**，避免多个 MCP server 的 cancel scope 冲突

---

## 6. 配置 vs 运行时连接

| 概念 | 存储位置 | 含义 |
|------|----------|------|
| **配置** | `_mcp_servers`（`config.json`） | command/url、headers、enabledTools 等静态配置 |
| **Session / 连接** | `_mcp_stacks` | 运行时：`AsyncExitStack` → transport → `ClientSession` |

```
上层（用户看到的）
  config.json / Settings 里的 MCP 配置     ← 稳定，改完才变
  @preset、工具列表                        ← 连接成功时注册，看起来像「一直开着」

底层（实际运行的）
  _mcp_stacks[server] = 活的 session       ← 可能断、可能静默重连
  MCPToolWrapper._session                  ← 重连后会换成新的 session 对象
```

底层会在以下时机自动建连 / 重连，**通常不在 UI 上提示**：

1. 每条消息前 `connect_missing_servers`（只补缺失的）
2. 调 tool 时发现 session 死了 → `_refresh_terminated_server`
3. WebUI 改配置 → hot reload
4. 网络瞬断 → transient error 重试

---

## 7. 三种能力：Tool、Resource、Prompt

MCP 协议定义三类能力，nanobot 连接时全部拉取并注册为 LLM 可调用的「工具」。

| 能力 | MCP 方法 | 本质 | nanobot 命名 |
|------|----------|------|-------------|
| **Tool** | `list_tools` → `call_tool` | 执行动作 | `mcp_{server}_{toolname}` |
| **Resource** | `list_resources` → `read_resource` | 读数据 | `mcp_{server}_resource_{name}` |
| **Prompt** | `list_prompts` → `get_prompt` | 生成对话模板 | `mcp_{server}_prompt_{name}` |

一句话记忆：

```
Resource  → 「给你看材料」
Prompt    → 「教你怎么做 / 给你范例对话」
Tool      → 「替你动手干」
```

### Tool

- 有参数，可能有副作用
- 底层：`session.call_tool(name, arguments=...)`
- 返回执行结果

### Resource

- **只读**，nanobot 包装后**无参数**（`read_only = True`）
- 清单上的 `description` 是索引说明；`read_resource(uri)` 返回的是**真实内容**（文档、schema 等）
- 底层：`session.read_resource(uri)`

### Prompt

- 可带参数（如 `topic`、`table_name`）
- 返回一组 **messages**（user/assistant 等多轮文本），是工作流 / 少样本模板
- 底层：`session.get_prompt(name, arguments=...)`
- nanobot 将 messages 拼成文本返回给模型

> 许多 MCP server **只实现 tools**，`list_resources` / `list_prompts` 为空或失败是正常现象；代码里失败只打 debug 日志，不影响连接。

---

## 8. 应用场景与具体示例

假设连接了 `filesystem`、`postgres`、`github` 三个 MCP server。

### Tool — 执行动作

**用户**：「帮我在 GitHub 上开一个 bug issue。」

```
mcp_github_create_issue(
  owner="nanobot-ai",
  repo="nanobot",
  title="MCP connection intermittently drops",
  body="..."
)
```

| Server | Tool 示例 | 场景 |
|--------|-----------|------|
| filesystem | `mcp_filesystem_write_file` | 修改配置文件 |
| Browserbase | `mcp_browserbase_navigate` | 打开网页并操作 |
| postgres | `mcp_postgres_query` | 执行 SQL |
| github | `mcp_github_create_issue` | 创建 Issue |

### Resource — 只读拿上下文

**用户**：「读一下 API 文档，告诉我 `/users` 有哪些字段。」

```
mcp_postgres_resource_PostgreSQL_System_Information()
```

返回 schema、表结构等静态/半静态文本，无参数，只读。

与 Tool 的分工：

```
先 Resource：拉 schema / 文档进上下文
再 Tool：    按 schema 写 SQL 并执行
```

### Prompt — 标准流程模板

**用户**：「帮我设计一张新的订单表。」

```
mcp_postgres_prompt_design-schema(
  table_name="orders",
  requirements="支持多币种、软删除"
)
```

返回的不是 SQL 结果，而是编排好的对话片段，例如：

```
[user] 你是数据库设计专家。请为表 orders 设计 schema...
[assistant] 我会先确认：1) 主键策略 2) 索引需求 ...
```

### 完整任务串联

**用户**：「分析 orders 表的数据质量并写报告。」

```
1. Prompt（可选）
   mcp_postgres_prompt_data-quality-check(table_name="orders")
   → 拿到标准检查流程

2. Resource
   mcp_postgres_resource_PostgreSQL_System_Information()
   → 确认列、类型、约束

3. Tool（多次）
   mcp_postgres_query(sql="SELECT COUNT(*) FROM orders WHERE email IS NULL")
   ...

4. Tool（可选）
   mcp_filesystem_write_file(path="report.md", content="...")
```

### 选型速查

| 你想让 server… | 用 |
|----------------|-----|
| 执行操作、改状态、跑查询 | **Tool** |
| 提供可读文档 / schema / 配置 | **Resource** |
| 提供固定 SOP、标准问法、多轮模板 | **Prompt** |

---

## 9. 与 nanobot Skill 的对比

### 能力分工（精炼理解）

| | **Skill** | **MCP Prompt** | **MCP Tool** |
|--|-----------|----------------|--------------|
| 语义 | 工作流 / 方法论 / 少样本 | 可参数化的 SOP / 对话模板 | 动手执行 |
| 默认位置 | system prompt | 工具列表里的定义 | 工具列表里的定义 |
| 正文怎么进上下文 | 自动注入或 `read_file` | 模型调 `mcp_*_prompt_*` | 模型调 `mcp_*_*` |
| 是否每轮自动出现 | always skill 是；普通 skill 只有目录 | 否，需主动调用 | 否，需主动调用 |
| 类比 | 常驻操作规程 / 书架索引 | 按需领取的作业指导单 | 手和脚 |

### Skill 在 system prompt 的两种形态

**1. `always=true` 的 skill — 全文每轮注入**

```python
always_skills = self.skills.get_always_skills()
always_content = self.skills.load_skills_for_context(always_skills)
# → "# Active Skills\n\n{全文}"
```

**2. 普通 skill — 只放目录，全文按需 `read_file`**

```markdown
# Skills
The following skills extend your capabilities. To use a skill, read its SKILL.md using the read_file tool.
{{ skills_summary }}
```

### MCP Prompt 在 tool message

模型调用后，结果进入 `role: "tool"` 消息：

```python
tool_message = {
    "role": "tool",
    "tool_call_id": tool_call.id,
    "name": tool_call.name,
    "content": result,
}
```

- **当前 turn 内**：同一次 agent loop 的后续 iteration 都能看到
- **turn 结束后**：会写入 session history（可能被截断），但**不会**自动注入下一轮的 system prompt

### 核心差异

```
Skill（always）  → proactive，system prompt 全文，每个 turn 都在场
Skill（普通）    → proactive 目录 + reactive 正文（read_file → tool message）
MCP Prompt       → reactive，tool message，主要服务当前 turn 推理链
MCP Tool         → reactive，tool message，返回执行结果
```

---

## 10. 上层展示 vs 底层连接状态

### 上层展示什么

- **WebUI Settings**：command/url、测试连接、改完可能要 restart / hot reload
- **聊天 @preset**：告诉模型用哪个 preset，附带工具前缀
- **`runtime_lines`**：每轮对话开始时的一次性快照，判断 preset 是否在 `_mcp_stacks` 里

WebUI 的 `ConnectionStatus` 指的是 **浏览器 ↔ gateway** 的 WebSocket，**不是** gateway ↔ MCP server 的 session。

### 底层实际状态

- `_mcp_stacks` 存活的连接可能静默断连、重连
- 用户通常只在 tool 调用失败、日志、或 LLM 上下文警告里间接感知

### 图书馆类比

```
Resource = 图书馆（只读材料）
Prompt   = 作业指导书（流程 / 少样本）
Tool     = 手和脚（执行）
Skill    = 刻在墙上的常驻规章（system prompt）
```

---

## 附录：关键源码位置（nanobot）

| 主题 | 文件 |
|------|------|
| MCP 连接与三种 Wrapper | `nanobot/agent/tools/mcp.py` |
| MCP 关闭 | `nanobot/agent/loop.py` → `close_mcp()` |
| Skill 注入 system prompt | `nanobot/agent/context.py` → `build_system_prompt()` |
| Tool message 写入 | `nanobot/agent/runner.py` |
| Session history 持久化 | `nanobot/agent/loop.py` → `_save_turn()` |
| MCP 配置 schema | `nanobot/config/schema.py` → `MCPServerConfig` |

---

*文档生成日期：2026-06-22*
