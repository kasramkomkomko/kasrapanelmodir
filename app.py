import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import defaultdict
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

import services
import settings
from botapp import core
from config import CURRENCY, EPHEMERAL_DB, WEB_URL
from crypto import enc
from db import Session
from models import Order, Panel, Plan, Service, User
from panels import TYPE_LABELS, adapter_for, detect
from texts import D

log = logging.getLogger("web")
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["money"] = lambda v: f"{int(v or 0):,}"
templates.env.globals.update(CURRENCY=CURRENCY, TYPE_LABELS=TYPE_LABELS, brand=settings.brand)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.get("secret_key"), max_age=60 * 60 * 24 * 7,
                   https_only=WEB_URL.startswith("https"), same_site="lax")


def configured() -> bool:
    return bool(settings.get("web_pass_hash"))


def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    return f"{salt}${hashlib.scrypt(pw.encode(), salt=salt.encode(), n=2 ** 14, r=8, p=1).hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$")
        return hmac.compare_digest(hash_pw(pw, salt).split("$")[1], h)
    except Exception:
        return False


def need_login(request: Request):
    if not configured():
        raise HTTPException(status_code=303, headers={"Location": "/setup"})
    if not request.session.get("auth"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


def flash(request: Request, msg: str, kind: str = "ok"):
    request.session["flash"] = [msg, kind]


def render(request: Request, name: str, **ctx):
    f = request.session.pop("flash", None)
    return templates.TemplateResponse(request, name, {"flash": f, "path": request.url.path, **ctx})


def back(path: str):
    return RedirectResponse(path, status_code=303)


@app.get("/healthz")
async def health():
    return {"ok": True}


# ───────────── راه‌اندازی اولیه (فقط یک‌بار) ─────────────
_setup = {"token": None, "username": None, "admin": None, "code": None, "tries": 0}


@app.get("/setup")
async def setup_page(request: Request):
    if configured():
        return back("/login")
    step = 1 if not _setup["token"] else (2 if not _setup["admin"] else 3)
    return render(request, "setup.html", step=step, bot=_setup["username"], admin=_setup["admin"])


@app.post("/setup/token")
async def setup_token(request: Request, token: str = Form(...)):
    if configured():
        return back("/login")
    un = await core.validate(token.strip())
    if not un:
        flash(request, "توکن نامعتبر است. از BotFather دوباره کپی کنید.", "bad")
        return back("/setup")
    _setup.update(token=token.strip(), username=un, admin=None, code=None, tries=0)
    return back("/setup")


@app.post("/setup/admin")
async def setup_admin(request: Request, admin_id: str = Form(...)):
    if configured() or not _setup["token"]:
        return back("/setup")
    if not admin_id.strip().isdigit():
        flash(request, "شناسه عددی تلگرام را وارد کنید.", "bad")
        return back("/setup")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    ok = await core.send_once(_setup["token"], int(admin_id), f"🔐 کد تایید راه‌اندازی پنل: <code>{code}</code>")
    if not ok:
        flash(request, f"ارسال کد ممکن نشد. اول ربات @{_setup['username']} را در تلگرام استارت کنید و شناسه را دوباره بررسی کنید.", "bad")
        return back("/setup")
    _setup.update(admin=int(admin_id), code=code, tries=0)
    return back("/setup")


@app.post("/setup/reset")
async def setup_reset():
    _setup.update(token=None, username=None, admin=None, code=None, tries=0)
    return back("/setup")


@app.post("/setup/finish")
async def setup_finish(request: Request, code: str = Form(...), password: str = Form(...), password2: str = Form(...)):
    if configured() or not _setup["code"]:
        return back("/setup")
    _setup["tries"] += 1
    if _setup["tries"] > 5:
        _setup.update(admin=None, code=None, tries=0)
        flash(request, "تلاش بیش از حد. دوباره شناسه ادمین را وارد کنید.", "bad")
        return back("/setup")
    if not secrets.compare_digest(code.strip(), _setup["code"]):
        flash(request, "کد تایید اشتباه است.", "bad")
        return back("/setup")
    if len(password) < 6 or password != password2:
        flash(request, "رمز باید حداقل ۶ کاراکتر باشد و تکرارش یکی باشد.", "bad")
        return back("/setup")
    await settings.set_many({"bot_token": _setup["token"], "admin_ids": str(_setup["admin"]),
                             "web_pass_hash": hash_pw(password), "brand": "soulsvpn"})
    try:
        await core.start(_setup["token"])
    except Exception:
        log.exception("bot start failed")
    _setup.update(token=None, username=None, admin=None, code=None, tries=0)
    request.session["auth"] = True
    flash(request, "راه‌اندازی کامل شد. ربات فعال است.")
    return back("/")


# ───────────── ورود ─────────────
_attempts: dict[str, list[float]] = defaultdict(list)


@app.get("/login")
async def login_page(request: Request):
    if not configured():
        return back("/setup")
    return render(request, "login.html")


@app.post("/login")
async def login(request: Request, password: str = Form("")):
    ip = request.client.host if request.client else "?"
    now = time.time()
    _attempts[ip] = [x for x in _attempts[ip] if now - x < 300]
    if len(_attempts[ip]) >= 5:
        flash(request, "تلاش‌های ناموفق زیاد بود. چند دقیقه بعد دوباره امتحان کنید.", "bad")
        return back("/login")
    if not check_pw(password, settings.get("web_pass_hash")):
        _attempts[ip].append(now)
        flash(request, "رمز اشتباه است.", "bad")
        return back("/login")
    request.session["auth"] = True
    return back("/")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return back("/login")


# ───────────── بخش‌های محافظت‌شده ─────────────
r = APIRouter(dependencies=[Depends(need_login)])


@r.get("/")
async def dashboard(request: Request):
    async with Session() as s:
        stats = {
            "users": await s.scalar(select(func.count(User.id))),
            "services": await s.scalar(select(func.count(Service.id))),
            "pending": await s.scalar(select(func.count(Order.id)).where(Order.status == "pending")),
            "income": await s.scalar(select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "paid")),
            "panels": await s.scalar(select(func.count(Panel.id))),
        }
        pend = (await s.execute(select(Order).where(Order.status == "pending").order_by(Order.id.desc()).limit(5))).scalars().all()
    return render(request, "dashboard.html", stats=stats, pend=pend, bot_user=core.bot_username(), ephemeral=EPHEMERAL_DB)


# ───────────── تنظیمات ─────────────
@r.get("/settings")
async def settings_page(request: Request):
    keys = ["brand", "owner_name", "support_id", "card_number", "card_holder", "min_topup", "admin_ids"]
    return render(request, "settings.html", v={k: settings.get(k) for k in keys}, bot_user=core.bot_username())


@r.post("/settings/general")
async def settings_general(request: Request, brand: str = Form(""), owner_name: str = Form(""), support_id: str = Form(""),
                           card_number: str = Form(""), card_holder: str = Form(""), min_topup: str = Form("10000"),
                           admin_ids: str = Form("")):
    ids = [x for x in admin_ids.replace("،", ",").replace(" ", "").split(",") if x]
    if not ids or not all(x.isdigit() for x in ids):
        flash(request, "شناسه ادمین‌ها باید عددی باشد (چند شناسه با کاما جدا شود).", "bad")
        return back("/settings")
    await settings.set_many({"brand": brand.strip() or "soulsvpn", "owner_name": owner_name.strip(),
                             "support_id": support_id.strip(), "card_number": card_number.strip(),
                             "card_holder": card_holder.strip(),
                             "min_topup": min_topup.strip() if min_topup.strip().isdigit() else "10000",
                             "admin_ids": ",".join(ids)})
    flash(request, "تنظیمات ذخیره شد.")
    return back("/settings")


@r.post("/settings/token")
async def settings_token(request: Request, token: str = Form(...)):
    token = token.strip()
    if not await core.validate(token):
        flash(request, "توکن نامعتبر است.", "bad")
        return back("/settings")
    await settings.set_many({"bot_token": token})
    try:
        un = await core.start(token)
        flash(request, f"ربات @{un} با توکن جدید فعال شد.")
    except Exception:
        log.exception("restart failed")
        flash(request, "توکن ذخیره شد ولی ربات اجرا نشد.", "bad")
    return back("/settings")


@r.post("/settings/password")
async def settings_password(request: Request, current: str = Form(...), new: str = Form(...)):
    if not check_pw(current, settings.get("web_pass_hash")):
        flash(request, "رمز فعلی اشتباه است.", "bad")
    elif len(new) < 6:
        flash(request, "رمز جدید باید حداقل ۶ کاراکتر باشد.", "bad")
    else:
        await settings.set_many({"web_pass_hash": hash_pw(new)})
        flash(request, "رمز پنل تغییر کرد.")
    return back("/settings")


# ───────────── متن پیام‌ها و دکمه‌ها ─────────────
@r.get("/texts")
async def texts_page(request: Request):
    groups: dict[str, list] = {}
    for key, it in D.items():
        st = settings.get("s_" + key, None)
        groups.setdefault(it["group"], []).append({
            "key": key, **it,
            "value": settings.get("t_" + key) or it["text"],
            "style_now": "default" if st is None else (st or "none"),
        })
    order = ["دکمه‌ها"] + [g for g in groups if g != "دکمه‌ها"]
    return render(request, "texts.html", groups=[(g, groups[g]) for g in order])


@r.post("/texts/save")
async def texts_save(request: Request):
    f = await request.form()
    to_set, to_del = {}, []
    for key, it in D.items():
        val = f.get("t_" + key)
        if val is not None:
            val = val.replace("\r\n", "\n")
            if not val.strip() or val == it["text"]:
                to_del.append("t_" + key)
            else:
                to_set["t_" + key] = val
        if it["kind"] == "btn":
            st = f.get("s_" + key, "default")
            if st == "default":
                to_del.append("s_" + key)
            elif st in ("none", "primary", "success", "danger"):
                to_set["s_" + key] = "" if st == "none" else st
    await settings.delete_keys(to_del)
    if to_set:
        await settings.set_many(to_set)
    flash(request, "متن‌ها و دکمه‌ها ذخیره شد و همین حالا روی ربات اعمال می‌شود.")
    return back("/texts")


@r.post("/texts/reset")
async def texts_reset(request: Request):
    await settings.delete_keys([k for k in list(settings._c) if k.startswith(("t_", "s_"))])
    flash(request, "همه‌ی متن‌ها به حالت پیش‌فرض برگشت.")
    return back("/texts")


# ───────────── پیام همگانی و شخصی ─────────────
_bc = {"running": False, "sent": 0, "failed": 0, "total": 0}


async def _send(bot, chat_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id, text)
        return True
    except TelegramBadRequest as e:
        if "parse" in str(e).lower():
            try:
                await bot.send_message(chat_id, text, parse_mode=None)
                return True
            except Exception:
                return False
        return False
    except Exception:
        return False


async def _broadcast(text: str):
    bot = core.get_bot()
    async with Session() as s:
        ids = (await s.execute(select(User.tg_id).where(User.banned.is_(False)))).scalars().all()
    _bc.update(running=True, sent=0, failed=0, total=len(ids))
    for i in ids:
        if await _send(bot, i, text):
            _bc["sent"] += 1
        else:
            _bc["failed"] += 1
        await asyncio.sleep(0.05)
    _bc["running"] = False


_tasks: set = set()


@r.get("/broadcast")
async def broadcast_page(request: Request, to: str = ""):
    return render(request, "broadcast.html", bc=_bc, to=to, online=bool(core.get_bot()))


@r.post("/broadcast/all")
async def broadcast_all(request: Request, text: str = Form(...)):
    if not core.get_bot():
        flash(request, "ربات فعال نیست.", "bad")
    elif _bc["running"]:
        flash(request, "یک ارسال همگانی در حال انجام است.", "bad")
    else:
        t = asyncio.create_task(_broadcast(text))
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
        flash(request, "ارسال همگانی شروع شد.")
    return back("/broadcast")


@r.post("/broadcast/user")
async def broadcast_user(request: Request, tg_id: str = Form(...), text: str = Form(...)):
    bot = core.get_bot()
    if not bot:
        flash(request, "ربات فعال نیست.", "bad")
    elif not tg_id.strip().isdigit():
        flash(request, "شناسه عددی تلگرام را وارد کنید.", "bad")
    else:
        ok = await _send(bot, int(tg_id), text)
        flash(request, "پیام ارسال شد." if ok else "ارسال نشد (کاربر ربات را استارت نکرده یا مسدود کرده).", "ok" if ok else "bad")
    return back("/broadcast")


# پنل‌ها
@r.get("/panels")
async def panels_page(request: Request):
    async with Session() as s:
        panels = (await s.execute(select(Panel).order_by(Panel.id))).scalars().all()
        counts = dict((await s.execute(select(Plan.panel_id, func.count(Plan.id)).group_by(Plan.panel_id))).all())
    return render(request, "panels.html", panels=panels, counts=counts)


@r.post("/panels/add")
async def panel_add(request: Request, name: str = Form(""), url: str = Form(...), username: str = Form(""),
                    password: str = Form(...), inbound_id: str = Form(""), sub_base: str = Form("")):
    extra = {}
    if inbound_id.strip().isdigit():
        extra["inbound_id"] = int(inbound_id)
    if sub_base.strip():
        extra["sub_base"] = sub_base.strip()
    ad = await detect(url, username.strip(), password, extra)
    if not ad:
        flash(request, "پنل شناسایی نشد. آدرس، نام کاربری و رمز را بررسی کنید.", "bad")
        return back("/panels")
    async with Session() as s:
        s.add(Panel(name=name.strip() or ad.url, url=ad.url, ptype=ad.ptype, username=username.strip(),
                    password_enc=enc(password), extra=json.dumps(extra)))
        await s.commit()
    flash(request, f"پنل شناسایی و ذخیره شد: {TYPE_LABELS[ad.ptype]}")
    return back("/panels")


@r.post("/panels/{pid}/test")
async def panel_test(request: Request, pid: int):
    async with Session() as s:
        p = await s.get(Panel, pid)
    ok = bool(p) and await adapter_for(p).check()
    flash(request, "اتصال برقرار است." if ok else "اتصال برقرار نشد.", "ok" if ok else "bad")
    return back("/panels")


@r.post("/panels/{pid}/toggle")
async def panel_toggle(pid: int):
    async with Session() as s:
        p = await s.get(Panel, pid)
        if p:
            p.active = not p.active
            await s.commit()
    return back("/panels")


@r.post("/panels/{pid}/delete")
async def panel_delete(request: Request, pid: int):
    async with Session() as s:
        used = await s.scalar(select(func.count(Plan.id)).where(Plan.panel_id == pid)) \
            + await s.scalar(select(func.count(Service.id)).where(Service.panel_id == pid))
        if used:
            flash(request, "این پنل پلن یا سرویس دارد. به‌جای حذف، غیرفعالش کنید.", "bad")
        else:
            p = await s.get(Panel, pid)
            if p:
                await s.delete(p)
                await s.commit()
            flash(request, "پنل حذف شد.")
    return back("/panels")


# پلن‌ها
@r.get("/plans")
async def plans_page(request: Request):
    async with Session() as s:
        plans = (await s.execute(select(Plan).order_by(Plan.price))).scalars().all()
        panels = (await s.execute(select(Panel).where(Panel.active.is_(True)))).scalars().all()
    return render(request, "plans.html", plans=plans, panels=panels)


@r.post("/plans/add")
async def plan_add(request: Request, name: str = Form(...), panel_id: int = Form(...), days: int = Form(30),
                   gb: int = Form(0), price: int = Form(...)):
    async with Session() as s:
        s.add(Plan(name=name.strip(), panel_id=panel_id, days=max(days, 0), gb=max(gb, 0), price=max(price, 0)))
        await s.commit()
    flash(request, "پلن اضافه شد.")
    return back("/plans")


@r.post("/plans/{pid}/toggle")
async def plan_toggle(pid: int):
    async with Session() as s:
        p = await s.get(Plan, pid)
        if p:
            p.active = not p.active
            await s.commit()
    return back("/plans")


@r.post("/plans/{pid}/delete")
async def plan_delete(request: Request, pid: int):
    async with Session() as s:
        if await s.scalar(select(func.count(Service.id)).where(Service.plan_id == pid)):
            flash(request, "این پلن سرویس فعال دارد. به‌جای حذف، غیرفعالش کنید.", "bad")
        else:
            p = await s.get(Plan, pid)
            if p:
                await s.delete(p)
                await s.commit()
            flash(request, "پلن حذف شد.")
    return back("/plans")


# سفارش‌ها
@r.get("/orders")
async def orders_page(request: Request):
    async with Session() as s:
        orders = (await s.execute(select(Order).order_by(Order.id.desc()).limit(100))).scalars().all()
    return render(request, "orders.html", orders=orders)


@r.post("/orders/{oid}/{action}")
async def order_action(request: Request, oid: int, action: str):
    if action not in ("approve", "reject"):
        raise HTTPException(404)
    async with Session() as s:
        o = await services.set_order(s, oid, action == "approve")
    flash(request, "انجام شد." if o else "این درخواست قبلاً بررسی شده.", "ok" if o else "bad")
    return back("/orders")


@r.get("/receipt/{oid}")
async def receipt(oid: int):
    async with Session() as s:
        o = await s.get(Order, oid)
    bot = core.get_bot()
    if not o or not o.receipt_file_id or not bot:
        raise HTTPException(404)
    f = await bot.get_file(o.receipt_file_id)
    buf = await bot.download_file(f.file_path)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


# کاربران
@r.get("/users")
async def users_page(request: Request):
    async with Session() as s:
        users = (await s.execute(select(User).order_by(User.id.desc()).limit(200))).scalars().all()
    return render(request, "users.html", users=users)


@r.post("/users/{uid}/balance")
async def user_balance(request: Request, uid: int, delta: int = Form(...)):
    async with Session() as s:
        u = await s.get(User, uid)
        if u:
            u.balance = max(0, u.balance + delta)
            await s.commit()
            flash(request, f"موجودی جدید: {u.balance:,} {CURRENCY}")
    return back("/users")


@r.post("/users/{uid}/ban")
async def user_ban(uid: int):
    async with Session() as s:
        u = await s.get(User, uid)
        if u:
            u.banned = not u.banned
            await s.commit()
    return back("/users")


# سرویس‌ها
@r.get("/services")
async def services_page(request: Request):
    async with Session() as s:
        svcs = (await s.execute(select(Service).order_by(Service.id.desc()).limit(200))).scalars().all()
    return render(request, "services.html", svcs=svcs)


@r.post("/services/{sid}/delete")
async def service_delete(request: Request, sid: int):
    async with Session() as s:
        svc = await s.get(Service, sid)
        if svc:
            try:
                await adapter_for(svc.panel).delete(svc.username, json.loads(svc.ref))
            except Exception as e:
                log.warning("panel delete failed: %s", e)
                flash(request, "حذف روی پنل انجام نشد؛ فقط از لیست ربات حذف شد.", "bad")
            await s.delete(svc)
            await s.commit()
    return back("/services")


app.include_router(r)
