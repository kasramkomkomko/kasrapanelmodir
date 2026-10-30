import asyncio
import logging
import os

import uvicorn

import settings
from config import PORT
from db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main():
    await init_db()
    await settings.load()

    # اختیاری: اگر کسی ترجیح داد با Variables راه بیندازد
    if not settings.get("web_pass_hash") and all(os.getenv(k) for k in ("BOT_TOKEN", "ADMIN_IDS", "WEB_PASS")):
        from web.app import hash_pw
        await settings.set_many({"bot_token": os.environ["BOT_TOKEN"], "admin_ids": os.environ["ADMIN_IDS"],
                                 "web_pass_hash": hash_pw(os.environ["WEB_PASS"]), "brand": "soulsvpn"})

    from botapp import core
    from web.app import app

    async def boot():
        tok = settings.get("bot_token")
        if tok:
            try:
                logging.info("bot started: @%s", await core.start(tok))
            except Exception:
                logging.exception("bot failed to start; توکن را از پنل وب بررسی کنید")

    boot_task = asyncio.create_task(boot())
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info"))
    await server.serve()
    boot_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
