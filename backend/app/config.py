"""配置管理模块"""

import os
from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载环境变量
# 首先尝试加载当前目录的.env
load_dotenv()
backend_env = Path(__file__).resolve().parents[1] / ".env"
if backend_env.exists():
    load_dotenv(backend_env, override=False)

# 然后尝试加载HelloAgents的.env(如果存在)
helloagents_env = Path(__file__).parent.parent.parent.parent / "HelloAgents" / ".env"
if helloagents_env.exists():
    load_dotenv(helloagents_env, override=False)  # 不覆盖已有的环境变量


def _set_openai_aliases_from_llm_env() -> None:
    """Support legacy LLM_* env names used by this project's .env.example."""
    aliases = {
        "OPENAI_API_KEY": ("LLM_API_KEY", "DEEPSEEK_API_KEY"),
        "OPENAI_BASE_URL": ("LLM_BASE_URL",),
        "OPENAI_MODEL": ("LLM_MODEL_ID",),
    }

    for target, sources in aliases.items():
        if os.getenv(target):
            continue

        for source in sources:
            value = os.getenv(source)
            if value:
                os.environ[target] = value
                break


_set_openai_aliases_from_llm_env()


class Settings(BaseSettings):
    """应用配置"""

    # 应用基本配置
    app_name: str = "多agent的智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS配置 - 使用字符串,在代码中分割
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # 高德地图API配置
    amap_api_key: str = ""

    # Unsplash API配置
    unsplash_access_key: str = ""
    unsplash_secret_key: str = ""

    # LLM配置 (从环境变量读取,由HelloAgents管理)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"

    # LangChain 配置
    langchain_tracing: bool = False  # 是否启用 LangSmith 追踪
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str = ""
    langchain_project: str = "trip-planner"

    # 智能体配置
    agent_max_iterations: int = 3
    agent_temperature: float = 0.7
    agent_timeout: float = 30.0

    # 日志配置
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的环境变量

    def get_cors_origins_list(self) -> List[str]:
        """获取CORS origins列表"""
        return [origin.strip() for origin in self.cors_origins.split(',')]


# 创建全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings


# 验证必要的配置
def validate_config():
    """验证配置是否完整"""
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY未配置")

    # LangChain 使用标准 OpenAI 环境变量
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        errors.append("OPENAI_API_KEY 未配置（LangChain 必需）")

    # LangChain 配置检查
    if settings.langchain_tracing and not settings.langchain_api_key:
        warnings.append("启用了 LangSmith 追踪但未配置 LANGCHAIN_API_KEY")

    if errors:
        error_msg = "配置错误:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    if warnings:
        print("\n⚠️  配置警告:")
        for w in warnings:
            print(f"  - {w}")

    return True


# 打印配置信息(用于调试)
def print_config():
    """打印当前配置(隐藏敏感信息)"""
    print(f"应用名称: {settings.app_name}")
    print(f"版本: {settings.app_version}")
    print(f"服务器: {settings.host}:{settings.port}")
    print(f"高德地图API Key: {'已配置' if settings.amap_api_key else '未配置'}")

    # 检查LLM配置
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_base_url = os.getenv("OPENAI_BASE_URL", settings.openai_base_url)
    openai_model = os.getenv("OPENAI_MODEL", settings.openai_model)

    print(f"OpenAI API Key: {'已配置' if openai_api_key else '未配置'}")
    print(f"OpenAI Base URL: {openai_base_url}")
    print(f"OpenAI Model: {openai_model}")
    print(f"LangChain 追踪: {'启用' if settings.langchain_tracing else '禁用'}")
    print(f"智能体最大迭代次数: {settings.agent_max_iterations}")
    print(f"智能体温度: {settings.agent_temperature}")
    print(f"智能体超时: {settings.agent_timeout}秒")
    print(f"日志级别: {settings.log_level}")

