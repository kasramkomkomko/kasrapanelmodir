"""همه‌ی متن پیام‌ها و دکمه‌های ربات؛ از پنل وب قابل ویرایش است."""
import settings
from config import CURRENCY


def M(group, label, text, vars=""):
    return {"kind": "msg", "group": group, "label": label, "text": text, "vars": vars}


def B(label, text, style=None, vars=""):
    return {"kind": "btn", "group": "دکمه‌ها", "label": label, "text": text, "style": style, "vars": vars}


D = {
    # ── دکمه‌ها
    "btn_buy": B("خرید سرویس", "🛒 خرید سرویس", "primary"),
    "btn_my": B("سرویس‌های من", "📦 سرویس‌های من"),
    "btn_wallet": B("کیف پول", "💰 کیف پول", "success"),
    "btn_support": B("پشتیبانی", "🆘 پشتیبانی"),
    "btn_admin": B("مدیریت (فقط ادمین)", "⚙️ مدیریت", "danger"),
    "btn_back": B("بازگشت", "🔙 بازگشت"),
    "btn_topup": B("شارژ کیف پول", "➕ شارژ کیف پول", "success"),
    "btn_confirm": B("تایید خرید", "✅ خرید", "success"),
    "btn_cancel": B("انصراف", "❌ انصراف", "danger"),
    "btn_renew": B("تمدید", "🔄 تمدید ({price} {currency})", "success", "{price}"),
    "btn_plan": B("دکمه‌ی هر پلن", "{plan} • {price} {currency}", "primary", "{plan} {price}"),
    # ── پیام‌های اصلی
    "msg_start": M("منو", "پیام /start", "سلام {name} 👋\nبه {brand} خوش آمدید. یکی از گزینه‌ها را انتخاب کنید:", "{name}"),
    "msg_menu": M("منو", "منوی اصلی", "منوی اصلی:"),
    "msg_support": M("منو", "پشتیبانی", "برای پشتیبانی به {support} پیام دهید."),
    "msg_cancelled": M("منو", "لغو عملیات", "لغو شد."),
    # ── خرید
    "msg_buy_title": M("خرید", "لیست پلن‌ها", "🛒 پلن مورد نظر را انتخاب کنید:"),
    "msg_no_plans": M("خرید", "پلنی نیست", "فعلاً پلنی برای فروش وجود ندارد."),
    "msg_plan_view": M("خرید", "جزئیات پلن", "<b>{plan}</b>\n{details}\nقیمت: <b>{price}</b> {currency}\nموجودی شما: {balance} {currency}", "{plan} {details} {price} {balance}"),
    "msg_plan_gone": M("خرید", "پلن حذف شده", "این پلن دیگر موجود نیست."),
    "msg_not_enough": M("خرید", "موجودی کافی نیست", "موجودی کافی نیست. <b>{need}</b> {currency} دیگر لازم است.", "{need}"),
    "msg_building": M("خرید", "هشدار در حال ساخت", "⏳ در حال ساخت سرویس..."),
    "msg_purchase_ok": M("خرید", "خرید موفق", "✅ سرویس شما ساخته شد.\n\nلینک اشتراک:\n<code>{link}</code>\n\nموجودی باقی‌مانده: {balance} {currency}", "{link} {balance}"),
    "msg_purchase_fail": M("خرید", "خرید ناموفق", "❌ ساخت سرویس انجام نشد و مبلغی کسر نشد.\nبعداً دوباره تلاش کنید یا به {support} پیام دهید."),
    # ── سرویس‌ها
    "msg_my_title": M("سرویس‌ها", "لیست سرویس‌ها", "📦 سرویس‌های شما:"),
    "msg_no_services": M("سرویس‌ها", "سرویسی ندارد", "هنوز سرویسی ندارید."),
    "msg_service_view": M("سرویس‌ها", "جزئیات سرویس", "<b>{plan}</b>\n{info}\n\nلینک اشتراک:\n<code>{link}</code>", "{plan} {info} {link}"),
    "msg_service_gone": M("سرویس‌ها", "سرویس پیدا نشد", "سرویس پیدا نشد."),
    "msg_renew_ok": M("سرویس‌ها", "تمدید موفق", "✅ سرویس تمدید شد."),
    "msg_renew_fail": M("سرویس‌ها", "تمدید ناموفق", "❌ تمدید انجام نشد و مبلغی کسر نشد. بعداً تلاش کنید."),
    "msg_renew_no_balance": M("سرویس‌ها", "موجودی تمدید کافی نیست", "موجودی برای تمدید کافی نیست."),
    # ── کیف پول
    "msg_wallet": M("کیف پول", "موجودی", "💰 موجودی شما: <b>{balance}</b> {currency}", "{balance}"),
    "msg_topup_amount": M("کیف پول", "درخواست مبلغ", "مبلغ شارژ را به {currency} بفرستید (حداقل {min}).\nبرای لغو: /cancel", "{min}"),
    "msg_topup_bad": M("کیف پول", "مبلغ نامعتبر", "یک عدد معتبر و حداقل {min} بفرستید.", "{min}"),
    "msg_topup_card": M("کیف پول", "اطلاعات کارت", "مبلغ <b>{amount}</b> {currency} را به کارت زیر واریز کنید:\n\n<code>{card}</code>\n{holder}\n\nسپس <b>عکس رسید</b> را همین‌جا بفرستید.", "{amount} {card} {holder}"),
    "msg_topup_need_photo": M("کیف پول", "رسید عکس نبود", "لطفاً عکس رسید را بفرستید. برای لغو: /cancel"),
    "msg_topup_received": M("کیف پول", "رسید ثبت شد", "✅ رسید ثبت شد. پس از بررسی، موجودی شما شارژ می‌شود."),
    "msg_topup_approved": M("کیف پول", "شارژ تایید شد", "✅ شارژ <b>{amount}</b> {currency} تایید شد.\nموجودی فعلی: <b>{balance}</b> {currency}", "{amount} {balance}"),
    "msg_topup_rejected": M("کیف پول", "شارژ رد شد", "❌ درخواست شارژ شما رد شد. در صورت اشتباه با {support} تماس بگیرید."),
}


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def _vars(kw):
    base = {"brand": settings.brand(), "owner": settings.get("owner_name"),
            "support": settings.get("support_id") or "@support", "currency": CURRENCY}
    base.update(kw)
    return _Safe(base)


def t(key: str, **kw) -> str:
    """متن (پیام یا دکمه) با جایگزینی متغیرها. اگر قالب ویرایش‌شده خراب باشد، پیش‌فرض استفاده می‌شود."""
    v = _vars(kw)
    custom = settings.get("t_" + key)
    for src in (custom, D[key]["text"]):
        if src:
            try:
                return src.format_map(v)
            except Exception:
                continue
    return key


def style(key: str):
    v = settings.get("s_" + key, None)
    if v is None:
        return D[key].get("style")
    return v or None
