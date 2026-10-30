import json

from crypto import dec

from .base import Adapter
from .hiddify import Hiddify
from .marzban import Marzban
from .marzneshin import Marzneshin
from .xui import XUI

ADAPTERS = {c.ptype: c for c in (Hiddify, Marzban, Marzneshin, XUI)}
TYPE_LABELS = {
    "marzban": "Marzban / PasarGuard",
    "marzneshin": "Marzneshin",
    "3xui": "3x-ui / Sanaei / Alireza / X-UI",
    "hiddify": "Hiddify",
}


def _candidates(url: str):
    url = url.strip().rstrip("/")
    if url.startswith(("http://", "https://")):
        return [url]
    return ["https://" + url, "http://" + url]


async def detect(url: str, username: str, password: str, extra: dict | None = None) -> Adapter | None:
    """نوع پنل را از روی رفتار API تشخیص می‌دهد و آداپتور آماده برمی‌گرداند."""
    for u in _candidates(url):
        for cls in (Hiddify, Marzban, Marzneshin, XUI):
            ad = cls(u, username, password, extra)
            if await ad.check():
                return ad
    return None


def adapter_for(panel) -> Adapter:
    return ADAPTERS[panel.ptype](panel.url, panel.username, dec(panel.password_enc), json.loads(panel.extra or "{}"))
