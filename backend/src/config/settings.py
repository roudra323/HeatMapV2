"""Application settings"""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # Database
    database_url: str = "sqlite:///./heatmap.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API Keys
    quicknode_api_key: Optional[str] = None
    etherscan_api_key: Optional[str] = None
    the_graph_api_key: Optional[str] = None

    # Email
    sendgrid_api_key: Optional[str] = None
    notification_email_from: str = "noreply@heatmap.io"

    # Payments (optional)
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None

    # System
    pricing_enabled: bool = False
    price_per_request: float = 0.00
    environment: str = "development"
    debug: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Celery
    celery_broker_url: Optional[str] = None  # Defaults to redis_url
    celery_result_backend: Optional[str] = None  # Defaults to redis_url

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_celery_broker(self) -> str:
        """Get Celery broker URL"""
        return self.celery_broker_url or self.redis_url

    def get_celery_backend(self) -> str:
        """Get Celery result backend URL"""
        return self.celery_result_backend or self.redis_url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
