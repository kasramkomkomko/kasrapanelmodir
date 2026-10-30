from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Panel(Base):
    __tablename__ = "panels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(300))
    ptype: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(200), default="")
    password_enc: Mapped[str] = mapped_column(Text)
    extra: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(200), default="")
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    panel_id: Mapped[int] = mapped_column(ForeignKey("panels.id"))
    days: Mapped[int] = mapped_column(default=30)
    gb: Mapped[int] = mapped_column(default=0)  # 0 = نامحدود
    price: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    panel: Mapped[Panel] = relationship(lazy="selectin")


class Order(Base):
    """درخواست شارژ کیف پول (کارت‌به‌کارت)"""
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/paid/rejected
    receipt_file_id: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship(lazy="selectin")


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    panel_id: Mapped[int] = mapped_column(ForeignKey("panels.id"))
    username: Mapped[str] = mapped_column(String(100))
    ref: Mapped[str] = mapped_column(Text, default="{}")
    sub_url: Mapped[str] = mapped_column(Text, default="")
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped[User] = relationship(lazy="selectin")
    plan: Mapped[Plan] = relationship(lazy="selectin")
    panel: Mapped[Panel] = relationship(lazy="selectin")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
