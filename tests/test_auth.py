from app.config import settings


def test_login_page_is_reachable_unauthenticated(client):
    response = client.get("/login")

    assert response.status_code == 200


def test_dashboard_route_redirects_to_login_when_unauthenticated(client):
    response = client.get("/dashboard/invoices", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_with_correct_token_sets_session_and_redirects(client):
    response = client.post(
        "/login", data={"token": settings.operator_api_token}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/invoices"
    assert "session" in response.cookies

    follow_up = client.get("/dashboard/invoices")
    assert follow_up.status_code == 200


def test_login_with_wrong_token_rerenders_with_error_and_no_session(client):
    response = client.post(
        "/login", data={"token": "wrong-token"}, follow_redirects=False
    )

    assert response.status_code == 401
    assert "Invalid token" in response.text
    assert "session" not in response.cookies

    follow_up = client.get("/dashboard/invoices", follow_redirects=False)
    assert follow_up.status_code == 303


def test_logout_clears_session(client):
    client.post("/login", data={"token": settings.operator_api_token})
    assert client.get("/dashboard/invoices").status_code == 200

    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/login"

    after_logout = client.get("/dashboard/invoices", follow_redirects=False)
    assert after_logout.status_code == 303
