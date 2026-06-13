from __future__ import annotations

from fastapi import HTTPException

from backend.app.repository import DeliveryRepository
from backend.app.schemas import (
    Order,
    OrderCreate,
    OrderStatus,
    QuoteRequest,
    QuoteResponse,
)

VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.created: {OrderStatus.paid, OrderStatus.cancelled},
    OrderStatus.paid: {OrderStatus.preparing, OrderStatus.cancelled},
    OrderStatus.preparing: {OrderStatus.out_for_delivery, OrderStatus.cancelled},
    OrderStatus.out_for_delivery: {OrderStatus.delivered},
    OrderStatus.delivered: set(),
    OrderStatus.cancelled: set(),
}


class DeliveryService:
    def __init__(self, repository: DeliveryRepository) -> None:
        self.repository = repository

    def quote(self, payload: QuoteRequest) -> QuoteResponse:
        restaurant = self.repository.get_restaurant(payload.restaurant_id)
        if restaurant is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        menu_by_id = {item.id: item for item in restaurant.menu if item.available}
        subtotal = 0.0
        items_count = 0
        for item in payload.items:
            menu_item = menu_by_id.get(item.menu_item_id)
            if menu_item is None:
                raise HTTPException(
                    status_code=400, detail=f"invalid menu item: {item.menu_item_id}"
                )
            subtotal += menu_item.price * item.quantity
            items_count += item.quantity
        total = round(subtotal + restaurant.delivery_fee, 2)
        return QuoteResponse(
            restaurant_id=restaurant.id,
            subtotal=round(subtotal, 2),
            delivery_fee=restaurant.delivery_fee,
            total=total,
            items_count=items_count,
        )

    def create_order(self, payload: OrderCreate) -> Order:
        quote = self.quote(
            QuoteRequest(restaurant_id=payload.restaurant_id, items=payload.items)
        )
        order = Order(
            id=0,
            restaurant_id=payload.restaurant_id,
            customer=payload.customer,
            items=payload.items,
            subtotal=quote.subtotal,
            delivery_fee=quote.delivery_fee,
            total=quote.total,
        )
        return self.repository.save_order(order)

    def get_order_or_404(self, order_id: int) -> Order:
        order = self.repository.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        return order

    def update_status(self, order_id: int, status: OrderStatus) -> Order:
        order = self.get_order_or_404(order_id)
        if status not in VALID_TRANSITIONS[order.status]:
            raise HTTPException(
                status_code=409,
                detail=f"invalid transition: {order.status} -> {status}",
            )
        updated = order.model_copy(update={"status": status})
        return self.repository.save_order(updated)

    def assign_courier(self, order_id: int, courier_name: str) -> Order:
        order = self.get_order_or_404(order_id)
        updated = order.model_copy(update={"courier_name": courier_name})
        return self.repository.save_order(updated)
