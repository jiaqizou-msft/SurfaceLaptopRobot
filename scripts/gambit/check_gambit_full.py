"""Check all available Gambit routes and plugins on the DUT."""
import httpx
import json
from collections import Counter

BASE = "http://192.168.0.4:22133"

# Get swagger spec for full details
r = httpx.get(f"{BASE}/swagger/v1/swagger.json", timeout=10)
spec = r.json()
paths = spec.get("paths", {})

print(f"Total endpoints: {len(paths)}")

# Group by category/tag
categories = {}
for path, methods in paths.items():
    for method, details in methods.items():
        tags = details.get("tags", ["Other"])
        tag = tags[0] if tags else "Other"
        if tag not in categories:
            categories[tag] = []
        summary = details.get("summary", "")
        categories[tag].append(f"{method.upper():6s} {path}  {summary}")

print(f"Categories: {len(categories)}")
print()
for tag in sorted(categories.keys()):
    endpoints = categories[tag]
    print(f"=== {tag} ({len(endpoints)} endpoints) ===")
    for ep in endpoints:
        print(f"  {ep}")
    print()

# Check routes endpoint for plugin info
try:
    r2 = httpx.get(f"{BASE}/Routes", timeout=10)
    routes = r2.json()
    print(f"\n/Routes returned {len(routes)} items")
except:
    pass

# Check version info
try:
    r3 = httpx.get(f"{BASE}/version/drivers", timeout=10)
    print(f"\nDriver versions: {r3.text[:500]}")
except:
    pass

try:
    r4 = httpx.get(f"{BASE}/version/firmware", timeout=10)
    print(f"\nFirmware: {r4.text[:500]}")
except:
    pass
