import logging
import os
from typing import Any, List, Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Application
    app_name: str = "FastAPI Modular Template"
    debug: bool = False
    version: str = "1.0.0"
    environment: str = "dev"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database (local default: sqlite)
    database_url: str = "sqlite+aiosqlite:///./local_app.db"

    # JWT / local session
    jwt_secret_key: str = "change-me-local-dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Frontend / CORS
    frontend_url: str = "http://127.0.0.1:5173"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Super Admin seed (set password in .env — never hardcode)
    super_admin_username: str = "admin"
    super_admin_password: str = ""

    # Optional Atoms / OIDC (not required for local mode)
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_issuer_url: str = ""
    oidc_scope: str = "openid email profile"
    admin_user_id: str = ""
    admin_user_email: str = ""

    # Optional Object Storage (Atoms OSS) — unused in local file mode
    oss_service_url: str = ""
    oss_api_key: str = ""

    # Supabase Storage (public bucket "uploads")
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""
    supabase_storage_bucket: str = "uploads"

    # AWS Lambda Configuration
    is_lambda: bool = False
    lambda_function_name: str = "fastapi-backend"
    aws_region: str = "us-east-1"

    @property
    def backend_url(self) -> str:
        """Generate backend URL from host and port."""
        if self.is_lambda:
            return os.environ.get(
                "PYTHON_BACKEND_URL",
                f"https://{self.lambda_function_name}.execute-api.{self.aws_region}.amazonaws.com",
            )
        display_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        return os.environ.get("PYTHON_BACKEND_URL", f"http://{display_host}:{self.port}")

    @property
    def cors_origins_list(self) -> List[str]:
        """CORS allow-list: CORS_ORIGINS plus FRONTEND_URL when set."""
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        frontend = (self.frontend_url or "").strip().rstrip("/")
        if frontend and frontend not in origins:
            origins.append(frontend)
        # Deduplicate while preserving order
        seen = set()
        unique: List[str] = []
        for origin in origins:
            key = origin.rstrip("/")
            if key not in seen:
                seen.add(key)
                unique.append(origin)
        return unique

    class Config:
        case_sensitive = False
        extra = "ignore"
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __getattr__(self, name: str) -> Any:
        """Fallback: read unknown attributes from environment (UPPER_CASE)."""
        env_var_name = name.upper()
        if env_var_name in os.environ:
            value = os.environ[env_var_name]
            self.__dict__[name] = value
            logger.debug("Read dynamic attribute %s from %s", name, env_var_name)
            return value
        # Local-friendly defaults for optional Atoms settings
        optional_defaults = {
            "oidc_client_id": "",
            "oidc_client_secret": "",
            "oidc_issuer_url": "",
            "oidc_scope": "openid email profile",
            "oss_service_url": "",
            "oss_api_key": "",
            "admin_user_id": "",
            "admin_user_email": "",
        }
        if name in optional_defaults:
            return optional_defaults[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


settings = Settings()
