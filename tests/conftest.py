from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.db import engine
from tests.factories import CustomerFactory


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    CustomerFactory._meta.sqlalchemy_session = session
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
