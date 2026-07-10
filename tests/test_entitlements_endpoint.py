import uuid

from tests.factories import CustomerFactory


def test_get_entitlement_returns_stable_shape_for_existing_customer(client, db_session):
    customer = CustomerFactory()
    db_session.flush()

    response = client.get(f"/entitlements/{customer.id}")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "customer_id": str(customer.id),
        "throttled": False,
        "reason": None,
        "ttl_seconds": 60,
    }


def test_get_entitlement_404s_for_unknown_customer(client):
    response = client.get(f"/entitlements/{uuid.uuid4()}")

    assert response.status_code == 404
