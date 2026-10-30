import time
from dataclasses import dataclass, field

GB = 1024 ** 3


class PanelError(Exception):
    pass


@dataclass
class Created:
    username: str
    sub_url: str
    ref: dict = field(default_factory=dict)


@dataclass
class Usage:
    used: int = 0      # بایت
    total: int = 0     # بایت، 0 = نامحدود
    expire: int = 0    # unix ts، 0 = بدون انقضا


def expire_ts(days: int) -> int:
    return int(time.time()) + days * 86400 if days > 0 else 0


def new_expire(current: int, days: int) -> int:
    """تمدید: از انقضای فعلی (اگر هنوز نگذشته) یا از الان."""
    if days <= 0:
        return 0
    return max(int(time.time()), current or 0) + days * 86400


def check_resp(r):
    if r.status_code >= 400:
        raise PanelError(f"{r.status_code}: {r.text[:200]}")
    return r


class Adapter:
    ptype = "base"

    def __init__(self, url: str, username: str, password: str, extra: dict | None = None):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.extra = extra or {}

    async def check(self) -> bool:
        raise NotImplementedError

    async def create_user(self, name: str, days: int, gb: int) -> Created:
        raise NotImplementedError

    async def usage(self, name: str, ref: dict) -> Usage:
        raise NotImplementedError

    async def renew(self, name: str, ref: dict, days: int, gb: int) -> None:
        raise NotImplementedError

    async def delete(self, name: str, ref: dict) -> None:
        raise NotImplementedError
