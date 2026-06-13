from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.app.repository import DeliveryRepository
from backend.app.schemas import (
    Order,
    OrderCreate,
    OrderStatus,
    PaymentWebhook,
    QuoteRequest,
    QuoteResponse,
    Restaurant,
    StatusUpdate,
)
from backend.app.services import DeliveryService

repository = DeliveryRepository()
service = DeliveryService(repository)

app = FastAPI(title="ATENA Food Delivery API", version="1.0.0")


class CourierAssignment(BaseModel):
    courier_name: str = Field(min_length=2)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "atena-food-delivery"}


@app.get("/restaurants", response_model=list[Restaurant])
def list_restaurants() -> list[Restaurant]:
    return service.repository.list_restaurants()


@app.get("/restaurants/{restaurant_id}/menu")
def restaurant_menu(restaurant_id: int) -> dict:
    restaurant = service.repository.get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="restaurant not found")
    return {"restaurant_id": restaurant.id, "items": restaurant.menu}


@app.post("/cart/quote", response_model=QuoteResponse)
def quote_cart(payload: QuoteRequest) -> QuoteResponse:
    return service.quote(payload)


@app.post("/orders", response_model=Order)
def create_order(payload: dict) -> Order:
    return service.create_order(OrderCreate.model_validate(payload))


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: int) -> Order:
    return service.get_order_or_404(order_id)


@app.post("/orders/{order_id}/status", response_model=Order)
def update_status(order_id: int, payload: StatusUpdate) -> Order:
    return service.update_status(order_id, payload.status)


@app.post("/courier/assign/{order_id}", response_model=Order)
def assign_courier(order_id: int, payload: CourierAssignment) -> Order:
    return service.assign_courier(order_id, payload.courier_name)


@app.post("/payments/webhook", response_model=Order)
def payment_webhook(payload: PaymentWebhook) -> Order:
    if not payload.paid:
        return service.get_order_or_404(payload.order_id)
    return service.update_status(payload.order_id, status=OrderStatus.paid)
