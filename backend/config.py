"""Environment-backed application settings loaded from backend/.env."""

from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "local-development-secret-change-me")
JWT_ALGORITHM: str = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

if JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
    raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive")