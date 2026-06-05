"""Order service — payment receipts, admin approval/rejection, completion."""
from __future__ import annotations

from app.core.constants import OrderStatus, PaymentStatus
from app.models.order import Order
from app.models.payment import Payment
from app.repositories.orders import OrderRepository
from app.repositories.payments import PaymentRepository


class OrderService:
    def __init__(self, orders: OrderRepository, payments: PaymentRepository) -> None:
        self.orders = orders
        self.payments = payments

    async def attach_receipt(self, order: Order, receipt_file_id: str) -> Payment:
        payment = await self.payments.get_by_order_id(order.id)
        if payment is None:
            payment = Payment(order_id=order.id, amount=order.amount)
            await self.payments.add(payment)
        payment.receipt_file_id = receipt_file_id
        payment.status = PaymentStatus.PENDING
        order.status = OrderStatus.UNDER_REVIEW
        return payment

    async def mark_wallet_paid(self, order: Order) -> None:
        order.paid_from_wallet = True
        order.status = OrderStatus.UNDER_REVIEW

    async def approve(self, order: Order, note: str | None = None) -> None:
        order.status = OrderStatus.APPROVED
        order.admin_note = note
        payment = await self.payments.get_by_order_id(order.id)
        if payment:
            payment.status = PaymentStatus.CONFIRMED

    async def reject(self, order: Order, note: str | None = None) -> None:
        order.status = OrderStatus.REJECTED
        order.admin_note = note
        payment = await self.payments.get_by_order_id(order.id)
        if payment:
            payment.status = PaymentStatus.REJECTED

    async def complete(self, order: Order) -> None:
        order.status = OrderStatus.COMPLETED

    async def cancel(self, order: Order) -> None:
        order.status = OrderStatus.CANCELLED

    async def get(self, order_id: int) -> Order | None:
        return await self.orders.get(order_id)
