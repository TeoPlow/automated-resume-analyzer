from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех SQLAlchemy-моделей."""

    pass


class Database:
    """Менеджер подключения к PostgreSQL."""

    def __init__(self, url: str, echo: bool = False) -> None:
        self._engine = create_async_engine(url, echo=echo, pool_size=10)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def create_tables(self) -> None:
        """Создать все таблицы из зарегистрированных моделей."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        """Получить новую сессию БД."""
        return self._session_factory()

    async def dispose(self) -> None:
        """Закрыть пул соединений."""
        await self._engine.dispose()
