from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.core.config import settings
from backend.app.database.session import get_db
from backend.app.models.entities import User, Patient, Encounter, AuditLog
from backend.app.schemas.pydantic_models import LoginRequest, Token, PatientRegisterRequest
from backend.app.services.token_service import next_opd_token, opd_token_guard

import bcrypt

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

import hashlib
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Phase 6: passwords are stored as salted bcrypt hashes. Legacy rows still
# hold unsalted SHA-256 digests; they keep verifying (and are transparently
# upgraded to bcrypt on next successful login) so existing accounts never break.

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")

def is_legacy_hash(hashed_password: str) -> bool:
    """True when a stored hash is the pre-Phase-6 unsalted SHA-256 format."""
    return bool(hashed_password) and not hashed_password.startswith("$2")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if not is_legacy_hash(hashed_password):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))
        except ValueError:
            return False
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


def require_roles(*allowed_roles: str):
    """LEGACY lenient guard — kept only for kiosk-surface compatibility.

    Requests with no token pass through anonymously (shared kiosk / demo
    mode). NEVER use this for clinical sign-off, verification, PHI reads or
    any admin action: those must use require_authenticated_roles, which
    rejects anonymous callers with 401 (Phase 6 security audit).
    """
    async def role_guard(user: Optional[User] = Depends(get_current_user)) -> Optional[User]:
        if user is not None and user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not authorized to perform this action."
            )
        return user
    return role_guard


def require_authenticated_roles(*allowed_roles: str):
    """Strict RBAC guard (Phase 6): a valid, unexpired token for an allowed
    role is mandatory. Missing/invalid/expired credentials -> 401;
    authenticated but disallowed role -> 403. The role is taken from the
    database User row, never from the client-supplied token claims alone.
    """
    async def role_guard(user: Optional[User] = Depends(get_current_user)) -> User:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: a valid bearer token must be supplied.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not authorized to perform this action."
            )
        return user
    return role_guard

@router.post("/login", response_model=Token)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    ident = req.identifier.strip()
    user = None

    # Try matching email, phone, abha_id
    query = select(User).where(
        (User.email == ident) | (User.phone == ident) | (User.abha_id == ident)
    )
    res = await db.execute(query)
    user = res.scalars().first()

    # Staff accounts must never be resolved through the patient sign-in tab
    # (a shared phone/email identifier would otherwise auto-create or attach
    # patient records to a DOCTOR/ADMIN identity).
    if user is not None and req.role == "PATIENT" and user.role in ("DOCTOR", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials do not match the requested role."
        )

    # If logging in as patient and not found by user, check Patient MRN or ABHA
    if not user and req.role == "PATIENT":
        pat_res = await db.execute(
            select(Patient).where(
                (Patient.abha_id == ident) | (Patient.mrn == ident) | (Patient.phone == ident)
            )
        )
        patient = pat_res.scalars().first()
        if patient and patient.user_id:
            u_res = await db.execute(select(User).where(User.id == patient.user_id))
            user = u_res.scalars().first()
            if user is not None and user.role in ("DOCTOR", "ADMIN"):
                # Legacy-linked staff identity — refuse patient sign-in path.
                user = None
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credentials do not match the requested role."
                )
        elif patient:
            # Auto create user record for existing patient without one
            user = User(
                full_name=patient.name,
                role="PATIENT",
                phone=patient.phone,
                abha_id=patient.abha_id
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            patient.user_id = user.id
            await db.commit()

    import random

    if not user:
        # For development/demo convenience, auto-register patient if logging in with valid phone/ABHA
        if req.role == "PATIENT":
            patient_name = req.name.strip() if req.name else f"Patient {ident[-4:] if len(ident) >= 4 else ident}"
            user = User(
                full_name=patient_name,
                phone=ident if "@" not in ident else None,
                abha_id=ident if "ABHA" in ident or "-" in ident else None,
                email=ident if "@" in ident else None,
                role="PATIENT"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials or user not registered."
            )

    # If logging in as patient, ensure Patient record and active Encounter exist in DB
    if req.role == "PATIENT":
        pat_res = await db.execute(
            select(Patient).where(
                (Patient.user_id == user.id) |
                (Patient.phone == ident) |
                (Patient.abha_id == ident)
            )
        )
        patient = pat_res.scalars().first()
        if not patient:
            mrn_num = random.randint(1000, 9999)
            patient = Patient(
                user_id=user.id,
                name=req.name.strip() if req.name else user.full_name,
                age=req.age or 35,
                gender=(req.gender or "Male").upper(),
                phone=user.phone or (ident if "@" not in ident else None),
                abha_id=user.abha_id or (ident if "ABHA" in ident or "-" in ident else None),
                mrn=f"MRN-2026-{mrn_num}"
            )
            db.add(patient)
            await db.commit()
            await db.refresh(patient)
        else:
            if req.name and req.name.strip():
                patient.name = req.name.strip()
            if req.age:
                patient.age = req.age
            if req.gender:
                patient.gender = req.gender.upper()
            if not patient.user_id:
                patient.user_id = user.id
            await db.commit()
            await db.refresh(patient)

        # Check if an active encounter exists for this patient, else create one
        enc_res = await db.execute(
            select(Encounter).where(
                Encounter.patient_id == patient.id,
                Encounter.status.in_(["QUEUED", "INTAKE_IN_PROGRESS", "WAITING", "WAITING_CONSULTATION", "INTAKE_COMPLETED"])
            )
        )
        active_enc = enc_res.scalars().first()
        if not active_enc:
            # QA-07: this patient-login path had its own random token generator
            # (same 101-299 collision bug). Both entry points now allocate
            # through the same guarded helper.
            async with opd_token_guard(db):
                token_num = await next_opd_token(db)
                new_encounter = Encounter(
                    patient_id=patient.id,
                    department=req.department or "General Medicine",
                    token_number=token_num,
                    status="QUEUED",
                    priority="ROUTINE"
                )
                db.add(new_encounter)
                await db.commit()


    # Phase 6: DOCTOR / ADMIN access is a privileged path — a password is
    # ALWAYS required and must match the stored hash. The previous behaviour
    # ("check only if password provided") allowed issuing staff tokens with
    # no credential at all. The account's real role must also match the role
    # requested at login (no cross-role token issuance off a shared identifier).
    if req.role in ["DOCTOR", "ADMIN"]:
        if user.role != req.role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credentials do not match the requested role."
            )
        if not req.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Password is required for staff sign-in."
            )
        if not user.password_hash or not verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password."
            )
        # Transparently upgrade pre-Phase-6 unsalted SHA-256 hashes to bcrypt.
        if is_legacy_hash(user.password_hash):
            user.password_hash = get_password_hash(req.password)
            db.add(AuditLog(
                actor_id=user.id,
                actor_role=user.role,
                action="PASSWORD_HASH_UPGRADED",
                entity_type="USER",
                entity_id=user.id,
                details={"from": "sha256_unsalted", "to": "bcrypt"}
            ))
            await db.commit()

    # Record Audit Log
    audit = AuditLog(
        actor_id=user.id,
        actor_role=user.role,
        action="USER_LOGIN",
        entity_type="USER",
        entity_id=user.id,
        details={"identifier": ident, "role": user.role}
    )
    db.add(audit)
    await db.commit()

    token = create_access_token(data={"sub": user.id, "role": user.role, "name": user.full_name})
    return Token(
        access_token=token,
        role=user.role,
        user_id=user.id,
        name=user.full_name
    )

@router.get("/me")
async def get_me(user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "department": user.department,
        "doctor_reg_no": user.doctor_registration_no
    }
