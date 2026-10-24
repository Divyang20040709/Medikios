import sys
from pathlib import Path

# Ensure project root is on sys.path so 'backend.*' imports resolve
# regardless of the working directory (e.g. running from backend/).
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.database.session import init_db, get_database_status
from backend.app.api.auth_router import router as auth_router
from backend.app.api.intake_router import router as intake_router
from backend.app.api.document_router import router as document_router
from backend.app.api.doctor_router import router as doctor_router
from backend.app.api.admin_router import router as admin_router
from backend.app.api.fhir_router import router as fhir_router
from backend.app.api.speech_router import router as speech_router
from backend.app.api.chat_router import router as chat_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Security hygiene (Phase 6): the signing key lives in .env only (gitignored).
    # Refuse to start without it — an empty or published key lets anyone forge tokens.
    if not settings.JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is not set. Copy .env.example to .env and generate a value: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    # Initialize DB schemas on startup
    await init_db()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="MediKiosk - AI-Assisted Clinical Intake Platform for High-Volume Hospital OPDs",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
origins = settings.cors_origins
if "*" not in origins:
    origins.extend(["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every client-visible error must be valid JSON (the frontend parses error
# bodies for its messages). Without this handler an unexpected exception
# escapes as Starlette's plain-text "Internal Server Error" body. The real
# traceback is logged server-side only — never sent to the client.
logger = logging.getLogger("medikiosk.server")

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled server error on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again; if it persists, contact support."},
    )

# Uploads directory (storage only). Phase 6: the previous unauthenticated
# StaticFiles mount at /uploads exposed every uploaded medical document to
# anyone with the filename. Originals are now served ONLY through the
# role-guarded GET /api/documents/file/{document_id} endpoint.
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount Routers
app.include_router(auth_router)
app.include_router(intake_router)
app.include_router(chat_router)
app.include_router(document_router)
app.include_router(doctor_router)
app.include_router(admin_router)
app.include_router(fhir_router)
app.include_router(speech_router)

from backend.app.services.llm_service import llm_service

@app.get("/health")
async def health_check():
    # Report the ACTUAL connection result, not just what was configured.
    db = get_database_status()
    if db["connected"] and db["active_backend"] == "postgresql":
        db_target = "Local PostgreSQL" if db["is_local_postgres"] else "Managed PostgreSQL (Neon)"
    elif db["fallback_in_use"]:
        db_target = "SQLite (FALLBACK — PostgreSQL unreachable)"
    else:
        db_target = "Local SQLite"
    return {
        "status": "HEALTHY",
        "service": "MediKiosk Clinical Core API",
        "database": {
            "type": db_target,
            "target_backend": db["target_backend"],
            "connected": db["connected"],
            "fallback_in_use": db["fallback_in_use"],
            "error": db["error"],
        },
        "llm": {
            "model": settings.OPENROUTER_MODEL,
            "openrouter_key_present": settings.is_openrouter_configured,
        },
        "abdm_gateway": settings.ABDM_MODE,
        "version": "1.0.0"
    }

@app.get("/api/health/diagnostics")
async def get_diagnostics():
    """
    Returns full runtime configuration status so the user can verify
    Neon PostgreSQL and OpenRouter key detection without exposing secrets.
    """
    key_preview = "NOT_CONFIGURED"
    if settings.OPENROUTER_API_KEY:
        k = settings.OPENROUTER_API_KEY.strip()
        key_preview = f"{k[:8]}...{k[-4:]}" if len(k) > 12 else "****"

    neon_preview = "NOT_CONFIGURED (Using SQLite fallback)"
    db = get_database_status()
    if db["target_backend"] == "postgresql":
        neon_preview = settings.safe_database_url  # credentials masked

    return {
        "status": "READY",
        "database": {
            "target_backend": db["target_backend"],
            "is_local_postgres": db["is_local_postgres"],
            "connected": db["connected"],
            "fallback_in_use": db["fallback_in_use"],
            "active_backend": db["active_backend"],
            "connection": neon_preview,
            "last_error": db["error"],
        },
        "neon_database": {
            "configured": settings.is_neon_configured,
            "connection": neon_preview
        },
        "openrouter_llm": {
            "configured": settings.is_openrouter_configured,
            "model": settings.OPENROUTER_MODEL,
            "key_status": key_preview
        },
        "speech_provider": settings.SPEECH_PROVIDER,
        "ocr_provider": settings.OCR_PROVIDER,
        "abdm_mode": settings.ABDM_MODE
    }

@app.get("/api/health/llm-test")
async def test_llm_connection():
    """
    Directly tests connection to OpenRouter with NVIDIA Nemotron 3 Ultra.
    """
    return await llm_service.test_connection()

@app.get("/")
async def root():
    return {
        "message": "Welcome to MediKiosk API",
        "documentation": "/docs",
        "health": "/health",
        "diagnostics": "/api/health/diagnostics"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
