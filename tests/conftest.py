from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.main import app
from tests.factories import CustomerFactory


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    # create_savepoint: route-level session.commit()/rollback() (e.g. the
    # Stripe webhook's rollback-on-duplicate-event path) operate on a nested
    # SAVEPOINT instead of the outer transaction, so one request's rollback
    # can't undo another request's already-"committed" work within the same
    # test, and the whole test is still discarded by transaction.rollback()
    # below regardless.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    CustomerFactory._meta.sqlalchemy_session = session
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
