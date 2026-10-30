import os

PORT = int(os.getenv("PORT", "8000"))
CURRENCY = "تومان"

_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
WEB_URL = os.getenv("WEB_URL") or (f"https://{_domain}" if _domain else "")

_db = os.getenv("DATABASE_URL", "")
if not _db:
    # اگر Volume روی /data مونت شده باشد، دیتابیس آنجا دائمی می‌ماند
    _db = "sqlite+aiosqlite:////data/soulsvpn.db" if os.path.isdir("/data") else "sqlite+aiosqlite:///data.db"
if _db.startswith("postgres://"):
    _db = _db.replace("postgres://", "postgresql+asyncpg://", 1)
elif _db.startswith("postgresql://"):
    _db = _db.replace("postgresql://", "postgresql+asyncpg://", 1)
DATABASE_URL = _db
EPHEMERAL_DB = _db.startswith("sqlite") and not _db.startswith("sqlite+aiosqlite:////data/")
