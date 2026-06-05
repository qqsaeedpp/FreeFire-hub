"""Ticket repository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.constants import TicketStatus
from app.models.ticket import Ticket, TicketMessage
from app.repositories.base import BaseRepository


class TicketRepository(BaseRepository[Ticket]):
    model = Ticket

    async def get_with_messages(self, ticket_id: int) -> Ticket | None:
        result = await self.session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.messages))
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int) -> list[Ticket]:
        result = await self.session.execute(
            select(Ticket)
            .where(Ticket.user_id == user_id)
            .order_by(Ticket.id.desc())
        )
        return list(result.scalars().all())

    async def list_open(self, *, offset: int = 0, limit: int = 10) -> list[Ticket]:
        result = await self.session.execute(
            select(Ticket)
            .where(Ticket.status != TicketStatus.CLOSED)
            .order_by(Ticket.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def add_message(self, message: TicketMessage) -> TicketMessage:
        self.session.add(message)
        await self.session.flush()
        return message
