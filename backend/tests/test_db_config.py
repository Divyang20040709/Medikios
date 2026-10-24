"""Regression tests for local PostgreSQL connection configuration.

Verifies the fixes for:
- getaddrinfo failure caused by an un-encoded '@' in the password.
- Mislabeling the target as Neon when it is actually local PostgreSQL.
- Forcing ssl=require on a local (non-TLS) PostgreSQL server.
- Credential leakage in display strings / source defaults.
"""
from sqlalchemy.engine.url import make_url

from backend.app.core.config import Settings, settings


def _sample() -> Settings:
    # A .env-style URL whose password contains a bare '@' (the original failure).
    return Settings(
        DATABASE_URL="postgresql://postgres:pa55@word@localhost:5432/Medikios",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5432,
        POSTGRES_DB="medikiosk_db",
        POSTGRES_USER="",
        POSTGRES_PASSWORD="",
        _env_file=None,
    )


def test_password_with_at_is_parsed_from_last_at():
    s = _sample()
    user, pwd, host, port, db = s._split_db_url(s._raw_db_url)
    assert user == "postgres"
    assert pwd == "pa55@word"
    assert host == "localhost"
    assert db == "Medikios"


def test_local_target_overrides_alias_host_and_db():
    s = _sample()
    url = make_url(s.database_url)
    assert url.drivername == "postgresql+asyncpg"
    # Target is forced to the explicit local settings, not the alias values.
    assert url.host == "127.0.0.1"
    assert url.port == 5432
    assert url.database == "medikiosk_db"
    # Credentials preserved and safely re-encoded (no getaddrinfo split bug).
    assert url.username == "postgres"
    assert url.password == "pa55@word"


def test_no_forced_ssl_for_local_postgres():
    s = _sample()
    assert s.is_local_postgres is True
    assert s.is_neon_configured is False
    url = make_url(s.database_url)
    assert "ssl" not in (url.query or {})


def test_safe_display_url_masks_password():
    s = _sample()
    safe = s.safe_database_url
    assert "pa55@word" not in safe
    assert "****" in safe
    assert "127.0.0.1" in safe and "medikiosk_db" in safe


def test_settings_have_no_hardcoded_credentials_default():
    # The source default must not embed a real password.
    from backend.app.core.config import Settings as S
    fields = S.model_fields
    assert fields["POSTGRES_PASSWORD"].default in ("", None)
    assert fields["POSTGRES_URL"].default == ""


def test_backend_detection_without_any_postgres_config_falls_back_to_sqlite():
    s = Settings(
        DATABASE_URL="", NEON_DATABASE_URL="", POSTGRES_URL="", POSTGRESQL_URL="",
        POSTGRES_USER="", POSTGRES_PASSWORD="", _env_file=None,
    )
    # Only if no env var leaked in from the process environment:
    if not (s.POSTGRES_USER or s._raw_db_url):
        assert s.database_backend == "sqlite"
        assert s.database_url.startswith("sqlite+aiosqlite")


def test_real_imported_settings_target_local_postgres():
    # Guard the actual shipped config: it must resolve to local Postgres,
    # not be mislabeled as Neon.
    assert settings.database_backend in ("postgresql", "sqlite")
    if settings.database_backend == "postgresql":
        assert settings.is_local_postgres is True
        assert settings.is_neon_configured is False
