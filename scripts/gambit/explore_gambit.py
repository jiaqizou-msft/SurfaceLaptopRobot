"""Explore the Gambit API on the device under test."""
import httpx
import json

BASE = "http://192.168.0.4:22133"

try:
    r = httpx.get(f"{BASE}/swagger/v1/swagger.json", timeout=5)
    print(f"Status: {r.status_code}")
    data = r.json()

    info = data.get("info", {})
    print(f"API: {info.get('title', '?')} v{info.get('version', '?')}")

    paths = data.get("paths", {})
    print(f"Endpoints: {len(paths)}")
    print()

    for path in sorted(paths.keys()):
        for method in paths[path]:
            summary = paths[path][method].get("summary", "")
            tags = paths[path][method].get("tags", [])
            tag = tags[0] if tags else ""
            print(f"  {method.upper():6s} {path:50s} [{tag}] {summary}")

except Exception as e:
    print(f"Failed: {e}")
    # Try basic connectivity
    try:
        r = httpx.get(f"{BASE}/", timeout=5)
        print(f"Root response: {r.status_code}")
        print(r.text[:500])
    except Exception as e2:
        print(f"Root also failed: {e2}")
