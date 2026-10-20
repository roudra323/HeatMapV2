from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

import heatmap_core.db.models  # noqa: F401
from heatmap_core.db.base import Base
from tests.conftest import alembic_config


def test_all_tables_created(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_downgrade_and_upgrade_round_trip(database_url: str, engine: Engine) -> None:
    cfg = alembic_config(database_url)
    command.downgrade(cfg, "base")
    assert "transfers" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "transfers" in inspect(engine).get_table_names()
