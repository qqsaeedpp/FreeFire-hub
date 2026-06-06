"""Project-wide constants and enums."""
from __future__ import annotations

import enum

PAGE_SIZE = 5  # default pagination size for lists


class OrderStatus(str, enum.Enum):
    PENDING = "pending"          # awaiting receipt / admin review
    AWAITING_PAYMENT = "awaiting_payment"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderType(str, enum.Enum):
    DIAMOND_UID = "diamond_uid"
    DIAMOND_ACCOUNT = "diamond_account"
    ACCOUNT_PURCHASE = "account_purchase"


class AccountStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"  # user-listed, awaiting an admin decision
    AVAILABLE = "available"            # admin-added listing, live in the shop
    LISTED_FOR_SALE = "listed_for_sale"  # user listing the admin published to the shop
    RESERVED = "reserved"
    SOLD = "sold"
    SOLD_TO_ADMIN = "sold_to_admin"    # admin bought it directly from the seller
    HIDDEN = "hidden"                  # kept in DB but hidden from the public shop


# Statuses that are shown to buyers in the public shop (and can be reserved).
SHOP_VISIBLE_STATUSES = (AccountStatus.AVAILABLE, AccountStatus.LISTED_FOR_SALE)


class PaymentMethod(str, enum.Enum):
    ONLINE = "online"
    CARD_TO_CARD = "card_to_card"
    WALLET = "wallet"


class CardPurpose(str, enum.Enum):
    """Which sales channel a stored card belongs to."""

    DIAMOND = "diamond"
    ACCOUNT = "account"


class SaleRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    PURCHASE = "purchase"
    REFERRAL_REWARD = "referral_reward"
    REFUND = "refund"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class LoginMethod(str, enum.Enum):
    GUEST = "guest"
    FACEBOOK = "facebook"
    GOOGLE = "google"
    VK = "vk"
    TWITTER = "twitter"
    APPLE = "apple"


# Human-readable Persian labels for statuses (used in messages).
ORDER_STATUS_FA: dict[str, str] = {
    OrderStatus.PENDING: "در انتظار بررسی",
    OrderStatus.AWAITING_PAYMENT: "در انتظار پرداخت",
    OrderStatus.UNDER_REVIEW: "در حال بررسی",
    OrderStatus.APPROVED: "تایید شده",
    OrderStatus.REJECTED: "رد شده",
    OrderStatus.COMPLETED: "تکمیل شده",
    OrderStatus.CANCELLED: "لغو شده",
}

TICKET_STATUS_FA: dict[str, str] = {
    TicketStatus.OPEN: "باز",
    TicketStatus.ANSWERED: "پاسخ داده شده",
    TicketStatus.CLOSED: "بسته شده",
}

PAYMENT_METHOD_FA: dict[str, str] = {
    PaymentMethod.ONLINE: "💳 پرداخت آنلاین",
    PaymentMethod.CARD_TO_CARD: "🏦 کارت به کارت",
    PaymentMethod.WALLET: "👛 کیف پول",
}

ACCOUNT_STATUS_FA: dict[str, str] = {
    AccountStatus.PENDING_REVIEW: "در انتظار بررسی",
    AccountStatus.AVAILABLE: "موجود در فروشگاه",
    AccountStatus.LISTED_FOR_SALE: "منتشرشده در فروشگاه",
    AccountStatus.RESERVED: "رزرو شده",
    AccountStatus.SOLD: "فروخته شده",
    AccountStatus.SOLD_TO_ADMIN: "خریداری‌شده توسط ادمین",
    AccountStatus.HIDDEN: "مخفی",
}

CARD_PURPOSE_FA: dict[str, str] = {
    CardPurpose.DIAMOND: "💎 کارت فروش جم",
    CardPurpose.ACCOUNT: "🛒 کارت فروش اکانت",
}
