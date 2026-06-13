from __future__ import annotations

from backend.app.schemas import Order, Restaurant
from backend.app.seed import seed_restaurants


class DeliveryRepository:
    def __init__(self) -> None:
        self.restaurants: list[Restaurant] = seed_restaurants()
        self.orders: dict[int, Order] = {}
        self._next_order_id = 1

    def list_restaurants(self) -> list[Restaurant]:
        return self.restaurants

    def get_restaurant(self, restaurant_id: int) -> Restaurant | None:
        return next((r for r in self.restaurants if r.id == restaurant_id), None)

    def save_order(self, order: Order) -> Order:
        if order.id == 0:
            order = order.model_copy(update={"id": self._next_order_id})
            self._next_order_id += 1
        self.orders[order.id] = order
        return order

    def get_order(self, order_id: int) -> Order | None:
        return self.orders.get(order_id)

    def reset_for_tests(self) -> None:
        self.orders.clear()
        self._next_order_id = 1
