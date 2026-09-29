"""
profit_optimizer.py
-------------------
The "Profit / No-Show Engine" of Smart Railway.

Four pure, side-effect-free functions (easy to unit test and to explain):

1. dynamic_multiplier()      -> surge price from seat scarcity + departure urgency
2. cancellation_refund()     -> refund with a retention penalty that protects revenue
3. flash_resale_price()      -> discounted price to refill a freed last-minute seat
4. waitlist_limit()          -> how many extra passengers we can safely queue,
                                based on the train's historical no-show rate

Design rule: the railway must never be worse off from a cancellation
than the *expected* outcome of resale. Penalties scale with the chance
the seat CANNOT be resold.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# ---- Tunable policy constants (regulated fares => surge is capped) ----------
MIN_MULTIPLIER = 1.00
MAX_MULTIPLIER = 1.50           # never charge more than 1.5x base fare
MAX_SCARCITY_SURGE = 0.40       # portion of surge driven by occupancy
MAX_URGENCY_SURGE = 0.10        # portion of surge driven by proximity to departure
URGENCY_WINDOW_HOURS = 72

# Time-tiered base penalty (mirrors the shape of real railway rules)
PENALTY_TIERS = [               # (hours_left_threshold, penalty_rate)
    (48, 0.10),
    (12, 0.25),
    (4, 0.50),
    (0, 1.00),                  # under 4h: no refund
]
MAX_DYNAMIC_PENALTY = 0.60      # ceiling for the resale-risk penalty

FLASH_WINDOW_HOURS = 6          # flash resale opens this close to departure
FLASH_FLOOR_RATIO = 0.60        # never sell below 60% of base fare


# ---- 1. Surge pricing --------------------------------------------------------
def dynamic_multiplier(total_seats: int, sold_seats: int, hours_left: float) -> float:
    """
    Price multiplier in [1.0, 1.5].

    Scarcity: flat below 50% occupancy, then a convex (quadratic) ramp so the
    price rises slowly at first and steeply as the last seats disappear.
    Urgency: small linear bump inside the final 72 hours, only when the train
    is already >=50% full (we never surge an empty train).
    """
    if total_seats <= 0:
        raise ValueError("total_seats must be positive")
    occupancy = min(max(sold_seats / total_seats, 0.0), 1.0)

    scarcity = 0.0
    if occupancy > 0.5:
        scarcity = MAX_SCARCITY_SURGE * ((occupancy - 0.5) / 0.5) ** 2

    urgency = 0.0
    if occupancy >= 0.5 and 0 < hours_left < URGENCY_WINDOW_HOURS:
        urgency = MAX_URGENCY_SURGE * (1 - hours_left / URGENCY_WINDOW_HOURS)

    return round(min(MIN_MULTIPLIER + scarcity + urgency, MAX_MULTIPLIER), 2)


def dynamic_price(base_fare: float, total_seats: int, sold_seats: int,
                  hours_left: float) -> float:
    return round(base_fare * dynamic_multiplier(total_seats, sold_seats, hours_left), 2)


# ---- 2. Cancellation retention penalty --------------------------------------
def _tier_penalty(hours_left: float) -> float:
    for threshold, rate in PENALTY_TIERS:
        if hours_left >= threshold:
            return rate
    return 1.0


def resale_probability(total_seats: int, sold_seats: int,
                       waitlist_len: int, hours_left: float) -> float:
    """
    Heuristic P(freed seat gets resold). Rises with occupancy and waitlist
    depth, falls as departure nears (less time to find a buyer).
    A ML model can replace this function without touching anything else.
    """
    occupancy = sold_seats / max(total_seats, 1)
    demand = min(1.0, 0.6 * occupancy + 0.1 * waitlist_len)   # 0..1
    time_factor = min(1.0, max(hours_left, 0) / 24)            # 0..1
    return round(demand * (0.4 + 0.6 * time_factor), 3)


@dataclass
class RefundQuote:
    refund: float
    penalty: float
    penalty_rate: float
    resale_probability: float


def cancellation_refund(fare_paid: float, hours_left: float, total_seats: int,
                        sold_seats: int, waitlist_len: int) -> RefundQuote:
    """
    penalty_rate = max(time-tier penalty, resale-risk penalty)

    * Time tier      : the closer to departure, the higher the flat penalty.
    * Resale risk    : if the seat is unlikely to resell (empty waitlist, low
                       demand) we retain more, up to MAX_DYNAMIC_PENALTY.
    Result: railway keeps at least the expected loss from an unsold seat.
    """
    p_resale = resale_probability(total_seats, sold_seats, waitlist_len, hours_left)
    risk_penalty = (1 - p_resale) * MAX_DYNAMIC_PENALTY
    rate = min(1.0, max(_tier_penalty(hours_left), risk_penalty))
    penalty = round(fare_paid * rate, 2)
    return RefundQuote(round(fare_paid - penalty, 2), penalty, round(rate, 3), p_resale)


# ---- 3. Flash resale ---------------------------------------------------------
def flash_resale_price(base_fare: float, current_price: float, hours_left: float) -> float:
    """
    Discount that deepens as departure nears, floored at 60% of base fare so a
    flash sale can never sell a seat below a sensible cost floor.
    Outside the flash window the normal dynamic price applies.
    """
    if hours_left > FLASH_WINDOW_HOURS:
        return current_price
    discount = 0.35 * (1 - max(hours_left, 0) / FLASH_WINDOW_HOURS)   # 0..35%
    floor = base_fare * FLASH_FLOOR_RATIO
    return round(max(current_price * (1 - discount), floor), 2)


# ---- 4. No-show driven overbooking ------------------------------------------
def waitlist_limit(total_seats: int, no_show_rate: float, safety: float = 0.5) -> int:
    """
    Max waitlist size = expected no-shows * safety factor.
    e.g. 72 seats x 8% no-show x 0.5 -> 3 (rounded up). Keeps the risk of
    denied boarding low while converting no-shows into revenue.
    """
    return math.ceil(total_seats * no_show_rate * safety)


if __name__ == "__main__":     # quick demo for reviewers: python profit_optimizer.py
    for sold in (20, 40, 55, 65, 70, 72):
        m = dynamic_multiplier(72, sold, hours_left=10)
        print(f"sold={sold:>2}/72  multiplier={m}")
    q = cancellation_refund(fare_paid=600, hours_left=10, total_seats=72,
                            sold_seats=70, waitlist_len=3)
    print("refund quote:", q)
    print("flash price:", flash_resale_price(500, 600, hours_left=2))
