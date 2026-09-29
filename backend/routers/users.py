"""Registration and login endpoints for Smart Railway users."""

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from auth import create_access_token, hash_password, verify_password
from config import JWT_ACCESS_TOKEN_EXPIRE_MINUTES
from models import User

router = APIRouter(prefix="/users", tags=["users"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8)
    phone: Optional[str] = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        """Reject names that become blank after whitespace is removed."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name cannot be blank")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize email addresses so lookups are case-insensitive."""
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("password")
    @classmethod
    def bcrypt_password_length(cls, value: str) -> str:
        """Keep passwords within bcrypt's 72-byte input limit."""
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize email addresses so login matches registration."""
        return value.strip().lower()


class UserSummary(BaseModel):
    id: str
    name: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(str(user.id)),
        expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSummary(id=str(user.id), name=user.name, email=user.email),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn) -> AuthResponse:
    """Create a bcrypt-protected account and return a signed access token."""
    if await User.find_one(User.email == body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")

    user = User(
        name=body.name,
        email=body.email,
        phone=body.phone,
        password_hash=hash_password(body.password),
    )
    try:
        await user.insert()
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginIn) -> AuthResponse:
    """Verify credentials and return a signed access token."""
    user = await User.find_one(User.email == body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _auth_response(user)