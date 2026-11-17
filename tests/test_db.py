"""Database setup tests. All run against throwaway SQLite, never DATABASE_URL."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import normalize_database_url
from app.models import Base

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["database_url"] = db_url
    return cfg


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:***@h:5432/db"),
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:***@h/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:***@h/db?ssl=require"),
        ("sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:///:memory:"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert str(normalize_database_url(raw)) == expected


def test_single_migration_head():
    """Two migrations both claiming to be latest would break deploys."""
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    assert len(script.get_heads()) == 1


# Sync test on purpose: env.py calls asyncio.run(), which can't nest in a running loop.
def test_migrations_create_expected_schema_and_downgrade(tmp_path):
    db_file = tmp_path / "migrations.db"
    cfg = alembic_config(f"sqlite+aiosqlite:///{db_file}")

    command.upgrade(cfg, "head")

    inspector = sa.inspect(sa.create_engine(f"sqlite:///{db_file}"))
    assert {"users", "auth_identities"} <= set(inspector.get_table_names())

    assert {c["name"] for c in inspector.get_columns("users")} == {
        "id", "email", "display_name", "created_at", "updated_at",
    }
    assert {c["name"] for c in inspector.get_columns("auth_identities")} == {
        "id", "user_id", "provider", "provider_subject", "email",
        "created_at", "last_used_at",
    }

    uniques = inspector.get_unique_constraints("auth_identities")
    assert {"provider", "provider_subject"} in [set(u["column_names"]) for u in uniques]

    (fk,) = inspector.get_foreign_keys("auth_identities")
    assert fk["referred_table"] == "users"
    assert fk["options"].get("ondelete") == "CASCADE"

    command.downgrade(cfg, "base")
    assert not {"users", "auth_identities"} & set(
        sa.inspect(sa.create_engine(f"sqlite:///{db_file}")).get_table_names()
    )


def test_migrations_match_models(tmp_path):
    """Catches editing models.py without writing a migration."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    db_file = tmp_path / "drift.db"
    command.upgrade(alembic_config(f"sqlite+aiosqlite:///{db_file}"), "head")

    with sa.create_engine(f"sqlite:///{db_file}").connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


async def test_deleting_user_cascades_to_identities():
    from app.models import AuthIdentity, User
    from sqlalchemy import event, func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs otherwise
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        user = User(email="a@example.com")
        s.add(user)
        s.add(AuthIdentity(user=user, provider="apple", provider_subject="sub-1"))
        await s.commit()
        user_id = user.id  # read now: the rollback below expires `user`

        # Duplicate (provider, provider_subject) must be rejected.
        s.add(AuthIdentity(user=user, provider="apple", provider_subject="sub-1"))
        with pytest.raises(sa.exc.IntegrityError):
            await s.commit()
        await s.rollback()

        await s.execute(sa.delete(User).where(User.id == user_id))
        await s.commit()
        assert await s.scalar(select(func.count()).select_from(AuthIdentity)) == 0

    await engine.dispose()
