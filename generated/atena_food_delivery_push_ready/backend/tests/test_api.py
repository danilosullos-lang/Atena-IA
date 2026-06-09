from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app, repository

client = TestClient(app)


def setup_function() -> None:
    repository.reset_for_tests()


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_restaurants_and_menu() -> None:
    response = client.get("/restaurants")
    assert response.status_code == 200
    restaurants = response.json()
    assert restaurants[0]["name"] == "Atena Burgers"

    menu = client.get(f"/restaurants/{restaurants[0]['id']}/menu")
    assert menu.status_code == 200
    assert len(menu.json()["items"]) >= 2


def test_quote_cart_total() -> None:
    payload = {"restaurant_id": 1, "items": [{"menu_item_id": 101, "quantity": 2}]}
    response = client.post("/cart/quote", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["subtotal"] == 59.8
    assert body["delivery_fee"] == 4.99
    assert body["total"] == 64.79


def test_create_order_and_payment_flow() -> None:
    payload = {
        "restaurant_id": 1,
        "customer": {
            "name": "Danilo",
            "phone": "11999999999",
            "address": "Rua Atena, 100",
        },
        "items": [
            {"menu_item_id": 101, "quantity": 1},
            {"menu_item_id": 103, "quantity": 2},
        ],
        "payment_method": "pix",
    }
    created = client.post("/orders", json=payload)
    assert created.status_code == 200
    order = created.json()
    assert order["id"] == 1
    assert order["status"] == "created"
    assert order["total"] == 48.89

    paid = client.post(
        "/payments/webhook",
        json={"order_id": 1, "paid": True, "provider_reference": "pix-1"},
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"

    preparing = client.post("/orders/1/status", json={"status": "preparing"})
    assert preparing.status_code == 200
    assert preparing.json()["status"] == "preparing"

    assigned = client.post("/courier/assign/1", json={"courier_name": "Atena Rider"})
    assert assigned.status_code == 200
    assert assigned.json()["courier_name"] == "Atena Rider"


def test_invalid_status_transition_is_rejected() -> None:
    payload = {
        "restaurant_id": 1,
        "customer": {
            "name": "Cliente",
            "phone": "11999999999",
            "address": "Rua Atena, 100",
        },
        "items": [{"menu_item_id": 101, "quantity": 1}],
    }
    assert client.post("/orders", json=payload).status_code == 200
    response = client.post("/orders/1/status", json={"status": "delivered"})
    assert response.status_code == 409
