from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field, PositiveInt


class OrderStatus(StrEnum):
    created = "created"
    paid = "paid"
    preparing = "preparing"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"


class MenuItem(BaseModel):
    id: int
    name: str
    price: float = Field(gt=0)
    available: bool = True


class Restaurant(BaseModel):
    id: int
    name: str
    cuisine: str
    delivery_fee: float = Field(ge=0)
    eta_minutes: int = Field(gt=0)
    menu: list[MenuItem]


class CartItem(BaseModel):
    menu_item_id: int
    quantity: PositiveInt


class QuoteRequest(BaseModel):
    restaurant_id: int
    items: list[CartItem] = Field(min_length=1)


class QuoteResponse(BaseModel):
    restaurant_id: int
    subtotal: float
    delivery_fee: float
    total: float
    items_count: int


class Customer(BaseModel):
    name: str = Field(min_length=2)
    phone: str = Field(min_length=8)
    address: str = Field(min_length=5)


class OrderCreate(BaseModel):
    restaurant_id: int
    customer: Customer
    items: list[CartItem] = Field(min_length=1)
    payment_method: str = "pix"


class Order(BaseModel):
    id: int
    restaurant_id: int
    customer: Customer
    items: list[CartItem]
    subtotal: float
    delivery_fee: float
    total: float
    status: OrderStatus = OrderStatus.created
    courier_name: str | None = None


class StatusUpdate(BaseModel):
    status: OrderStatus


class PaymentWebhook(BaseModel):
    order_id: int
    paid: bool
    provider_reference: str
