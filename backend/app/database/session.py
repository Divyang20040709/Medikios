import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Runtime database status — reflects what ACTUALLY happened on connection,
# not just what was configured. Consumed by /health and /api/health/diagnostics.
db_status = {
    "target_backend": settings.database_backend,   # "postgresql" | "sqlite"
    "is_local_postgres": settings.is_local_postgres,
    "connected": False,                             # True only after a real SELECT 1
    "active_backend": None,                         # backend actually in use after init_db
    "fallback_in_use": False,                       # True if Postgres failed -> SQLite
    "error": None,                                  # last real connection error message
}

connect_args = {}
engine_kwargs = {"echo": False, "future": True}

if "sqlite" in settings.database_url:
    connect_args = {"check_same_thread": False}
else:
    # PostgreSQL connection tuning. pool_pre_ping surfaces dead connections early.
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300
    if not settings.is_local_postgres:
        # PgBouncer / serverless pooling mode is only needed for remote managed hosts.
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

print(f"\n========================================================")
print(f" [MediKiosk Database Layer]")
if settings.database_backend == "sqlite":
    print(f" [Database Target] No PostgreSQL credentials found. Using Local SQLite: {settings.SQLITE_FALLBACK_URL}")
else:
    kind = "Local PostgreSQL" if settings.is_local_postgres else "Managed PostgreSQL (Neon)"
    print(f" [Database Target] {kind} @ {settings.safe_database_url}")
print(f"========================================================\n")

try:
    engine = create_async_engine(
        settings.database_url,
        connect_args=connect_args,
        **engine_kwargs
    )
except Exception as e:
    if settings.database_backend == "postgresql":
        # Do NOT silently pretend we are ready. Surface the real error immediately.
        db_status["error"] = f"engine-creation: {e}"
        logger.error(" [Database] PostgreSQL engine creation FAILED: %s", e)
    print(f" [Database] Warning: Engine creation error ({e}). Falling back to SQLite.")
    engine = create_async_engine(
        settings.SQLITE_FALLBACK_URL,
        future=True,
        connect_args={"check_same_thread": False},
    )

async_session_factory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_database_status() -> dict:
    """Return the true, current database connection status."""
    return dict(db_status)


async def init_db():
    global engine, async_session_factory
    target_url = settings.database_url
    targeting_postgres = settings.database_backend == "postgresql"

    try:
        if targeting_postgres:
            kind = "Local PostgreSQL" if settings.is_local_postgres else "Managed PostgreSQL (Neon)"
            print(f" [Database Status] Attempting connection to {kind} @ {settings.safe_database_url} ...")

        async with engine.begin() as conn:
            # Real connectivity test — success here is the ONLY thing that lets
            # us claim PostgreSQL is connected.
            await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)

            # Auto-align columns for PostgreSQL if tables pre-existed.
            if "sqlite" not in str(engine.url):
                cols_res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))
                existing_cols = set(r[0] for r in cols_res.fetchall())
                for col_name, col_def in [
                    ("phone", "VARCHAR"),
                    ("abha_id", "VARCHAR"),
                    ("doctor_registration_no", "VARCHAR"),
                    ("is_active", "BOOLEAN DEFAULT TRUE")
                ]:
                    if col_name not in existing_cols:
                        await conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))

                # QA-07: OPD tokens must be unique at the database level, not
                # only in application code. Tables that pre-date this change do
                # not get the index from create_all(), so create it idempotently
                # — but only when the existing rows are still duplicate-free,
                # because a partially-migrated table would fail startup.
                try:
                    duplicate_groups = (
                        await conn.execute(text(
                            "SELECT count(*) FROM (SELECT token_number FROM encounters "
                            "GROUP BY token_number HAVING count(*) > 1) AS dupes"
                        ))
                    ).scalar_one()
                    if duplicate_groups == 0:
                        await conn.execute(text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_encounters_token_number "
                            "ON encounters (token_number)"
                        ))
                        print(" [Database Status] UNIQUE index on encounters.token_number verified.")
                    else:
                        logger.error(
                            " [Database] %s duplicate token_numbers found; UNIQUE index NOT created. "
                            "Resolve the duplicates before re-running.", duplicate_groups
                        )
                except Exception as index_error:  # never block startup on this
                    logger.error(" [Database] Could not create the token UNIQUE index: %s", index_error)

        db_status["connected"] = True
        db_status["active_backend"] = "postgresql" if "postgresql" in str(engine.url) else "sqlite"
        db_status["error"] = None
        if targeting_postgres:
            kind = "Local PostgreSQL" if settings.is_local_postgres else "Managed PostgreSQL (Neon)"
            print(f" [Database Status] SUCCESS! Connected and schema verified on {kind} ({settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}).")
        else:
            print(f" [Database Status] Connected and schema verified on Local SQLite ({settings.SQLITE_FALLBACK_URL}).")

    except Exception as e:
        # ---- Make PostgreSQL failures VISIBLE, not silent. ----
        db_status["error"] = str(e)
        db_status["connected"] = False
        logger.error(" [Database Status] PostgreSQL connection FAILED: %s", e)
        print(f"\n [Database Status] *** ERROR: Could NOT connect to PostgreSQL ***")
        print(f" [Database Status] Target was: {settings.safe_database_url}")
        print(f" [Database Status] Real error : {e}")

        if targeting_postgres:
            # Development convenience: keep the service alive on SQLite, but do NOT
            # claim PostgreSQL is ready. The /health endpoint will report the fallback.
            print(f" [Database Status] NOT claiming PostgreSQL is ready. Activating SQLite "
                  f"ONLY so the service stays reachable — fix .env / start PostgreSQL to resolve.\n")
            db_status["fallback_in_use"] = True
            db_status["active_backend"] = "sqlite (FALLBACK - PostgreSQL unreachable)"
            engine = create_async_engine(
                settings.SQLITE_FALLBACK_URL,
                future=True,
                connect_args={"check_same_thread": False},
            )
            async_session_factory = async_sessionmaker(
                bind=engine,
                autoflush=False,
                expire_on_commit=False,
                class_=AsyncSession,
            )
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print(f" [Database Status] SQLite fallback active (PostgreSQL is NOT connected).\n")
        else:
            print(f" [Database Status] SQLite initialization failed: {e}")
            raise
