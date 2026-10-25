import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tcancy:tcancy@localhost:5433/tcancy"
)
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
