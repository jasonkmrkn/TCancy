import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tcancy:tcancy@localhost:5433/tcancy"
)
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")

SESSION_SECRET = os.environ.get("SESSION_SECRET", "")

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").strip().lower() in ("1", "true", "yes")