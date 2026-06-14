import requests
import urllib3
urllib3.disable_warnings()

resp = requests.get(
    'https://localhost:8089/services/apps/local',
    auth=('vishal', 'Vishal@123.'),
    params={'output_mode': 'json', 'count': 0},
    verify=False,
    timeout=10
)

if resp.status_code == 200:
    apps = resp.json()['entry']
    print(f"Found {len(apps)} installed apps:\n")
    print(f"{'FOLDER NAME (use this for --app)':45s}  DISPLAY LABEL")
    print("-" * 80)
    for e in sorted(apps, key=lambda x: x['name']):
        label = e['content'].get('label', '')
        print(f"{e['name']:45s}  {label}")
else:
    print(f"Error {resp.status_code}: {resp.text[:500]}")
