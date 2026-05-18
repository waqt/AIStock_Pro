import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# 预先计算路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")

class Settings(BaseSettings):
    APP_NAME: str = "AIStock_Pro"
    APP_VERSION: str = "2.1.0"
    DEBUG: bool = True

    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "gemini"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "aistock_pro"

    # AI API Keys
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DOUBAO_API_KEY: Optional[str] = None
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    DOUBAO_MODEL: str = "doubao-seed-2-0-mini-260428"
    TUSHARE_TOKEN: Optional[str] = None

    # Web Search (Brave Search API — free 2000 queries/month)
    BRAVE_API_KEY: Optional[str] = None

    # Proxy (for Gemini etc.)
    HTTP_PROXY: Optional[str] = None
    HTTPS_PROXY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore"
    )

settings = Settings()
