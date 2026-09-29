"""main.py - run with:  uvicorn main:app --reload   (docs at /docs)"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from beanie import init_beanie
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from dsa.route_finder import DEMO_GRAPH, base_fare_for_distance, shortest_path
from models import Ticket, Train, User
from routers import bookings


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    await init_beanie(client.smart_railway, document_models=[User, Train, Ticket])
    if not await Train.find_one():                     # seed one demo train
        found = shortest_path(DEMO_GRAPH, "Agra Cantt", "Lucknow")
        km, route = found
        await Train(number="12001", name="Smart Express", route=route,
                    source=route[0], destination=route[-1],
                    departure_time=datetime.now(timezone.utc) + timedelta(hours=5),
                    distance_km=km, total_seats=72,
                    base_fare=base_fare_for_distance(km)).insert()
    yield


app = FastAPI(title="Smart Railway API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(bookings.router)


@app.get("/route")
def route(src: str, dst: str):
    found = shortest_path(DEMO_GRAPH, src, dst)
    if not found:
        raise HTTPException(404, "No route")
    km, path = found
    return {"distance_km": km, "path": path, "base_fare": base_fare_for_distance(km)}


@app.get("/trains")
async def list_trains():
    return await Train.find_all().to_list()
