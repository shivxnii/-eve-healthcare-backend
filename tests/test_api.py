from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Booking, BookingStatus, Payment


def signup(client, name, email, password="password123"):
    return client.post("/auth/signup", json={"name": name, "email": email, "password": password})


def login(client, email, password="password123"):
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def create_booking(client, token, offering_id):
    return client.post(
        "/bookings",
        headers=headers(token),
        json={"centre_test_id": offering_id, "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )


def test_signup_login_and_duplicate_signup(client, offering):
    assert signup(client, "Alice", "alice@example.com").status_code == 201
    assert signup(client, "Alice", "alice@example.com").status_code == 400
    assert login(client, "alice@example.com")


def test_invalid_login(client, offering):
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": "wrongpass"}).status_code == 401


def test_centres_and_details(client, offering):
    assert client.get("/centres").status_code == 200
    response = client.get("/centres/1")
    assert response.status_code == 200
    assert response.json()["tests"][0]["price"] == "500.00"


def test_booking_requires_auth_and_invalid_offering(client, offering):
    assert client.post("/bookings", json={"centre_test_id": offering, "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}).status_code == 401
    token = login(client, "alice@example.com")
    response = client.post("/bookings", headers=headers(token), json={"centre_test_id": 9999, "appointment_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    assert response.status_code == 404


def test_create_booking_and_unauthorized_access(client, offering):
    signup(client, "Bob", "bob@example.com")
    bob_token = login(client, "bob@example.com")
    booking = create_booking(client, bob_token, offering)
    assert booking.status_code == 201
    booking_id = booking.json()["id"]
    alice_token = login(client, "alice@example.com")
    assert client.get(f"/bookings/{booking_id}", headers=headers(alice_token)).status_code == 403


def test_successful_payment_and_idempotency(client, offering):
    token = login(client, "bob@example.com")
    booking = create_booking(client, token, offering).json()
    response = client.post("/payments/", headers={**headers(token), "Idempotency-Key": "key-1"}, json={"booking_id": booking["id"], "simulate": "SUCCESS"})
    assert response.status_code == 201
    payment_id = response.json()["id"]
    response2 = client.post("/payments/", headers={**headers(token), "Idempotency-Key": "key-1"}, json={"booking_id": booking["id"], "simulate": "SUCCESS"})
    assert response2.status_code == 201
    assert response2.json()["id"] == payment_id
    assert client.get(f"/bookings/{booking['id']}", headers=headers(token)).json()["status"] == "CONFIRMED"


def test_failed_payment(client, offering):
    token = login(client, "bob@example.com")
    booking = create_booking(client, token, offering).json()
    response = client.post("/payments/", headers=headers(token), json={"booking_id": booking["id"], "simulate": "FAILED"})
    assert response.status_code == 201
    assert client.get(f"/bookings/{booking['id']}", headers=headers(token)).json()["status"] == "FAILED"


def test_webhook_is_idempotent(client, offering):
    token = login(client, "bob@example.com")
    booking = create_booking(client, token, offering).json()
    payload = {"event_id": "evt-test-1", "transaction_id": "txn-webhook-1", "booking_id": booking["id"], "status": "SUCCESS"}
    first = client.post("/payments/webhook/", json=payload)
    second = client.post("/payments/webhook/", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    db = SessionLocal()
    assert db.query(Payment).filter(Payment.transaction_id == "txn-webhook-1").count() == 1
    assert db.get(Booking, booking["id"]).status == BookingStatus.CONFIRMED
    db.close()


def test_cancel_booking(client, offering):
    token = login(client, "bob@example.com")
    booking = create_booking(client, token, offering).json()
    response = client.post(f"/bookings/{booking['id']}/cancel", headers=headers(token))
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=headers(token)).status_code == 400


def test_admin_management_endpoints(client, offering):
    response = client.post("/auth/login", json={"email": "admin@evehealthcare.com", "password": "Admin12345!"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    centre = client.post("/centres", headers=headers(token), json={"name": "New Diagnostics", "location": "Delhi"})
    assert centre.status_code == 201
    centre_id = centre.json()["id"]
    new_test = client.post("/centres/catalog/tests", headers=headers(token), json={"name": "Vitamin D", "description": "Vitamin D level"})
    assert new_test.status_code == 201
    test_id = new_test.json()["id"]
    offering_response = client.post(f"/centres/{centre_id}/tests", headers=headers(token), json={"test_id": test_id, "price": "750.00"})
    assert offering_response.status_code == 201


def test_non_admin_cannot_manage_centres(client, offering):
    token = login(client, "bob@example.com")
    assert client.post("/centres", headers=headers(token), json={"name": "Nope", "location": "Jaipur"}).status_code == 403


def test_catalog_retrieval_and_admin_updates(client, offering):
    admin = client.post("/auth/login", json={"email": "admin@evehealthcare.com", "password": "Admin12345!"}).json()["access_token"]
    assert client.get("/centres/catalog/tests").status_code == 200
    test_id = client.get("/centres/catalog/tests").json()[0]["id"]
    assert client.get(f"/centres/catalog/tests/{test_id}").status_code == 200
    updated = client.patch(f"/centres/catalog/tests/{test_id}", headers=headers(admin), json={"name": "CBC Updated"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "CBC Updated"
    centre = client.patch("/centres/1", headers=headers(admin), json={"location": "Jaipur City"})
    assert centre.status_code == 200
    assert centre.json()["location"] == "Jaipur City"


def test_rate_limiter():
    from app.core.rate_limit import RateLimiter
    limiter = RateLimiter("2/second")
    assert limiter.allowed("test-client") is True
    assert limiter.allowed("test-client") is True
    assert limiter.allowed("test-client") is False
