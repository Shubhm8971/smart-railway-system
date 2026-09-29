"""
models.py  -  MongoDB documents (Beanie ODM on top of Pydantic v2)

Collections: users, trains, tickets
A "Train" document represents one scheduled RUN (train + departure datetime),
so pricing and revenue are tracked per run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TicketStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


# ---------------------------------------------------------------- Users -----
class User(Document):
    name: str
    email: Indexed(str, unique=True)
    phone: Optional[str] = None
    password_hash: str = ""                     # store a bcrypt hash, never plain text
    loyalty_no_show_count: int = 0              # repeat no-shows can lose priority later
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "users"


# ---------------------------------------------------------------- Trains ----
class RevenueTracker(BaseModel):
    """Running P&L for this train run. Updated atomically with $inc."""
    ticket_revenue: float = 0.0        # gross fares collected
    refunds_paid: float = 0.0          # money returned on cancellations
    penalties_retained: float = 0.0    # cancellation penalties kept
    no_show_retained: float = 0.0      # fares kept from passengers who never boarded
    flash_revenue: float = 0.0         # revenue from flash-resold seats

    @property
    def net_revenue(self) -> float:
        return self.ticket_revenue - self.refunds_paid


class Train(Document):
    number: Indexed(str)
    name: str
    route: List[str]                               # ordered station names
    source: str
    destination: str
    departure_time: datetime
    distance_km: float
    total_seats: int = 72
    base_fare: float
    price_multiplier: float = 1.0                  # recomputed on every booking event
    historical_no_show_rate: float = 0.08          # feeds waitlist_limit()
    revenue: RevenueTracker = Field(default_factory=RevenueTracker)

    class Settings:
        name = "trains"


# --------------------------------------------------------------- Tickets ----
class Ticket(Document):
    pnr: Indexed(str, unique=True)
    user_id: PydanticObjectId
    train_id: PydanticObjectId
    passenger_name: str
    seat_number: Optional[int] = None              # None while WAITLISTED
    status: TicketStatus = TicketStatus.CONFIRMED
    fare_paid: float
    is_flash_sale: bool = False                    # bought / promoted inside flash window
    checked_in: bool = False                       # false at departure => no-show
    no_show: bool = False
    refund_amount: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)   # FIFO order for waitlist
    cancelled_at: Optional[datetime] = None

    class Settings:
        name = "tickets"
        indexes = [[("train_id", 1), ("status", 1), ("created_at", 1)]]
