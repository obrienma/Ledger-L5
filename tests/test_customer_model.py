import uuid

from tests.factories import CustomerFactory


def test_customer_id_is_a_database_assigned_uuid(db_session):
    customer = CustomerFactory()
    db_session.flush()

    assert isinstance(customer.id, uuid.UUID)
    assert customer.created_at is not None


def test_customer_ids_are_unique_across_rows(db_session):
    first = CustomerFactory()
    second = CustomerFactory()
    db_session.flush()

    assert first.id != second.id
