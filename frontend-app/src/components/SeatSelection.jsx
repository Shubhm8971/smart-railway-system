// SeatSelection.jsx
// Live seat map + availability badge + dynamic price for one train run.
// Polls GET /bookings/availability/{trainId} every 8s. If the backend is not
// running it falls back to MOCK data, so the UI can be demoed on its own.
import { useCallback, useEffect, useMemo, useState } from "react";

const API = import.meta.env?.VITE_API_URL ?? "http://localhost:8000";
const POLL_MS = 8000;

const MOCK = {
  train: { number: "12001", name: "Smart Express", source: "Agra Cantt", destination: "Lucknow" },
  total_seats: 72, available_seats: 9,
  taken_seats: Array.from({ length: 72 }, (_, i) => i + 1).filter((n) => n % 8 !== 0),
  waitlist_count: 1, waitlist_limit: 3,
  base_fare: 450, multiplier: 1.32, price: 594, flash_open: false, hours_left: 5.2,
};

// One place decides what the badge says, so the UI and the pitch stay consistent.
function statusOf(a) {
  if (a.hours_left <= 0)
    return { label: "Departed", tone: "bg-slate-200 text-slate-600 ring-slate-300", cta: null };
  if (a.available_seats === 0)
    return a.waitlist_count < a.waitlist_limit
      ? { label: "Waitlist open", tone: "bg-amber-100 text-amber-900 ring-amber-300", cta: "Join waitlist" }
      : { label: "Sold out", tone: "bg-slate-200 text-slate-600 ring-slate-300", cta: null };
  if (a.flash_open)
    return { label: `Flash seats · ${a.available_seats} left`, tone: "bg-emerald-100 text-emerald-900 ring-emerald-300", cta: "Grab flash seat" };
  if (a.available_seats <= 10)
    return { label: `Filling fast · ${a.available_seats} left`, tone: "bg-red-100 text-red-800 ring-red-300", cta: "Book seat" };
  return { label: `${a.available_seats} seats available`, tone: "bg-sky-100 text-sky-900 ring-sky-300", cta: "Book seat" };
}

export default function SeatSelection({ trainId, token, onUnauthorized }) {
  const [data, setData] = useState(null);
  const [live, setLive] = useState(true);
  const [seat, setSeat] = useState(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState(null);
  const [connectionError, setConnectionError] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/bookings/availability/${trainId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        const result = await r.json().catch(() => ({}));
        if (r.status === 401) onUnauthorized?.();
        throw new Error(result.detail ?? `Availability request failed (${r.status})`);
      }
      setData(await r.json());
      setLive(true);
      setConnectionError("");
    } catch (error) {
      setData((d) => d ?? MOCK);          // demo fallback
      setLive(false);
      setConnectionError(error.message || "Could not reach the railway API");
    }
  }, [trainId, token, onUnauthorized]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const taken = useMemo(() => new Set(data?.taken_seats ?? []), [data]);
  if (!data) return <p className="p-6 text-slate-500">Loading live availability…</p>;

  const s = statusOf(data);
  const occupancy = Math.round(((data.total_seats - data.available_seats) / data.total_seats) * 100);
  const surged = data.multiplier > 1;

  async function book() {
    setMsg(null);
    try {
      const r = await fetch(`${API}/bookings/reserve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ train_id: trainId, passenger_name: name, preferred_seat: seat }),
      });
      const j = await r.json();
      if (r.status === 401) onUnauthorized?.();
      if (!r.ok) throw new Error(j.detail ?? "Booking failed");
      setMsg({ ok: true, text: `${j.status}: PNR ${j.pnr}${j.seat_number ? `, seat ${j.seat_number}` : ""}` });
      setSeat(null);
      load();
    } catch (e) {
      setMsg({ ok: false, text: live ? e.message : "Backend offline (demo data): booking disabled" });
    }
  }

  return (
    <section className="mx-auto max-w-3xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">
            {data.train.number} {data.train.name}
          </h2>
          <p className="text-slate-600">{data.train.source} to {data.train.destination}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ring-1 ${s.tone}`} role="status">
          {s.label}
        </span>
      </header>

      {/* Price block: shows WHY the price is what it is */}
      <div className="mt-5 flex items-end gap-4">
        <p className="text-4xl font-bold tabular-nums text-slate-900">₹{data.price}</p>
        {surged && (
          <p className="pb-1 text-sm text-slate-500">
            <span className="line-through">₹{data.base_fare}</span>{" "}
            <span className="font-medium text-red-700">{data.multiplier.toFixed(2)}× demand</span>
          </p>
        )}
        {data.flash_open && <p className="pb-1 text-sm font-medium text-emerald-700">Last-minute flash price</p>}
      </div>

      {/* Occupancy bar */}
      <div className="mt-4" aria-label={`Train ${occupancy}% full`}>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200">
          <div className="h-full bg-slate-800 transition-all duration-700" style={{ width: `${occupancy}%` }} />
        </div>
        <p className="mt-1 text-xs text-slate-500">
          {occupancy}% full · {data.waitlist_count}/{data.waitlist_limit} on waitlist · departs in {data.hours_left}h
        </p>
      </div>

      {/* Seat grid: 4 per row with an aisle after seat 2 */}
      <div className="mt-6 grid grid-cols-[repeat(5,2.5rem)] justify-center gap-2" role="group" aria-label="Seat map">
        {Array.from({ length: data.total_seats }, (_, i) => i + 1).flatMap((n) => {
          const isTaken = taken.has(n);
          const btn = (
            <button
              key={n}
              disabled={isTaken}
              onClick={() => setSeat(n === seat ? null : n)}
              aria-pressed={seat === n}
              aria-label={`Seat ${n} ${isTaken ? "taken" : "free"}`}
              className={`h-10 w-10 rounded-md text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600
                ${isTaken ? "cursor-not-allowed bg-slate-200 text-slate-400"
                  : seat === n ? "bg-sky-700 text-white"
                  : "bg-emerald-50 text-emerald-900 ring-1 ring-emerald-300 hover:bg-emerald-100"}`}
            >
              {n}
            </button>
          );
          return n % 4 === 2 ? [btn, <span key={`a${n}`} aria-hidden />] : [btn];
        })}
      </div>

      {/* Booking form */}
      {s.cta && (
        <div className="mt-6 flex flex-wrap gap-3">
          <input
            value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Passenger name"
            className="min-w-48 flex-1 rounded-md border border-slate-300 px-3 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600"
          />
          <button
            onClick={book} disabled={!name.trim() || !live}
            className="rounded-md bg-slate-900 px-5 py-2 font-medium text-white hover:bg-slate-700 disabled:opacity-40"
          >
            {s.cta}{seat ? ` (seat ${seat})` : ""}
          </button>
        </div>
      )}
      {msg && <p className={`mt-3 text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>{msg.text}</p>}
      {!live && <p className="mt-3 text-xs text-amber-700">Showing demo data. {connectionError}</p>}
    </section>
  );
}
