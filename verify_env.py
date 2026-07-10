"""Verify .env loads correctly and test IAM token."""
from pathlib import Path
from dotenv import load_dotenv
import os, requests

load_dotenv(Path(__file__).resolve().parent / ".env")

url = os.getenv("ORCHESTRATE_INSTANCE_URL", "")
key = os.getenv("ORCHESTRATE_API_KEY", "")
aid = os.getenv("ORCHESTRATE_AGENT_ID", "")

print("ORCHESTRATE_INSTANCE_URL :", (url[:55] + "...") if len(url) > 55 else url or "(empty)")
print("ORCHESTRATE_API_KEY      :", (key[:6] + "..." + key[-4:]) if len(key) > 10 else "(empty)")
print("ORCHESTRATE_AGENT_ID     :", (aid[:8] + "...") if aid else "(empty)")

all_set = all([url, key, aid])
print()
print("All three vars configured:", all_set)

if not all_set:
    missing = [n for n, v in [("ORCHESTRATE_INSTANCE_URL", url), ("ORCHESTRATE_API_KEY", key), ("ORCHESTRATE_AGENT_ID", aid)] if not v]
    print("Missing:", ", ".join(missing))
    raise SystemExit(1)

print("Testing IAM token...")
resp = requests.post(
    "https://iam.cloud.ibm.com/identity/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": key.strip()},
    timeout=15,
)
if resp.status_code == 200:
    token = resp.json()["access_token"]
    print("IAM token OK:", token[:20] + "...")
    print()
    print("SUCCESS - app.py will load .env correctly. Run:  python app.py")
else:
    body = resp.json()
    code = body.get("errorCode", "unknown")
    msg  = body.get("errorMessage", resp.text[:200])
    print(f"IAM FAILED {resp.status_code}: [{code}] {msg}")
    raise SystemExit(1)
