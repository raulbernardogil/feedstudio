import os
from pathlib import Path

import pytest

os.environ.setdefault("FEEDSTUDIO_ENVIRONMENT", "test")


@pytest.fixture()
def app_client(tmp_path: Path, monkeypatch):
    """Fresh database + storage per test, jobs executed synchronously."""
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    # Set FEEDSTUDIO_TEST_DATABASE_URL=postgresql+psycopg://... to run the API
    # tests against PostgreSQL (the schema is dropped and recreated per test).
    db_url = os.environ.get("FEEDSTUDIO_TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    if db_url.startswith("postgresql"):
        from sqlalchemy import create_engine, text

        reset = create_engine(db_url)
        with reset.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        reset.dispose()
    monkeypatch.setenv("FEEDSTUDIO_DATABASE_URL", db_url)
    monkeypatch.setenv("FEEDSTUDIO_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("FEEDSTUDIO_PUBLIC_BASE_URL", "http://testserver")

    from feedstudio import config, db, jobs, storage

    config.get_settings.cache_clear()
    db.configure(db_url)
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.attributes["database_url"] = db_url
    command.upgrade(cfg, "head")
    storage.set_storage(storage.LocalStorage(tmp_path / "storage"))
    jobs.set_runner(jobs.SyncJobRunner())

    from feedstudio.main import create_app

    with TestClient(create_app()) as client:
        yield client
    db.get_engine().dispose()
    config.get_settings.cache_clear()
