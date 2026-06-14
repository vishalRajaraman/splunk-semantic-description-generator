import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import yaml, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open("config/config.yaml") as f:
    cfg = yaml.safe_load(f)

# Support both groq and legacy gemini config blocks
ai_cfg = cfg.get("groq", cfg.get("gemini", {}))
keys = ai_cfg.get("api_keys", ai_cfg.get("api_key", []))
if isinstance(keys, str):
    keys = [keys]

model = ai_cfg.get("model", "llama-3.3-70b-versatile")
api_base = ai_cfg.get("api_base", "https://api.groq.com/openai/v1")
url = f"{api_base.rstrip('/')}/chat/completions"

print(f"Testing {len(keys)} Groq key(s) against {model}...")
print(f"Endpoint: {url}\n")

payload = {
    "model": model,
    "messages": [{"role": "user", "content": "Reply with just: OK"}],
    "max_tokens": 10,
    "temperature": 0,
}

ok_count = 0
for i, key in enumerate(keys):
    key_short = key[:20] + "..."
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            txt = r.json()["choices"][0]["message"]["content"].strip()
            print(f"  key{i+1:02d} [{key_short}] ✓  WORKING  response: {txt}")
            ok_count += 1
        elif r.status_code == 429:
            print(f"  key{i+1:02d} [{key_short}] 429  KEY VALID but rate-limited")
        elif r.status_code == 401:
            print(f"  key{i+1:02d} [{key_short}] 401  INVALID KEY — check key value")
        else:
            err = r.json().get("error", {}).get("message", "?")[:100]
            print(f"  key{i+1:02d} [{key_short}] {r.status_code}  {err}")
    except Exception as e:
        print(f"  key{i+1:02d} [{key_short}] ERROR: {e}")

print(f"\n{ok_count}/{len(keys)} keys are currently working.")
if ok_count == 0:
    print("  → Get a free Groq key at: https://console.groq.com/keys")
