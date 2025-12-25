import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from models import User

# DB dependency
try:
    from db import get_db  # type: ignore
except Exception:
    from db import SessionLocal  # type: ignore

    def get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()


# ---------------- Config ----------------

JWT_SECRET = (os.getenv("JWT_SECRET") or "").strip()
JWT_ALG = (os.getenv("JWT_ALG") or "HS256").strip()
JWT_EXPIRES_MIN = int((os.getenv("JWT_EXPIRES_MIN") or "43200").strip())  # 30 дней

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is not set")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ---------------- Helpers ----------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, sub: str) -> str:
    now = _now_utc()
    exp = now + timedelta(minutes=JWT_EXPIRES_MIN)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_token(creds.credentials)

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=401, detail="User not found")

    # soft-delete / disable
    if getattr(u, "deleted_at", None) is not None:
        raise HTTPException(status_code=401, detail="User deleted")
    if getattr(u, "is_active", True) is False:
        raise HTTPException(status_code=401, detail="User inactive")

    return u


# ---------------- Schemas ----------------

class RegisterReq(BaseModel):
    email: EmailStr
    password: str


class AuthResp(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class MeResp(BaseModel):
    id: str
    email: str
    created_at: Optional[str] = None


# ---------------- Routes ----------------

@router.post("/register", response_model=AuthResp)
def register(payload: RegisterReq, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    now = datetime.utcnow()
    user = db.query(User).filter(User.email == email).first()

    # 1) Уже существует и активен
    if user and user.deleted_at is None and user.is_active:
        raise HTTPException(status_code=409, detail="Email already registered")

    # 2) Существует, но был soft-delete / выключен — восстановим
    if user:
        user.password_hash = hash_password(payload.password)
        user.is_active = True
        user.deleted_at = None
        if hasattr(user, "updated_at"):
            user.updated_at = now
        db.commit()
        db.refresh(user)
    else:
        # 3) Новый пользователь
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(payload.password),
            is_active=True,
            created_at=now,
            deleted_at=None,
        )
        if hasattr(user, "updated_at"):
            user.updated_at = now
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(sub=user.id)
    return AuthResp(
        access_token=token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    )


@router.post("/login", response_model=AuthResp)
def login(payload: LoginReq, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    u = db.query(User).filter(User.email == email).first()
    if not u:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if getattr(u, "deleted_at", None) is not None or getattr(u, "is_active", True) is False:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    if not verify_password(payload.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return AuthResp(access_token=create_access_token(sub=u.id))


@router.get("/me", response_model=MeResp)
def me(user: User = Depends(get_current_user)):
    return MeResp(
        id=user.id,
        email=user.email,
        created_at=user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    )


@router.delete("/me")
def delete_me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # soft delete
    user.is_active = False
    user.deleted_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}