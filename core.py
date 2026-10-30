import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

log = logging.getLogger("bot")
_props = DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)

dp = Dispatcher(storage=MemoryStorage())
_state = {"bot": None, "task": None, "router": False, "username": ""}


def get_bot() -> Bot | None:
    return _state["bot"]


def bot_username() -> str:
    return _state["username"]


async def validate(token: str) -> str | None:
    """نام کاربری ربات را برمی‌گرداند؛ اگر توکن نامعتبر بود None."""
    b = Bot(token, default=_props)
    try:
        return (await b.get_me()).username
    except Exception:
        return None
    finally:
        await b.session.close()


async def _run(b: Bot):
    try:
        await dp.start_polling(b, handle_signals=False)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("polling stopped")


async def start(token: str) -> str:
    """ربات را با توکن داده‌شده (دوباره) راه‌اندازی می‌کند."""
    await stop()
    b = Bot(token, default=_props)
    try:
        me = await b.get_me()
    except Exception:
        await b.session.close()
        raise
    if not _state["router"]:
        from botapp import handlers
        dp.include_router(handlers.router)
        _state["router"] = True
    _state.update(bot=b, username=me.username, task=asyncio.create_task(_run(b)))
    return me.username


async def stop():
    t, b = _state["task"], _state["bot"]
    _state.update(task=None, bot=None, username="")
    if t:
        t.cancel()
        try:
            await t
        except BaseException:
            pass
    if b:
        await b.session.close()


async def notify(tg_id: int, text: str):
    b = get_bot()
    if not b:
        return
    try:
        await b.send_message(tg_id, text)
    except Exception as e:
        log.warning("notify %s failed: %s", tg_id, e)


async def send_once(token: str, chat_id: int, text: str) -> bool:
    """ارسال یک پیام با توکن مشخص (برای کد تایید راه‌اندازی اولیه)."""
    b = Bot(token, default=_props)
    try:
        await b.send_message(chat_id, text)
        return True
    except Exception:
        return False
    finally:
        await b.session.close()
