import os
import time
from typing import Dict, Optional, Tuple
import httpx
from fastapi import FastAPI, Response
from pydantic import BaseModel

TRIP_SERVICE_URL = os.getenv("TRIP_SERVICE_URL", "http://localhost:8001")
CACHE_TTL_SECONDS = 60

app = FastAPI(title="TravelPlan - Gateway")

_cache: Dict[str, Tuple[float, int, bytes]] = {}

class TripPayload(BaseModel):
    city: str
    start_date: str
    end_date: str

class TripUpdatePayload(BaseModel):
    city: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

async def _forward(method: str, path: str, body: Optional[dict] = None, use_cache: bool = False) -> Response:
    key = f"{method}:{path}"

    if use_cache and key in _cache:
        ts, status_code, cached_body = _cache[key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            print(f"[CACHE HIT] {method} {path}")
            return Response(content=cached_body, status_code=status_code, media_type="application/json")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(method, f"{TRIP_SERVICE_URL}{path}", json=body)

    if use_cache and resp.status_code == 200:
        _cache[key] = (time.time(), resp.status_code, resp.content)
        print(f"[CACHE MISS] {method} {path} -> resposta armazenada em cache")

    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")

def _invalidate_cache(trip_id: int) -> None:
    _cache.pop(f"GET:/trips/{trip_id}", None)
    _cache.pop("GET:/trips", None)

@app.get("/health")
async def health():
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{TRIP_SERVICE_URL}/health")
    return resp.json()

@app.post("/trips")
async def create_trip(payload: TripPayload):
    return await _forward("POST", "/trips", body=payload.dict())

@app.get("/trips")
async def list_trips():
    return await _forward("GET", "/trips", use_cache=True)

@app.get("/trips/{trip_id}")
async def get_trip(trip_id: int):
    return await _forward("GET", f"/trips/{trip_id}", use_cache=True)

@app.put("/trips/{trip_id}")
async def update_trip(trip_id: int, payload: TripUpdatePayload):
    resp = await _forward("PUT", f"/trips/{trip_id}", body=payload.dict(exclude_unset=True))
    _invalidate_cache(trip_id)
    return resp

@app.delete("/trips/{trip_id}")
async def delete_trip(trip_id: int):
    resp = await _forward("DELETE", f"/trips/{trip_id}")
    _invalidate_cache(trip_id)
    return resp
