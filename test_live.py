"""Live end-to-end test: send a real message through the new SSE endpoint."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from app import send_to_orchestrate, ORCHESTRATE_ENVIRONMENT_ID

print(f"Environment: {ORCHESTRATE_ENVIRONMENT_ID}\n")

# Turn 1
print("=== Turn 1: Diabetes diet question ===")
r1 = send_to_orchestrate("What foods should I eat for Type 2 Diabetes?")
assert r1["type"] == "success", f"Turn 1 failed: {r1}"
print(f"Thread ID : {r1['thread_id']}")
print(f"Text ({len(r1['text'])} chars):\n{r1['text'][:500]}\n")

# Turn 2 — same thread, follow-up question
print("=== Turn 2: Follow-up on same thread ===")
r2 = send_to_orchestrate("Can you give me a daily meal plan for that?", thread_id=r1["thread_id"])
assert r2["type"] == "success", f"Turn 2 failed: {r2}"
print(f"Thread ID : {r2['thread_id']}  (same={r2['thread_id']==r1['thread_id']})")
print(f"Text ({len(r2['text'])} chars):\n{r2['text'][:500]}\n")

print("Live end-to-end test PASSED")
