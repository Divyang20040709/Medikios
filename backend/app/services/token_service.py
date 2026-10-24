"""Atomic OPD token allocation.

QA-07 originally replaced the random token (101-299, no collision check) with
"highest issued + 1". That is unique for sequential check-ins but NOT under
concurrent ones: two requests can both read the same MAX() before either
commits, and both then allocate the same number. That race was reproduced
against SQLite before this module existed (two requests both got OPD-101).

The read-then-write is therefore made atomic for the whole allocate → insert →
commit window:

* PostgreSQL (the production database) — `pg_advisory_xact_lock` serializes
  allocation. The lock is released by the transaction itself, so a crash can
  never leave it held, and a second check-in re-reads MAX() only after the
  first one committed.
* SQLite / other single-writer backends — an in-process asyncio lock covers the
  same window (one process owns the file, so process scope is sufficient).

Uniqueness is additionally enforced by a UNIQUE index on `encounters.token_number`
(see models/entities.py and init_db), so a logic regression raises instead of
silently issuing a duplicate token.
"""

import asyncio
import weakref
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Encounter

# Any stable 32-bit key works; this one spells "MKOP" so it is easy to spot in
# pg_locks while debugging. It must never be reused by another feature.
OPD_TOKEN_LOCK_KEY = 0x4D4B4F50

# First token issued when the table is empty (keeps the existing OPD-101+ range
# used by the seeded demo data).
FIRST_TOKEN_NUMBER = 100

# One lock per running event loop: a single lock reused across loops (each
# pytest test gets a fresh loop) raises "attached to a different loop".
_process_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _process_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _process_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _process_locks[loop] = lock
    return lock


def _is_postgres(db: AsyncSession) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:  # pragma: no cover - defensive, never expected
        return False


async def next_opd_token(db: AsyncSession) -> str:
    """Next free OPD number for this transaction (see opd_token_guard)."""
    if _is_postgres(db):
        result = await db.execute(
            text(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(token_number FROM 5) AS INTEGER)), :floor) "
                "FROM encounters WHERE token_number ~ '^OPD-[0-9]+$'"
            ),
            {"floor": FIRST_TOKEN_NUMBER},
        )
        return f"OPD-{result.scalar_one() + 1}"

    result = await db.execute(
        select(Encounter.token_number).where(Encounter.token_number.like("OPD-%"))
    )
    issued = [
        int(token.split("-")[-1])
        for (token,) in result.all()
        if token and token.split("-")[-1].isdigit()
    ]
    return f"OPD-{max(issued, default=FIRST_TOKEN_NUMBER) + 1}"


@asynccontextmanager
async def opd_token_guard(db: AsyncSession) -> AsyncIterator[None]:
    """Serialize token allocation until the caller's commit.

    Callers must read the next token, add the Encounter and COMMIT inside this
    block — releasing the guard before the commit would re-open the race.
    """
    if _is_postgres(db):
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": OPD_TOKEN_LOCK_KEY}
        )
        yield
        return

    async with _process_lock():
        yield
