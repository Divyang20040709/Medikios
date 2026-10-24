import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Explicitly search for .env in project root and backend dir
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
possible_env_paths = [
    ROOT_DIR / ".env",
    BACKEND_DIR / ".env",
    Path.cwd() / ".env"
]

for p in possible_env_paths:
    if p.exists():
        load_dotenv(dotenv_path=p, override=True)

class Settings(BaseSettings):
    APP_NAME: str = "MediKiosk"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Database configuration.
    # Credentials are read from .env only — NEVER hardcoded in source.
    # Local PostgreSQL target (SQLAlchemy async driver: postgresql+asyncpg)
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "medikiosk_db"
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    # Optional full-URL aliases. When discrete POSTGRES_USER/PASSWORD are absent,
    # credentials are parsed safely from the first non-empty URL below.
    NEON_DATABASE_URL: str = ""
    DATABASE_URL: str = ""
    POSTGRES_URL: str = ""
    POSTGRESQL_URL: str = ""
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///./medikiosk.db"
    
    # Neon Auth & JWT
    NEON_AUTH_URL: str = "https://auth.neon.tech"
    AUTH_URL: str = ""
    # Signing secrets come from .env only (which is gitignored). They default to
    # empty on purpose: a literal default here would be published with the source
    # and anyone could mint a valid admin token. main.py refuses to start without
    # them, so a fresh clone must copy .env.example -> .env and set real values.
    NEON_AUTH_COOKIE_SECRET: str = ""
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    # OpenRouter LLM (NVIDIA Nemotron 3 Ultra) (aliases supported)
    OPENROUTER_API_KEY: str = ""
    OPEN_ROUTER_API_KEY: str = ""
    LLM_API_KEY: str = ""
    OPENROUTER_KEY: str = ""
    OPENROUTER_MODEL: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Local LLM (free, no API key): Ollama or any OpenAI-compatible local server
    LOCAL_LLM_ENABLED: bool = True
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.2"
    LLM_TIMEOUT_SECONDS: float = 20.0
    
    # Speech Recognition (Local Whisper Model from model/whisper)
    SPEECH_PROVIDER: str = "whisper"
    WHISPER_MODEL_PATH: str = "model/whisper"
    WHISPER_MODEL_SIZE: str = "base"
    BHASHINI_API_KEY: str = ""
    BHASHINI_USER_ID: str = ""
    BHASHINI_PIPELINE_ID: str = ""
    
    # OCR Pipeline (Local PaddleOCR Model from model/paddleocr)
    OCR_PROVIDER: str = "paddleocr"
    PADDLEOCR_MODEL_PATH: str = "model/paddleocr"
    TESSERACT_PATH: str = ""
    MAX_DOCUMENT_UPLOAD_MB: int = 25
    OCR_TIMEOUT_SECONDS: float = 90.0
    
    # ABDM Gateway
    ABDM_CLIENT_ID: str = ""
    ABDM_CLIENT_SECRET: str = ""
    ABDM_BRIDGE_URL: str = "https://dev.abdm.gov.in/gateway"
    ABDM_MODE: str = "sandbox"
    
    # CORS
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000"

    @property
    def effective_neon_url(self) -> str:
        candidates = [
            self.NEON_DATABASE_URL,
            self.DATABASE_URL,
            self.POSTGRES_URL,
            self.POSTGRESQL_URL,
            os.getenv("NEON_DATABASE_URL", ""),
            os.getenv("DATABASE_URL", ""),
            os.getenv("POSTGRES_URL", ""),
            os.getenv("POSTGRESQL_URL", "")
        ]
        for c in candidates:
            c_clean = c.strip().strip('"\'')
            if c_clean:
                return c_clean
        return ""

    @property
    def effective_openrouter_key(self) -> str:
        candidates = [
            self.OPENROUTER_API_KEY,
            self.OPEN_ROUTER_API_KEY,
            self.LLM_API_KEY,
            self.OPENROUTER_KEY,
            os.getenv("OPENROUTER_API_KEY", ""),
            os.getenv("OPEN_ROUTER_API_KEY", ""),
            os.getenv("LLM_API_KEY", ""),
            os.getenv("OPENROUTER_KEY", "")
        ]
        for c in candidates:
            c_clean = c.strip().strip('"\'')
            if c_clean:
                return c_clean
        return ""

    @property
    def effective_auth_url(self) -> str:
        candidates = [
            self.NEON_AUTH_URL,
            self.AUTH_URL,
            os.getenv("NEON_AUTH_URL", ""),
            os.getenv("AUTH_URL", "")
        ]
        for c in candidates:
            c_clean = c.strip().strip('"\'')
            if c_clean:
                return c_clean
        return "https://auth.neon.tech"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_neon_configured(self) -> bool:
        return bool(self.effective_neon_url)

    @property
    def is_openrouter_configured(self) -> bool:
        return bool(self.effective_openrouter_key)

    # ── Database resolution (local PostgreSQL first, safe credential handling) ──

    @staticmethod
    def _split_db_url(url: str):
        """Split a postgres URL into (user, password, host, port, database).

        Handles passwords that contain URL-special characters such as '@'
        by splitting credentials from the host at the LAST '@'. Percent-encoded
        characters are decoded so they can be safely re-encoded by URL.create.
        """
        from urllib.parse import unquote
        rest = url.strip().strip('"\'')
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://", "postgres://"):
            if rest.lower().startswith(prefix):
                rest = rest[len(prefix):]
                break
        if "?" in rest:
            rest = rest.split("?", 1)[0]
        if "@" in rest:
            userinfo, hostpart = rest.rsplit("@", 1)
            if ":" in userinfo:
                user, pwd = userinfo.split(":", 1)
            else:
                user, pwd = userinfo, ""
            user, pwd = unquote(user), unquote(pwd)
        else:
            user, pwd = "", ""
            hostpart = rest
        database = ""
        if "/" in hostpart:
            hostport, database = hostpart.split("/", 1)
        else:
            hostport = hostpart
        host, port = hostport, ""
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
        return user, pwd, host, port, database

    @property
    def _raw_db_url(self) -> str:
        """First configured, non-empty, non-sqlite URL alias (from .env)."""
        candidates = [
            self.DATABASE_URL,
            self.NEON_DATABASE_URL,
            self.POSTGRES_URL,
            self.POSTGRESQL_URL,
            os.getenv("DATABASE_URL", ""),
            os.getenv("NEON_DATABASE_URL", ""),
            os.getenv("POSTGRES_URL", ""),
            os.getenv("POSTGRESQL_URL", ""),
        ]
        for c in candidates:
            c_clean = c.strip().strip('"\'')
            if c_clean and "sqlite" not in c_clean.lower() and "://" in c_clean:
                return c_clean
        return ""

    @property
    def database_backend(self) -> str:
        """'postgresql' when credentials/URL are available, else 'sqlite'."""
        if self.POSTGRES_USER or self.POSTGRES_PASSWORD or self._raw_db_url:
            return "postgresql"
        return "sqlite"

    @property
    def is_local_postgres(self) -> bool:
        return self.database_backend == "postgresql" and self.POSTGRES_HOST in ("127.0.0.1", "localhost", "::1")

    @property
    def is_neon_configured(self) -> bool:
        """Backwards-compatible flag: True only for a REMOTE managed postgres host."""
        return self.database_backend == "postgresql" and not self.is_local_postgres

    @property
    def safe_database_url(self) -> str:
        """Credential-free display URL (password never exposed)."""
        if self.database_backend == "sqlite":
            return self.SQLITE_FALLBACK_URL
        user = self.POSTGRES_USER or self._split_db_url(self._raw_db_url)[0] or "?"
        return f"postgresql+asyncpg://{user}:****@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def database_url(self) -> str:
        if self.database_backend == "sqlite":
            return self.SQLITE_FALLBACK_URL

        from sqlalchemy.engine.url import URL
        # Credentials: discrete .env vars take precedence; otherwise parse the URL alias.
        user = self.POSTGRES_USER
        pwd = self.POSTGRES_PASSWORD
        if not user:
            user, pwd, _h, _p, _d = self._split_db_url(self._raw_db_url)

        # Host/port/database always come from the explicit target settings so the
        # app connects to 127.0.0.1:5432/medikiosk_db regardless of the alias host.
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=user or None,
            password=pwd or None,
            host=self.POSTGRES_HOST,
            port=int(self.POSTGRES_PORT),
            database=self.POSTGRES_DB or "medikiosk_db",
        )
        # TLS only for remote managed hosts (e.g. Neon). Never forced for local.
        if self.is_neon_configured:
            url = url.set(query={"ssl": "require"})
        return url.render_as_string(hide_password=False)

    model_config = {"env_file": ".env", "extra": "allow"}

settings = Settings()
