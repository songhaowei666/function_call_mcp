import os
from pathlib import Path
from dotenv import load_dotenv

# 兼容 Pydantic v1 / v2
try:
    from pydantic.v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent

# 加载 .env 文件
env_path = ROOT_DIR / '.env'
load_dotenv(dotenv_path=env_path, override=True)


class Settings(BaseModel):
    """项目全局配置类，统一加载环境变量。"""

    # DashScope
    dashscope_api_key: str = Field(default='', description='DashScope API Key')

    # 高德地图
    amap_maps_api_key: str = Field(
        default='', description='AMap Maps API Key（高德地图 MCP Server 使用）'
    )

    # Tavily 搜索
    tavily_api_key: str = Field(
        default='', description='Tavily Search API Key（Tavily MCP Server 使用）'
    )

    # 数据库配置
    db_host: str = Field(
        default='rm-uf6z891lon6dxuqblqo.mysql.rds.aliyuncs.com',
        description='数据库主机地址',
    )
    db_port: int = Field(default=3306, description='数据库端口')
    db_user: str = Field(default='student123', description='数据库用户名')
    db_password: str = Field(default='student321', description='数据库密码')
    db_name: str = Field(default='ubr', description='数据库名')


# 从环境变量实例化全局配置
settings = Settings(
    dashscope_api_key=os.getenv('DASHSCOPE_API_KEY', ''),
    amap_maps_api_key=os.getenv('AMAP_MAPS_API_KEY', ''),
    tavily_api_key=os.getenv('TAVILY_API_KEY', ''),
    db_host=os.getenv('DB_HOST', 'rm-uf6z891lon6dxuqblqo.mysql.rds.aliyuncs.com'),
    db_port=int(os.getenv('DB_PORT', '3306')),
    db_user=os.getenv('DB_USER', 'student123'),
    db_password=os.getenv('DB_PASSWORD', 'student321'),
    db_name=os.getenv('DB_NAME', 'ubr'),
)

# 保持向后兼容的导出
dashscope_api_key: str = settings.dashscope_api_key
DASHSCOPE_API_KEY: str = settings.dashscope_api_key
amap_maps_api_key: str = settings.amap_maps_api_key
AMAP_MAPS_API_KEY: str = settings.amap_maps_api_key
tavily_api_key: str = settings.tavily_api_key
TAVILY_API_KEY: str = settings.tavily_api_key
