from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts import style, t


def btn(text: str, cb: str | None = None, style: str | None = None, url: str | None = None):
    """style: primary (آبی) / success (سبز) / danger (قرمز). اگر کلاینت پشتیبانی نکند دکمه معمولی دیده می‌شود."""
    extra = {"style": style} if style else {}
    return InlineKeyboardButton(text=text, callback_data=cb, url=url, **extra)


def tbtn(key: str, cb: str | None = None, url: str | None = None, **kw):
    """دکمه‌ای که متن و رنگش از تنظیمات پنل وب خوانده می‌شود."""
    return btn(t(key, **kw), cb, style(key), url)


def back(cb: str = "home"):
    return tbtn("btn_back", cb)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])
