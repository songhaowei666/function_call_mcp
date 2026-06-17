import os
import sys
import time
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text

# 将项目根目录加入 sys.path，以便导入 config
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
import config

# 解决中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# LangChain 1.x imports
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


# ====== 门票助手 system prompt ======
system_prompt = """我是门票助手，以下是关于门票订单表相关的字段，我可能会编写对应的SQL(运行环境是MySQL8.0)，对数据进行查询。
-- 门票订单表
CREATE TABLE tkt_orders (
    order_time DATETIME,             -- 订单日期
    account_id INT,                  -- 预定用户ID
    gov_id VARCHAR(18),              -- 商品使用人ID（身份证号）
    gender VARCHAR(10),              -- 使用人性别
    age INT,                         -- 年龄
    province VARCHAR(30),           -- 使用人省份
    SKU VARCHAR(100),                -- 商品SKU名
    product_serial_no VARCHAR(30),  -- 商品ID
    eco_main_order_id VARCHAR(20),  -- 订单ID
    sales_channel VARCHAR(20),      -- 销售渠道
    status VARCHAR(30),             -- 商品状态
    order_value DECIMAL(10,2),       -- 订单金额
    quantity INT                     -- 商品数量
);
一日门票，对应多种SKU：
Universal Studios Beijing One-Day Dated Ticket-Standard
Universal Studios Beijing One-Day Dated Ticket-Child
Universal Studios Beijing One-Day Dated Ticket-Senior
二日门票，对应多种SKU：
USB 1.5-Day Dated Ticket Standard
USB 1.5-Day Dated Ticket Discounted
一日门票、二日门票查询
SUM(CASE WHEN SKU LIKE 'Universal Studios Beijing One-Day%' THEN quantity ELSE 0 END) AS one_day_ticket_sales,
SUM(CASE WHEN SKU LIKE 'USB%' THEN quantity ELSE 0 END) AS two_day_ticket_sales

每当 exc_sql 工具返回 markdown 表格和图片时，你必须原样输出工具返回的全部内容（包括图片 markdown），不要只总结表格，也不要省略图片。这样用户才能直接看到表格和图片。
"""


# ====== 通用可视化函数（参考 assistant_ticket_bot-3.py） ======
def generate_chart_png(df_sql: pd.DataFrame, save_path: str) -> None:
    """根据 DataFrame 生成堆叠柱状图。"""
    columns = df_sql.columns
    x = np.arange(len(df_sql))

    # 获取 object 类型列（分类维度）
    object_columns = df_sql.select_dtypes(include='O').columns.tolist()
    if columns[0] in object_columns:
        object_columns.remove(columns[0])

    num_columns = df_sql.select_dtypes(exclude='O').columns.tolist()

    def safe_label(label: Any) -> str:
        """避免 matplotlib 格式化字符问题。"""
        return str(label).replace('%', '%%').replace('{', '{{').replace('}', '}}')

    if len(object_columns) > 0:
        # 对数据进行透视，生成堆叠柱状图
        pivot_df = df_sql.pivot_table(
            index=columns[0],
            columns=object_columns,
            values=num_columns,
            fill_value=0,
        )
        fig, ax = plt.subplots(figsize=(10, 6))
        bottoms = None
        for col in pivot_df.columns:
            ax.bar(pivot_df.index, pivot_df[col], bottom=bottoms, label=safe_label(col))
            if bottoms is None:
                bottoms = pivot_df[col].copy()
            else:
                bottoms += pivot_df[col]
    else:
        # 普通堆叠柱状图
        bottom = np.zeros(len(df_sql))
        for column in columns[1:]:
            plt.bar(x, df_sql[column], bottom=bottom, label=safe_label(column))
            bottom += df_sql[column]
        safe_xtick_labels = [safe_label(val) for val in df_sql[columns[0]]]
        plt.xticks(x, safe_xtick_labels)

    plt.legend()
    plt.title("销售统计")
    plt.xlabel(safe_label(columns[0]))
    plt.ylabel("门票数量")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


# ====== exc_sql 工具 ======
@tool
def exc_sql(sql_input: str) -> str:
    """对于生成的SQL，进行SQL查询，并自动可视化。"""
    settings = config.settings
    engine = create_engine(
        f'mysql+pymysql://{settings.db_user}:{settings.db_password}'
        f'@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4',
        connect_args={'connect_timeout': 10},
        pool_size=10,
        max_overflow=20,
    )
    try:
        df = pd.read_sql(text(sql_input), engine)
        md = df.head(10).to_markdown(index=False)

        # 自动创建目录并生成图表
        save_dir = Path(__file__).parent / 'image_show'
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f'bar_{int(time.time() * 1000)}.png'
        save_path = save_dir / filename
        generate_chart_png(df, str(save_path))

        img_md = f'![柱状图](image_show/{filename})'
        return f"{md}\n\n{img_md}"
    except Exception as e:
        return f"SQL执行或可视化出错: {str(e)}"


# ====== 初始化 LangChain Agent ======
def init_agent_service():
    """初始化门票助手 LangChain Agent（LangChain 1.x create_agent）。"""
    llm = ChatOpenAI(
        model="qwen-turbo",
        api_key=config.settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.1,
        timeout=30,
    )

    tools = [exc_sql]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )
    return agent


# ====== 终端交互模式 ======
def app_tui():
    """终端交互模式。"""
    agent = init_agent_service()
    messages = []

    while True:
        try:
            query = input('user question: ').strip()
            if not query:
                print('user question cannot be empty！')
                continue

            print("正在处理您的请求...")
            messages.append(HumanMessage(content=query))
            response = agent.invoke({"messages": messages})

            # 取出最后一条 AI 消息作为输出
            output_messages = response.get("messages", [])
            if output_messages:
                ai_msg = output_messages[-1]
                output = ai_msg.content
                messages = output_messages
            else:
                output = "未获取到模型回复"

            print('bot response:', output)
        except KeyboardInterrupt:
            print("\n退出终端模式")
            break
        except Exception as e:
            print(f"处理请求时出错: {str(e)}")


# ====== 图形界面模式 ======
def app_gui():
    """Gradio WebUI 模式。"""
    import gradio as gr

    agent = init_agent_service()

    def chat(message: str, history: list) -> str:
        # 将 gradio 历史转换为 LangChain 消息格式
        messages = [SystemMessage(content=system_prompt)]
        for human_msg, ai_msg in history:
            messages.append(HumanMessage(content=human_msg))
            messages.append(AIMessage(content=ai_msg))
        messages.append(HumanMessage(content=message))

        response = agent.invoke({"messages": messages})
        output_messages = response.get("messages", [])
        if output_messages:
            return output_messages[-1].content
        return "未获取到模型回复"

    demo = gr.ChatInterface(
        fn=chat,
        title="门票助手 (LangChain)",
        description="基于 LangChain + DashScope 的门票订单查询助手",
        examples=[
            "2023年4、5、6月一日门票，二日门票的销量多少？帮我按照周进行统计",
            "2023年7月的不同省份的入园人数统计",
            "帮我查看2023年10月1-7日销售渠道订单金额排名",
        ],
    )
    demo.launch()


if __name__ == '__main__':
    # 运行模式选择
    app_gui()  # 图形界面模式（默认）
