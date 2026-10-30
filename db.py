from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import DATABASE_URL
from models import Base

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
