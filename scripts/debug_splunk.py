"""Count total objects in Security Essentials."""
import requests, urllib3
urllib3.disable_warnings()

HOST = "https://localhost:8089"
AUTH = ("vishal", "Vishal@123.")
APP = "Splunk_Security_Essentials"

endpoints = [
    "saved/searches",
    "admin/macros",
    "admin/transforms-extract",
    "saved/eventtypes",
    "data/ui/views",
    "data/transforms/lookups",
]

for ep in endpoints:
    url = f"{HOST}/servicesNS/-/{APP}/{ep}"
    r = requests.get(url, auth=AUTH,
                     params={"output_mode": "json", "count": 0, "offset": 0},
                     verify=False, timeout=20)
    if r.ok:
        data = r.json()
        total = data.get("paging", {}).get("total", len(data.get("entry", [])))
        fetched = len(data.get("entry", []))
        print(f"{ep:45s}  total={total}  fetched={fetched}")
    else:
        print(f"{ep:45s}  ERROR {r.status_code}")
