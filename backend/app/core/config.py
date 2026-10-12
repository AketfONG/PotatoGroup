"""全局配置:通过环境变量 / .env 注入,见 backend/.env.example。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库连接串;本地默认 SQLite,生产切换 MySQL(见 docs/04-部署方案.md)
    database_url: str = "sqlite:///./potato.db"

    # JWT 配置(开发默认值仅用于本地;生产必须覆盖)
    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"
    jwt_expire_days: int = 7

    # 允许的前端来源,逗号分隔
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    app_env: str = "dev"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()