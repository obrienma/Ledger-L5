from sqlalchemy import text


def test_harness_connects_to_test_database(db_session):
    assert db_session.execute(text("select 1")).scalar() == 1
