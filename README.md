# Function Calling 与 MCP 案例实践

本项目是 Function Calling 与 MCP 的实践代码，包含 Function Calling 和 MCP 两个方向的案例，帮助你理解大模型如何通过工具调用与外部系统交互。


## 环境准备

### 1. 创建并激活 Conda 环境（推荐）

```bash
conda create -n deepstudy python=3.11 -y
conda activate deepstudy
pip -r install requirements.txt
```


## 配置 API Key

项目根目录下的 `.env` 文件用于存放敏感配置，请按如下格式填写：

```ini
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
```

将 `sk-xxxxxxxxxxxxxxxx` 替换为你从 [阿里云 DashScope](https://dashscope.console.aliyun.com/) 获取的真实 API Key。

##  案例

| 脚本 | 数据库驱动 | 可视化能力 | 特点 |
|---|---|---|---|
| `assistant_ticket_bot-1.py` | `mysqlconnector` | ❌ 无 | 基础 SQL 查询，返回 Markdown 表格 |
| `assistant_ticket_bot-2.py` | `mysqlconnector` | ✅ 简单柱状图 | 自动推断 x/y 轴，生成柱状图 |
| `assistant_ticket_bot-3.py` | `pymysql` | ✅ 堆叠柱状图 | 支持多维度透视、中文显示优化、Code Interpreter |


## 注意事项

- `.env` 文件已加入 `.gitignore`，请勿将 API Key 提交到 Git。
- 项目中的数据库连接信息（主机、用户名、密码）目前硬编码在脚本中，如需修改请编辑对应脚本或扩展 `config.py`。
- 建议在 `deepstudy` 环境下统一运行，避免不同 Conda 环境依赖版本冲突。

## 相关链接

- [阿里云 DashScope](https://dashscope.console.aliyun.com/)
- [qwen-agent 文档](https://github.com/QwenLM/Qwen-Agent)
