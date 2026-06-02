from typing import Literal

from pydantic import Field, RedisDsn

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_file_encoding="utf-8",
    )

    mode: Literal["DEV", "TEST", "PROD"] = Field(default="DEV")

    auth_user: str
    auth_pass: str

    db_engine: str = Field(default="postgresql+asyncpg")
    db_user: str = Field(default="postgres")
    db_password: str = Field(default="postgres")
    db_host: str = Field(default="postgres")
    db_port: str = Field(default="5432")
    db_name: str = Field(default="postgres")

    video_min_size_mb: int = Field(default=100)
    videos_download_size_mb: int = Field(default=32)
    redis_dsn: RedisDsn

    min_baseline_speed_mbps: float = Field(default=1.0)
    monitoring_run_interval_minutes: int = Field(default=60)

    kvs_cv: str = Field(default="")
    kvs_ahv: str = Field(default="")
    ip: str = Field(default="0.0.0.0")

    analytics_update_interval_minutes: int = Field(default=60)

    @property
    def db_connection_string(self) -> str:
        return (
            f"{self.db_engine}://"
            f"{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/"
            f"{self.db_name}"
        )

    @property
    def is_test_mode(self) -> bool:
        return self.mode == "TEST"


config = Config()
