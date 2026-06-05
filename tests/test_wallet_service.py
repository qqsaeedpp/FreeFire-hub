import pytest

from app.core.constants import TransactionType
from app.models.user import User
from app.repositories.wallets import WalletRepository
from app.services.wallet_service import InsufficientBalanceError, WalletService


async def _make_user(session) -> User:
    user = User(telegram_id=555, referral_code="ABC12345")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_credit_and_debit(session):
    user = await _make_user(session)
    service = WalletService(WalletRepository(session))

    await service.credit(user.id, 50_000, TransactionType.DEPOSIT, "test top-up")
    wallet = await service.get_or_create(user.id)
    assert wallet.balance == 50_000

    await service.debit(user.id, 20_000, TransactionType.PURCHASE, "test buy")
    wallet = await service.get_or_create(user.id)
    assert wallet.balance == 30_000

    history = await service.history(user.id)
    assert len(history) == 2
    assert history[0].balance_after == 30_000


@pytest.mark.asyncio
async def test_insufficient_balance(session):
    user = await _make_user(session)
    service = WalletService(WalletRepository(session))
    with pytest.raises(InsufficientBalanceError):
        await service.debit(user.id, 10_000)
