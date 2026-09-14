"""Discover Greater London GDK or BABABOOM locations with Google Places API (New)."""
import json
import os
import time
import requests

API_KEY = os.environ["GOOGLE_API_KEY"]
BRAND_KEY = os.environ.get("BRAND_KEY", "gdk").lower()
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", f"stores_{BRAND_KEY}.json")

CONFIG = {
    "gdk": {
        "query": "German Doner Kebab",
        "accepted": ["german doner kebab", "gdk"],
    },
    "bababoom": {
        "query": "BABABOOM kebab",
        "accepted": ["bababoom"],
    },
}

if BRAND_KEY not in CONFIG:
    raise SystemExit(f"Unknown BRAND_KEY: {BRAND_KEY}")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location,nextPageToken"

LAT_MIN, LAT_MAX = 51.28, 51.70
LNG_MIN, LNG_MAX = -0.52, 0.34
GRID_SPACING_DEG_LAT = 0.045
GRID_SPACING_DEG_LNG = 0.072
SEARCH_RADIUS_M = 4000


def frange(start, stop, step):
    vals, v = [], start
    while v <= stop:
        vals.append(round(v, 6))
        v += step
    return vals


def norm(s):
    return " ".join((s or "").lower().replace("ö", "o").split())


def is_brand_name(name):
    n = norm(name)
    return any(norm(term) in n for term in CONFIG[BRAND_KEY]["accepted"])


def search_point(lat, lng):
    results = []
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "textQuery": CONFIG[BRAND_KEY]["query"],
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": SEARCH_RADIUS_M,
            }
        },
    }

    page_token = None
    while True:
        if page_token:
            body["pageToken"] = page_token
        elif "pageToken" in body:
            body.pop("pageToken")

        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=20)
        if resp.status_code != 200:
            print(f"API error at {lat},{lng}: {resp.status_code} {resp.text[:300]}")
            break

        data = resp.json()
        for place in data.get("places", []):
            name = place.get("displayName", {}).get("text", "")
            if is_brand_name(name):
                results.append(place)

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)

    return results


def main():
    lat_points = frange(LAT_MIN, LAT_MAX, GRID_SPACING_DEG_LAT)
    lng_points = frange(LNG_MIN, LNG_MAX, GRID_SPACING_DEG_LNG)
    total = len(lat_points) * len(lng_points)
    seen = {}
    count = 0

    print(f"Scanning Greater London for {BRAND_KEY} across {total} grid points")
    for lat in lat_points:
        for lng in lng_points:
            count += 1
            print(f"[{count}/{total}] {lat},{lng}")
            for place in search_point(lat, lng):
                pid = place.get("id")
                loc = place.get("location", {})
                if not pid or loc.get("latitude") is None or loc.get("longitude") is None:
                    continue
                seen[pid] = {
                    "place_id": pid,
                    "name": place.get("displayName", {}).get("text", ""),
                    "address": place.get("formattedAddress", ""),
                    "lat": loc.get("latitude"),
                    "lng": loc.get("longitude"),
                }
            time.sleep(0.15)

    stores = sorted(seen.values(), key=lambda s: (s.get("address") or "", s.get("name") or ""))
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(stores, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Done: {len(stores)} locations -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
