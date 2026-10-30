import asyncio
import html
import json
import logging
import time
from urllib.parse import urlparse

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

import services
import settings
from botapp.kb import back, btn, kb, tbtn
from config import CURRENCY, WEB_URL
from crypto import enc
from db import Session
from models import Order, Panel, Plan, Service, User
from panels import GB, TYPE_LABELS, adapter_for, detect
from services import fmt
from texts import t

log = logging.getLogger("handlers")
router = Router()


# ───────────── کمکی‌ها ─────────────
def is_admin(uid: int) -> bool:
    return uid in settings.admin_ids()


def min_topup() -> int:
    v = settings.get("min_topup")
    return int(v) if v.isdigit() else 10000


def to_int(s: str):
    s = (s or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    s = s.replace(",", "").replace("،", "").strip()
    return int(s) if s.isdigit() else None


def esc(s) -> str:
    return html.escape(str(s or ""))


async def get_user(s, tu) -> User:
    u = (await s.execute(select(User).where(User.tg_id == tu.id))).scalar_one_or_none()
    if not u:
        u = User(tg_id=tu.id, username=tu.username or tu.full_name or "")
        s.add(u)
        await s.commit()
    return u


async def show(c: CallbackQuery, text: str, markup=None):
    try:
        await c.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return
        await c.message.answer(text, reply_markup=markup)


def main_menu(uid: int):
    rows = [
        [tbtn("btn_buy", "buy")],
        [tbtn("btn_my", "my"), tbtn("btn_wallet", "wallet")],
        [tbtn("btn_support", "support")],
    ]
    if is_admin(uid):
        rows.append([tbtn("btn_admin", "admin")])
    return kb(*rows)


def plan_line(p: Plan) -> str:
    gb = f"{p.gb} گیگ" if p.gb else "نامحدود"
    days = f"{p.days} روزه" if p.days else "بدون انقضا"
    return f"{days} • {gb}"


class BanMW(BaseMiddleware):
    async def __call__(self, handler, event, data):
        tu = data.get("event_from_user")
        if tu and not is_admin(tu.id):
            async with Session() as s:
                banned = (await s.execute(select(User.banned).where(User.tg_id == tu.id))).scalar()
            if banned:
                return
        return await handler(event, data)


router.message.outer_middleware(BanMW())
router.callback_query.outer_middleware(BanMW())


class TopUp(StatesGroup):
    amount = State()
    receipt = State()


class AddPanel(StatesGroup):
    url = State()
    user = State()
    pwd = State()
    name = State()


class Broadcast(StatesGroup):
    text = State()


# ───────────── منوی اصلی ─────────────
@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    async with Session() as s:
        await get_user(s, m.from_user)
    await m.answer(t("msg_start", name=esc(m.from_user.first_name)), reply_markup=main_menu(m.from_user.id))


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(t("msg_cancelled"), reply_markup=main_menu(m.from_user.id))


@router.callback_query(F.data == "home")
async def home(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    await show(c, t("msg_menu"), main_menu(c.from_user.id))


@router.callback_query(F.data == "support")
async def support(c: CallbackQuery):
    await c.answer()
    await show(c, t("msg_support"), kb([back()]))


# ───────────── خرید ─────────────
@router.callback_query(F.data == "buy")
async def buy(c: CallbackQuery):
    await c.answer()
    async with Session() as s:
        plans = (await s.execute(
            select(Plan).join(Panel, Plan.panel_id == Panel.id)
            .where(Plan.active.is_(True), Panel.active.is_(True)).order_by(Plan.price)
        )).scalars().all()
    if not plans:
        return await show(c, t("msg_no_plans"), kb([back()]))
    rows = [[tbtn("btn_plan", f"plan:{p.id}", plan=esc(p.name), price=fmt(p.price))] for p in plans]
    rows.append([back()])
    await show(c, t("msg_buy_title"), kb(*rows))


@router.callback_query(F.data.startswith("plan:"))
async def plan_view(c: CallbackQuery):
    await c.answer()
    async with Session() as s:
        p = await s.get(Plan, int(c.data.split(":")[1]))
        u = await get_user(s, c.from_user)
    if not p or not p.active:
        return await show(c, t("msg_plan_gone"), kb([back()]))
    text = t("msg_plan_view", plan=esc(p.name), details=plan_line(p), price=fmt(p.price), balance=fmt(u.balance))
    await show(c, text, kb([tbtn("btn_confirm", f"pay:{p.id}"), tbtn("btn_cancel", "buy")]))


@router.callback_query(F.data.startswith("pay:"))
async def pay(c: CallbackQuery):
    async with Session() as s:
        p = await s.get(Plan, int(c.data.split(":")[1]))
        u = await get_user(s, c.from_user)
        if not p or not p.active:
            await c.answer()
            return await show(c, t("msg_plan_gone"), kb([back()]))
        if u.balance < p.price:
            await c.answer()
            return await show(c, t("msg_not_enough", need=fmt(p.price - u.balance)),
                              kb([tbtn("btn_topup", "topup")], [back()]))
        await c.answer(t("msg_building")[:190])
        try:
            svc = await services.provision(s, u, p)
        except Exception:
            log.exception("provision failed")
            return await show(c, t("msg_purchase_fail"), kb([back()]))
    await show(c, t("msg_purchase_ok", link=esc(svc.sub_url), balance=fmt(u.balance)),
               kb([tbtn("btn_my", "my")], [back()]))


# ───────────── سرویس‌ها ─────────────
@router.callback_query(F.data == "my")
async def my_services(c: CallbackQuery):
    await c.answer()
    async with Session() as s:
        u = await get_user(s, c.from_user)
        svcs = (await s.execute(select(Service).where(Service.user_id == u.id).order_by(Service.id.desc()))).scalars().all()
    if not svcs:
        return await show(c, t("msg_no_services"), kb([tbtn("btn_buy", "buy")], [back()]))
    rows = [[btn(f"{x.plan.name} • {x.username}", f"svc:{x.id}")] for x in svcs[:20]]
    rows.append([back()])
    await show(c, t("msg_my_title"), kb(*rows))


async def _own_service(s, c: CallbackQuery, sid: int):
    svc = await s.get(Service, sid)
    if not svc or svc.user.tg_id != c.from_user.id:
        return None
    return svc


@router.callback_query(F.data.startswith("svc:"))
async def svc_view(c: CallbackQuery):
    await c.answer()
    async with Session() as s:
        svc = await _own_service(s, c, int(c.data.split(":")[1]))
        if not svc:
            return await show(c, t("msg_service_gone"), kb([back()]))
        try:
            u = await adapter_for(svc.panel).usage(svc.username, json.loads(svc.ref))
            total = f"{u.total / GB:.1f} گیگ" if u.total else "نامحدود"
            left = f"{max(0, int((u.expire - time.time()) / 86400))} روز" if u.expire else "نامحدود"
            info = f"مصرف: {u.used / GB:.2f} از {total}\nزمان باقی‌مانده: {left}"
        except Exception:
            log.exception("usage failed")
            info = "وضعیت مصرف الان در دسترس نیست."
        text = t("msg_service_view", plan=esc(svc.plan.name), info=info, link=esc(svc.sub_url))
        price = fmt(svc.plan.price)
    await show(c, text, kb([tbtn("btn_renew", f"renew:{svc.id}", price=price)], [back("my")]))


@router.callback_query(F.data.startswith("renew:"))
async def svc_renew(c: CallbackQuery):
    async with Session() as s:
        svc = await _own_service(s, c, int(c.data.split(":")[1]))
        u = await get_user(s, c.from_user)
        if not svc:
            await c.answer()
            return await show(c, t("msg_service_gone"), kb([back()]))
        if u.balance < svc.plan.price:
            await c.answer()
            return await show(c, t("msg_renew_no_balance"), kb([tbtn("btn_topup", "topup")], [back()]))
        await c.answer("⏳")
        try:
            await services.renew(s, u, svc)
        except Exception:
            log.exception("renew failed")
            return await show(c, t("msg_renew_fail"), kb([back()]))
    await show(c, t("msg_renew_ok"), kb([tbtn("btn_my", "my")], [back()]))


# ───────────── کیف پول ─────────────
@router.callback_query(F.data == "wallet")
async def wallet(c: CallbackQuery):
    await c.answer()
    async with Session() as s:
        u = await get_user(s, c.from_user)
    await show(c, t("msg_wallet", balance=fmt(u.balance)), kb([tbtn("btn_topup", "topup")], [back()]))


@router.callback_query(F.data == "topup")
async def topup(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(TopUp.amount)
    await show(c, t("msg_topup_amount", min=fmt(min_topup())))


@router.message(TopUp.amount)
async def topup_amount(m: Message, state: FSMContext):
    n = to_int(m.text)
    if not n or n < min_topup():
        return await m.answer(t("msg_topup_bad", min=fmt(min_topup())))
    await state.update_data(amount=n)
    await state.set_state(TopUp.receipt)
    await m.answer(t("msg_topup_card", amount=fmt(n), card=esc(settings.get("card_number") or "—"),
                     holder=esc(settings.get("card_holder"))))


@router.message(TopUp.receipt, F.photo)
async def topup_receipt(m: Message, state: FSMContext):
    amount = (await state.get_data())["amount"]
    await state.clear()
    fid = m.photo[-1].file_id
    async with Session() as s:
        u = await get_user(s, m.from_user)
        o = Order(user_id=u.id, amount=amount, receipt_file_id=fid)
        s.add(o)
        await s.commit()
    await m.answer(t("msg_topup_received"), reply_markup=main_menu(m.from_user.id))
    cap = (f"🧾 درخواست شارژ #{o.id}\nکاربر: {esc(m.from_user.full_name)} (<code>{m.from_user.id}</code>)\n"
           f"مبلغ: <b>{fmt(amount)}</b> {CURRENCY}")
    markup = kb([btn("✅ تایید", f"oa:{o.id}", "success"), btn("❌ رد", f"or:{o.id}", "danger")])
    for aid in settings.admin_ids():
        try:
            await m.bot.send_photo(aid, fid, caption=cap, reply_markup=markup)
        except Exception:
            log.warning("cannot notify admin %s", aid)


@router.message(TopUp.receipt)
async def topup_receipt_bad(m: Message):
    await m.answer(t("msg_topup_need_photo"))


async def _order_decision(c: CallbackQuery, approve: bool):
    if not is_admin(c.from_user.id):
        return await c.answer("⛔ دسترسی ندارید", show_alert=True)
    async with Session() as s:
        o = await services.set_order(s, int(c.data.split(":")[1]), approve)
    if not o:
        return await c.answer("این درخواست قبلاً بررسی شده.", show_alert=True)
    await c.answer("انجام شد")
    tag = "✅ تایید شد" if approve else "❌ رد شد"
    try:
        await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{tag} توسط {esc(c.from_user.full_name)}", reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("oa:"))
async def order_ok(c: CallbackQuery):
    await _order_decision(c, True)


@router.callback_query(F.data.startswith("or:"))
async def order_no(c: CallbackQuery):
    await _order_decision(c, False)


# ───────────── مدیریت داخل ربات ─────────────
def admin_menu():
    rows = [
        [btn("📊 آمار", "a:stats", "primary"), btn("🖥 پنل‌ها", "a:panels", "primary")],
        [btn("➕ افزودن پنل", "a:addpanel", "success"), btn("📢 پیام همگانی", "a:bc", "danger")],
    ]
    if WEB_URL:
        rows.append([btn("🌐 پنل وب", url=WEB_URL)])
    rows.append([back()])
    return kb(*rows)


async def _guard(c: CallbackQuery) -> bool:
    if not is_admin(c.from_user.id):
        await c.answer("⛔", show_alert=True)
        return False
    return True


@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery, state: FSMContext):
    if not await _guard(c):
        return
    await c.answer()
    await state.clear()
    await show(c, "⚙️ پنل مدیریت\nپلن‌ها، متن‌ها، کاربران و سفارش‌ها از پنل وب مدیریت می‌شود.", admin_menu())


@router.message(Command("admin"))
async def admin_cmd(m: Message):
    if is_admin(m.from_user.id):
        await m.answer("⚙️ پنل مدیریت", reply_markup=admin_menu())


@router.callback_query(F.data == "a:stats")
async def a_stats(c: CallbackQuery):
    if not await _guard(c):
        return
    await c.answer()
    async with Session() as s:
        users = await s.scalar(select(func.count(User.id)))
        svcs = await s.scalar(select(func.count(Service.id)))
        pend = await s.scalar(select(func.count(Order.id)).where(Order.status == "pending"))
        inc = await s.scalar(select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "paid"))
    await show(c, f"📊 کاربران: {users}\n📦 سرویس‌ها: {svcs}\n🧾 رسید در انتظار: {pend}\n💵 مجموع شارژ تایید شده: {fmt(inc)} {CURRENCY}",
               kb([back("admin")]))


@router.callback_query(F.data == "a:panels")
async def a_panels(c: CallbackQuery):
    if not await _guard(c):
        return
    await c.answer("در حال بررسی اتصال...")
    async with Session() as s:
        panels = (await s.execute(select(Panel))).scalars().all()
    if not panels:
        return await show(c, "هنوز پنلی اضافه نشده.", kb([btn("➕ افزودن پنل", "a:addpanel", "success")], [back("admin")]))
    res = await asyncio.gather(*[adapter_for(p).check() for p in panels])
    lines = [f"{'🟢' if ok else '🔴'} <b>{esc(p.name)}</b> — {TYPE_LABELS.get(p.ptype, p.ptype)}" for p, ok in zip(panels, res)]
    await show(c, "🖥 پنل‌ها:\n\n" + "\n".join(lines), kb([back("admin")]))


@router.callback_query(F.data == "a:addpanel")
async def a_addpanel(c: CallbackQuery, state: FSMContext):
    if not await _guard(c):
        return
    await c.answer()
    await state.set_state(AddPanel.url)
    await show(c, "آدرس پنل را بفرستید.\nمثال: <code>https://panel.example.com:8000</code>\n"
                  "برای هیدیفای آدرس را با مسیر پروکسی بفرستید.\nلغو: /cancel")


@router.message(AddPanel.url)
async def ap_url(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    u = (m.text or "").strip()
    if not urlparse(u if "://" in u else "https://" + u).hostname:
        return await m.answer("آدرس معتبر نیست.")
    await state.update_data(url=u)
    await state.set_state(AddPanel.user)
    await m.answer("نام کاربری ادمین پنل را بفرستید.\n(برای هیدیفای یک خط تیره «-» بفرستید)")


@router.message(AddPanel.user)
async def ap_user(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.update_data(user=(m.text or "").strip())
    await state.set_state(AddPanel.pwd)
    await m.answer("رمز عبور را بفرستید (برای هیدیفای: API Key).\nپیام شما بعد از دریافت حذف می‌شود.")


@router.message(AddPanel.pwd)
async def ap_pwd(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    pwd = (m.text or "").strip()
    try:
        await m.delete()
    except Exception:
        pass
    d = await state.get_data()
    wait = await m.answer("⏳ در حال شناسایی نوع پنل...")
    ad = await detect(d["url"], d["user"], pwd)
    if not ad:
        await state.clear()
        return await wait.edit_text("❌ پنل شناسایی نشد. آدرس، نام کاربری و رمز را بررسی کنید و دوباره تلاش کنید.",
                                    reply_markup=kb([btn("🔁 تلاش دوباره", "a:addpanel", "primary")], [back("admin")]))
    await state.update_data(pwd=pwd, url=ad.url, ptype=ad.ptype)
    await state.set_state(AddPanel.name)
    await wait.edit_text(f"✅ نوع پنل: <b>{TYPE_LABELS[ad.ptype]}</b>\nیک نام برای این پنل بفرستید (مثلاً «آلمان ۱»).")


@router.message(AddPanel.name)
async def ap_name(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    d = await state.get_data()
    await state.clear()
    async with Session() as s:
        s.add(Panel(name=(m.text or "").strip()[:100] or urlparse(d["url"]).hostname, url=d["url"], ptype=d["ptype"],
                    username=d["user"], password_enc=enc(d["pwd"])))
        await s.commit()
    await m.answer("✅ پنل ذخیره شد. حالا از پنل وب برایش پلن بسازید.", reply_markup=admin_menu())


@router.callback_query(F.data == "a:bc")
async def a_bc(c: CallbackQuery, state: FSMContext):
    if not await _guard(c):
        return
    await c.answer()
    await state.set_state(Broadcast.text)
    await show(c, "پیام همگانی را بفرستید (متن، عکس یا هر نوع پیامی). لغو: /cancel")


@router.message(Broadcast.text)
async def bc_send(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    await state.clear()
    async with Session() as s:
        ids = (await s.execute(select(User.tg_id).where(User.banned.is_(False)))).scalars().all()
    ok = 0
    for i in ids:
        try:
            await m.copy_to(i)
            ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await m.answer(f"📢 برای {ok} از {len(ids)} کاربر ارسال شد.", reply_markup=admin_menu())
