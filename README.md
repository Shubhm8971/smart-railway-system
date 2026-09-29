# Smart Railway

Dynamic yield pricing and automated flash-resale queues to recover revenue lost to late cancellations and no-shows.

## Project structure

```
smart-railway/
├── PITCH_DECK.md
├── backend/
│   ├── main.py                    # app, DB init, demo seed, /route, /trains
│   ├── models.py                  # Beanie models: User, Train, Ticket
│   ├── requirements.txt
│   ├── dsa/
│   │   ├── profit_optimizer.py    # surge, penalty, flash price, waitlist cap
│   │   └── route_finder.py        # Dijkstra (heapq)
│   └── routers/
│       └── bookings.py            # reserve, cancel, check-in, no-show sweep
└── frontend/
    └── src/
        ├── components/
        │   ├── SeatSelection.jsx  # live badge + price + seat map
        │   ├── PriceTag.jsx       # (extract price block when it grows)
        │   └── WaitlistPanel.jsx  # (planned)
        ├── pages/                 # Dashboard.jsx, MyTickets.jsx, AdminRevenue.jsx
        ├── api/client.js          # fetch wrapper
        └── App.jsx
```

## Run it

```bash
# 1. MongoDB running locally (mongod)

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload           # Swagger UI: http://localhost:8000/docs

# 3. Frontend (Vite + Tailwind)
npm create vite@latest frontend -- --template react
cd frontend && npm i && npm i -D tailwindcss @tailwindcss/vite
# add the Tailwind plugin per the Tailwind docs, then use <SeatSelection trainId="..." userId="..." />
```

## 3-minute demo script (Swagger `/docs`)

1. `POST /users` is not included; insert a user in Mongo or reuse any valid 24-char ObjectId as `user_id`.
2. `GET /trains` and copy the train `_id`.
3. `POST /bookings/reserve` several times and watch `GET /bookings/availability/{id}` raise the multiplier.
4. Fill the train, then reserve once more to see a WAITLISTED ticket.
5. `POST /bookings/{pnr}/cancel` on a confirmed ticket: the response shows the penalty and `promoted_pnrs`.
6. `POST /bookings/no-show-sweep/{id}?force=true` to show no-shows turning into revenue and waitlist promotions.

## Known limits (say these before faculty do)

- Seat allocation is not transactional in the demo; production needs MongoDB transactions or per-train locking.
- No authentication yet; `user_id` is passed in the request body.
- `resale_probability()` is a heuristic, designed to be swapped for a trained model.
- Route distances in `DEMO_EDGES` are approximate.
