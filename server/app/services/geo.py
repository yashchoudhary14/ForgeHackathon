"""User-triggered Nominatim lookups, persistent cache and one request/second.

Usage policy: https://operations.osmfoundation.org/policies/nominatim/
The public service is for moderate traffic; no autocomplete or background scans.
"""
import asyncio
import math
import os
import time

import httpx

from . import llm_cache

_lock = asyncio.Lock()
_last_request = 0.0


def distance_m(lat: float, lng: float, other_lat: float, other_lng: float) -> float:
    a, b = math.radians(lat), math.radians(other_lat)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(other_lng - lng) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1.0, h)))


def bounds(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    dy = math.degrees(radius_m / 6371000)
    dx = min(180, dy / max(0.000001, math.cos(math.radians(lat))))
    return max(-90, lat - dy), min(90, lat + dy), lng - dx, lng + dx


async def reverse_geocode(lat: float, lng: float) -> str | None:
    global _last_request
    base = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
    # Five decimal places is about a metre; no personal profile address is sent.
    key = llm_cache.cache_key("civic_geocode", [base, round(lat, 5), round(lng, 5)])
    async with _lock:
        hit = await llm_cache.read(key, ttl_hours=24 * 30)
        if hit is not None:
            return hit.get("address")
        await asyncio.sleep(max(0, 1.05 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(base + "/reverse", params={
                "lat": round(lat, 5), "lon": round(lng, 5), "format": "jsonv2", "zoom": 18,
                "accept-language": "en"}, headers={"User-Agent": os.getenv(
                    "NOMINATIM_USER_AGENT", "Adhikaar-Civic/2.0 (citizen issue reporting; local development)")})
            response.raise_for_status()
        address = response.json().get("display_name")
        if address:
            await llm_cache.write(key, {"address": address})
        return address
