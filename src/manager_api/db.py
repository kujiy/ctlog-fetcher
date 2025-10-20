from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import MYSQL_URL

ASYNC_MYSQL_URL = MYSQL_URL.replace("mysql+pymysql://", "mysql+aiomysql://")
print(ASYNC_MYSQL_URL)

_async_engine = None
_async_session: Optional[async_sessionmaker[AsyncSession]] = None

def init_engine():
    global _async_engine, _async_session
    if _async_engine is None:
        _async_engine = create_async_engine(
            ASYNC_MYSQL_URL,
            pool_pre_ping=True,
            pool_recycle=180,
            pool_size=10,
            max_overflow=20,
        )
        _async_session = async_sessionmaker(_async_engine, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    if _async_session is None:
        init_engine()
    async with _async_session() as session:
        yield session

async def dispose_engines():
    global _async_engine, _async_session
    # Dispose of async engine
    if _async_engine is not None:
        try:
            await _async_engine.dispose()
        except Exception:
            pass
    _async_engine = None
    _async_session = None

def dispose_engines_sync():
    """Synchronous wrapper for dispose_engines for use in non-async contexts."""
    global _async_engine, _async_session
    # Dispose of async engine
    if _async_engine is not None:
        try:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, create a task
                    asyncio.create_task(_async_engine.dispose())
                else:
                    # If loop is not running, run until complete
                    loop.run_until_complete(_async_engine.dispose())
            except RuntimeError:
                # No event loop, create new one
                asyncio.run(_async_engine.dispose())
        except Exception:
            pass
    _async_engine = None
    _async_session = None
