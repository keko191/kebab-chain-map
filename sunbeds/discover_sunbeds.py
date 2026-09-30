"""Discover sunbed/tanning businesses across London and the surrounding South East.

Uses Google Places API (New) text search across a grid and deduplicates by Place ID.
The broad search intentionally keeps "tanning-only" matches so mixed beauty/tanning
businesses are not missed; the map visually separates stronger sunbed matches.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

API_KEY = os.environ["GOOGLE_API_KEY"]
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "sunbeds/stores_sunbeds.json")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.rating,"
    "places.userRatingCount,"
    "places.websiteUri,"
    "places.googleMapsUri,"
    "places.businessStatus,"
    "places.types,"
    "nextPageToken"
)

# London + Surrey + Berkshire + nearby Kent/Essex/Hampshire fringe.
# Override these via repository/environment variables if the search area changes.
LAT_MIN = float(os.environ.get("LAT_MIN", "50.95"))
LAT_MAX = float(os.environ.get("LAT_MAX", "51.75"))
LNG_MIN = float(os.environ.get("LNG_MIN", "-1.20"))
LNG_MAX = float(os.environ.get("LNG_MAX", "0.55"))

GRID_SPACING_DEG_LAT = float(os.environ.get("GRID_SPACING_DEG_LAT", "0.075"))
GRID_SPACING_DEG_LNG = float(os.environ.get("GRID_SPACING_DEG_LNG", "0.12"))
SEARCH_RADIUS_M = int(os.environ.get("SEARCH_RADIUS_M", "6500"))

QUERIES = [
    "sunbed",
    "sunbeds",
    "tanning salon",
]


def frange(start: float, stop: float, step: float) -> list[float]:
    vals = []
    v = start
    while v <= stop + 1e-9:
        vals.append(round(v, 6))
        v += step
    return vals


def search_point(query: str, lat: float, lng: float) -> list[dict]:
    results = []
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "textQuery": query,
        "regionCode": "GB",
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": SEARCH_RADIUS_M,
            }
        },
    }

    page_token = None
    page_count = 0
    while True:
        if page_token:
            body["pageToken"] = page_token
        else:
            body.pop("pageToken", None)

        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            print(f"API error query={query!r} at {lat},{lng}: {resp.status_code} {resp.text[:300]}")
            break

        data = resp.json()
        results.extend(data.get("places", []))

        page_token = data.get("nextPageToken")
        page_count += 1
        if not page_token or page_count >= 3:
            break
        time.sleep(2)

    return results


def main() -> None:
    lat_points = frange(LAT_MIN, LAT_MAX, GRID_SPACING_DEG_LAT)
    lng_points = frange(LNG_MIN, LNG_MAX, GRID_SPACING_DEG_LNG)
    total = len(lat_points) * len(lng_points) * len(QUERIES)

    seen: dict[str, dict] = {}
    count = 0

    print(
        f"Scanning {LAT_MIN},{LNG_MIN} to {LAT_MAX},{LNG_MAX} "
        f"for {len(QUERIES)} tanning queries across {total} searches"
    )

    for lat in lat_points:
        for lng in lng_points:
            for query in QUERIES:
                count += 1
                print(f"[{count}/{total}] {query!r} @ {lat},{lng}")

                for place in search_point(query, lat, lng):
                    pid = place.get("id")
                    loc = place.get("location", {})
                    if not pid or loc.get("latitude") is None or loc.get("longitude") is None:
                        continue

                    # Ignore businesses Google explicitly marks permanently closed.
                    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                        continue

                    if pid not in seen:
                        seen[pid] = {
                            "place_id": pid,
                            "name": place.get("displayName", {}).get("text", ""),
                            "address": place.get("formattedAddress", ""),
                            "lat": loc.get("latitude"),
                            "lng": loc.get("longitude"),
                            "rating": place.get("rating"),
                            "user_rating_count": place.get("userRatingCount"),
                            "website_uri": place.get("websiteUri"),
                            "google_maps_uri": place.get("googleMapsUri"),
                            "business_status": place.get("businessStatus"),
                            "types": place.get("types", []),
                            "matched_queries": [],
                        }

                    if query not in seen[pid]["matched_queries"]:
                        seen[pid]["matched_queries"].append(query)

                time.sleep(0.12)

    stores = sorted(
        seen.values(),
        key=lambda s: ((s.get("name") or "").lower(), (s.get("address") or "").lower()),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "search_bounds": {
            "lat_min": LAT_MIN,
            "lat_max": LAT_MAX,
            "lng_min": LNG_MIN,
            "lng_max": LNG_MAX,
        },
        "queries": QUERIES,
        "stores": stores,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    strong = sum(
        1
        for s in stores
        if any(q in {"sunbed", "sunbeds"} for q in s.get("matched_queries", []))
    )
    print(f"Done: {len(stores)} total locations ({strong} strong sunbed matches) -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
