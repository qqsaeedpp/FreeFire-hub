"""Ticket service — create tickets, append messages, admin replies, close."""
from __future__ import annotations

from app.core.constants import TicketStatus
from app.models.ticket import Ticket, TicketMessage
from app.repositories.tickets import TicketRepository


class TicketService:
    def __init__(self, tickets: TicketRepository) -> None:
        self.tickets = tickets

    async def create(
        self,
        user_id: int,
        subject: str,
        *,
        text: str | None = None,
        file_id: str | None = None,
        file_type: str | None = None,
    ) -> Ticket:
        ticket = Ticket(user_id=user_id, subject=subject, status=TicketStatus.OPEN)
        await self.tickets.add(ticket)
        await self.tickets.add_message(
            TicketMessage(
                ticket_id=ticket.id,
                is_from_admin=False,
                text=text,
                file_id=file_id,
                file_type=file_type,
            )
        )
        return ticket

    async def add_user_message(
        self, ticket: Ticket, *, text=None, file_id=None, file_type=None
    ) -> TicketMessage:
        ticket.status = TicketStatus.OPEN
        return await self.tickets.add_message(
            TicketMessage(
                ticket_id=ticket.id,
                is_from_admin=False,
                text=text,
                file_id=file_id,
                file_type=file_type,
            )
        )

    async def add_admin_reply(
        self, ticket: Ticket, *, text=None, file_id=None, file_type=None
    ) -> TicketMessage:
        ticket.status = TicketStatus.ANSWERED
        return await self.tickets.add_message(
            TicketMessage(
                ticket_id=ticket.id,
                is_from_admin=True,
                text=text,
                file_id=file_id,
                file_type=file_type,
            )
        )

    async def close(self, ticket: Ticket) -> None:
        ticket.status = TicketStatus.CLOSED

    async def get_with_messages(self, ticket_id: int) -> Ticket | None:
        return await self.tickets.get_with_messages(ticket_id)
