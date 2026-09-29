"""
bookings.py  -  reservations, cancellations and the waitlist-promotion loop.

Flow
----
reserve  -> seat free?  yes: CONFIRMED (flash price if inside flash window)
                        no : WAITLISTED (capped by no-show-based waitlist_limit)
cancel   -> refund with retention penalty -> free seat -> promote_waitlist()
sweep    -> at chart time, un-checked-in tickets => NO_SHOW -> free seat -> promote_waitlist()

NOTE (demo scope): seat allocation reads then writes. For production, wrap the
reserve/cancel sections in a MongoDB transaction or use a per-train lock/queue
to prevent two users grabbing the same seat.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dsa.profit_optimizer import (
    FLASH_WINDOW_HOURS, cancellation_refund, dynamic_multiplier, dynamic_price,
    flash_resale_price, waitlist_limit,
)
from auth import get_current_user
from models import Ticket, TicketStatus, Train, User

router = APIRouter(prefix="/bookings", tags=["bookings"])


# ------------------------------------------------------------ schemas -------
class ReserveIn(BaseModel):
    train_id: PydanticObjectId
    passenger_name: str
    preferred_seat: Optional[int] = None


class CancelOut(BaseModel):
    pnr: str
    refund: float
    penalty: float
    penalty_rate: float
    promoted_pnrs: List[str]


# ------------------------------------------------------------ helpers -------
def hours_until(departure: datetime) -> float:
    if departure.tzinfo is None:                       # Mongo returns naive UTC
        departure = departure.replace(tzinfo=timezone.utc)
    return (departure - datetime.now(timezone.utc)).total_seconds() / 3600


async def _get_train(train_id: PydanticObjectId) -> Train:
    train = await Train.get(train_id)
    if not train:
        raise HTTPException(404, "Train not found")
    return train


async def _confirmed(train_id) -> List[Ticket]:
    return await Ticket.find(Ticket.train_id == train_id,
                             Ticket.status == TicketStatus.CONFIRMED).to_list()


async def _waitlist_count(train_id) -> int:
    return await Ticket.find(Ticket.train_id == train_id,
                             Ticket.status == TicketStatus.WAITLISTED).count()


def _free_seats(train: Train, confirmed: List[Ticket]) -> List[int]:
    taken = {t.seat_number for t in confirmed}
    return [s for s in range(1, train.total_seats + 1) if s not in taken]


async def _refresh_pricing(train: Train) -> float:
    """Recompute the surge multiplier from live occupancy and store it."""
    sold = len(await _confirmed(train.id))
    mult = dynamic_multiplier(train.total_seats, sold, hours_until(train.departure_time))
    await train.update({"$set": {"price_multiplier": mult}})
    return mult


# ------------------------------------------- waitlist promotion loop ---------
async def promote_waitlist(train: Train) -> List[str]:
    """
    Trigger loop: while a seat is free AND someone is waiting, promote the
    oldest waitlisted ticket (FIFO). Called after every cancellation / no-show.
    Returns the PNRs promoted.
    """
    promoted: List[str] = []
    in_flash = hours_until(train.departure_time) <= FLASH_WINDOW_HOURS

    while True:
        free = _free_seats(train, await _confirmed(train.id))
        if not free:
            break
        nxt = (await Ticket.find(Ticket.train_id == train.id,
                                 Ticket.status == TicketStatus.WAITLISTED)
               .sort("+created_at").first_or_none())
        if not nxt:
            break                                    # nobody waiting; seat stays open for flash sale
        nxt.seat_number, nxt.status = free[0], TicketStatus.CONFIRMED
        nxt.is_flash_sale = in_flash
        await nxt.save()
        promoted.append(nxt.pnr)

    await _refresh_pricing(train)
    return promoted


# ------------------------------------------------------------ endpoints -----
@router.get("/availability/{train_id}")
async def availability(train_id: PydanticObjectId,
                       current_user: User = Depends(get_current_user)):
    """Live numbers for the UI: seats, waitlist, price, flash status."""
    train = await _get_train(train_id)
    confirmed = await _confirmed(train.id)
    hrs = hours_until(train.departure_time)
    price = dynamic_price(train.base_fare, train.total_seats, len(confirmed), hrs)
    flash_open = hrs <= FLASH_WINDOW_HOURS and len(confirmed) < train.total_seats
    return {
        "train": {"id": str(train.id), "number": train.number, "name": train.name,
                  "source": train.source, "destination": train.destination,
                  "departure_time": train.departure_time},
        "total_seats": train.total_seats,
        "available_seats": train.total_seats - len(confirmed),
        "taken_seats": sorted(t.seat_number for t in confirmed),
        "waitlist_count": await _waitlist_count(train.id),
        "waitlist_limit": waitlist_limit(train.total_seats, train.historical_no_show_rate),
        "base_fare": train.base_fare,
        "multiplier": train.price_multiplier,
        "price": flash_resale_price(train.base_fare, price, hrs) if flash_open else price,
        "flash_open": flash_open,
        "hours_left": round(hrs, 2),
    }


@router.post("/reserve", status_code=201)
async def reserve(body: ReserveIn,
                  current_user: User = Depends(get_current_user)):
    train = await _get_train(body.train_id)
    hrs = hours_until(train.departure_time)
    if hrs <= 0:
        raise HTTPException(400, "Train has already departed")

    confirmed = await _confirmed(train.id)
    free = _free_seats(train, confirmed)
    price = dynamic_price(train.base_fare, train.total_seats, len(confirmed), hrs)

    if free:                                             # ---- confirmed path
        in_flash = hrs <= FLASH_WINDOW_HOURS
        fare = flash_resale_price(train.base_fare, price, hrs) if in_flash else price
        seat = body.preferred_seat if body.preferred_seat in free else free[0]
        status = TicketStatus.CONFIRMED
    else:                                                # ---- waitlist path
        if await _waitlist_count(train.id) >= waitlist_limit(
                train.total_seats, train.historical_no_show_rate):
            raise HTTPException(409, "Train full and waitlist closed")
        fare, seat, in_flash, status = price, None, False, TicketStatus.WAITLISTED

    ticket = Ticket(pnr=uuid.uuid4().hex[:10].upper(), user_id=current_user.id,
                    train_id=train.id, passenger_name=body.passenger_name,
                    seat_number=seat, status=status, fare_paid=fare, is_flash_sale=in_flash)
    await ticket.insert()

    inc = {"revenue.ticket_revenue": fare}
    if in_flash and status == TicketStatus.CONFIRMED:
        inc["revenue.flash_revenue"] = fare
    await train.update({"$inc": inc})
    await _refresh_pricing(train)
    return ticket


@router.post("/{pnr}/cancel", response_model=CancelOut)
async def cancel(pnr: str, current_user: User = Depends(get_current_user)):
    ticket = await Ticket.find_one(Ticket.pnr == pnr)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.user_id != current_user.id:
        raise HTTPException(404, "Ticket not found")
    if ticket.status not in (TicketStatus.CONFIRMED, TicketStatus.WAITLISTED):
        raise HTTPException(400, f"Cannot cancel a {ticket.status} ticket")

    train = await _get_train(ticket.train_id)
    hrs = hours_until(train.departure_time)
    if hrs <= 0:
        raise HTTPException(400, "Train has already departed")

    if ticket.status == TicketStatus.WAITLISTED:         # never held a seat: full refund
        refund, penalty, rate = ticket.fare_paid, 0.0, 0.0
    else:
        q = cancellation_refund(ticket.fare_paid, hrs, train.total_seats,
                                len(await _confirmed(train.id)),
                                await _waitlist_count(train.id))
        refund, penalty, rate = q.refund, q.penalty, q.penalty_rate

    ticket.status, ticket.seat_number = TicketStatus.CANCELLED, None
    ticket.refund_amount, ticket.cancelled_at = refund, datetime.now(timezone.utc)
    await ticket.save()
    await train.update({"$inc": {"revenue.refunds_paid": refund,
                                 "revenue.penalties_retained": penalty}})

    promoted = await promote_waitlist(train)             # <-- trigger loop
    return CancelOut(pnr=pnr, refund=refund, penalty=penalty,
                     penalty_rate=rate, promoted_pnrs=promoted)


@router.post("/{pnr}/check-in")
async def check_in(pnr: str, current_user: User = Depends(get_current_user)):
    ticket = await Ticket.find_one(Ticket.pnr == pnr)
    if (not ticket or ticket.user_id != current_user.id
            or ticket.status != TicketStatus.CONFIRMED):
        raise HTTPException(404, "Confirmed ticket not found")
    ticket.checked_in = True
    await ticket.save()
    return {"pnr": pnr, "checked_in": True}


@router.post("/no-show-sweep/{train_id}")
async def no_show_sweep(train_id: PydanticObjectId, cutoff_minutes: int = 30,
                        force: bool = False,
                        current_user: User = Depends(get_current_user)):
    """
    Run at chart-preparation time (default 30 min before departure; use
    force=true in the demo). Un-checked-in tickets become NO_SHOW, the fare
    is retained, the seat is released and the waitlist is promoted.
    """
    train = await _get_train(train_id)
    if not force and hours_until(train.departure_time) * 60 > cutoff_minutes:
        raise HTTPException(400, "Too early to mark no-shows")

    no_shows = [t for t in await _confirmed(train.id) if not t.checked_in]
    retained = 0.0
    for t in no_shows:
        t.status, t.no_show, t.seat_number = TicketStatus.NO_SHOW, True, None
        await t.save()
        retained += t.fare_paid
    if no_shows:
        await train.update({"$inc": {"revenue.no_show_retained": retained}})

    promoted = await promote_waitlist(train)             # <-- trigger loop
    return {"no_shows": len(no_shows), "fare_retained": round(retained, 2),
            "promoted_pnrs": promoted}
