from __future__ import annotations

from backend.app.schemas import MenuItem, Restaurant


def seed_restaurants() -> list[Restaurant]:
    return [
        Restaurant(
            id=1,
            name="Atena Burgers",
            cuisine="burger",
            delivery_fee=4.99,
            eta_minutes=28,
            menu=[
                MenuItem(id=101, name="Atena Smash", price=29.90),
                MenuItem(id=102, name="Batata Suprema", price=15.50),
                MenuItem(id=103, name="Refrigerante", price=7.00),
            ],
        ),
        Restaurant(
            id=2,
            name="Colares Pizza",
            cuisine="pizza",
            delivery_fee=6.50,
            eta_minutes=38,
            menu=[
                MenuItem(id=201, name="Pizza Margherita", price=49.90),
                MenuItem(id=202, name="Pizza Calabresa", price=52.90),
            ],
        ),
    ]
