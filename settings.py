"""تنظیمات داخل دیتابیس؛ کش در حافظه تا بات و وب هر دو فوراً تغییرات را ببینند."""
import secrets

from sqlalchemy import delete, select

from db import Session
from models import Setting

_c: dict[str, str] = {}


async def load():
    async with Session() as s:
        for r in (await s.execute(select(Setting))).scalars():
            _c[r.key] = r.value
    if "secret_key" not in _c:
        await set_many({"secret_key": secrets.token_urlsafe(48)})


async def set_many(d: dict):
    async with Session() as s:
        for k, v in d.items():
            row = await s.get(Setting, k)
            if row:
                row.value = v
            else:
                s.add(Setting(key=k, value=v))
        await s.commit()
    _c.update(d)


async def delete_keys(keys):
    keys = list(keys)
    if not keys:
        return
    async with Session() as s:
        await s.execute(delete(Setting).where(Setting.key.in_(keys)))
        await s.commit()
    for k in keys:
        _c.pop(k, None)


def get(key: str, default=""):
    return _c.get(key, default)


def admin_ids() -> list[int]:
    return [int(x) for x in get("admin_ids").replace(" ", "").split(",") if x.lstrip("-").isdigit()]


def brand() -> str:
    return get("brand") or "soulsvpn"
