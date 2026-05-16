import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# 预先计算路径，不放在类内部
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
    
    # API Keys
    GEMINI_API_KEY: Optional[str] = None
    TUSHARE_TOKEN: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore"
    )

settings = Settings()
