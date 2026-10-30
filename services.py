import json
import logging
import secrets
from datetime import datetime, timedelta

from botapp.core import notify
from models import Order, Service
from panels import adapter_for
from texts import t

log = logging.getLogger("services")


def fmt(n) -> str:
    return f"{int(n):,}"


async def provision(session, user, plan) -> Service:
    """ساخت سرویس روی پنل و کسر موجودی. اگر پنل خطا بدهد چیزی کسر نمی‌شود."""
    if user.balance < plan.price:
        raise ValueError("موجودی کافی نیست")
    ad = adapter_for(plan.panel)
    name = f"u{user.tg_id}_{secrets.token_hex(3)}"
    c = await ad.create_user(name, plan.days, plan.gb)
    svc = Service(
        user_id=user.id, plan_id=plan.id, panel_id=plan.panel_id,
        username=c.username, ref=json.dumps(c.ref), sub_url=c.sub_url,
        expire_at=datetime.utcnow() + timedelta(days=plan.days) if plan.days else None,
    )
    user.balance -= plan.price
    session.add(svc)
    await session.commit()
    return svc


async def renew(session, user, svc) -> None:
    plan = svc.plan
    if user.balance < plan.price:
        raise ValueError("موجودی کافی نیست")
    await adapter_for(svc.panel).renew(svc.username, json.loads(svc.ref), plan.days, plan.gb)
    base = max(svc.expire_at or datetime.utcnow(), datetime.utcnow())
    svc.expire_at = base + timedelta(days=plan.days) if plan.days else None
    user.balance -= plan.price
    session.add(svc)
    await session.commit()


async def set_order(session, order_id: int, approve: bool):
    """تایید/رد شارژ. اگر قبلاً بررسی شده باشد None برمی‌گرداند."""
    o = await session.get(Order, order_id)
    if not o or o.status != "pending":
        return None
    o.status = "paid" if approve else "rejected"
    if approve:
        o.user.balance += o.amount
    await session.commit()
    if approve:
        await notify(o.user.tg_id, t("msg_topup_approved", amount=fmt(o.amount), balance=fmt(o.user.balance)))
    else:
        await notify(o.user.tg_id, t("msg_topup_rejected"))
    return o
