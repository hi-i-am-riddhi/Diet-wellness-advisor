"""Quick smoke test for the Flask app."""
import json
import sys

try:
    from app import app, DISEASE_LIBRARY, AGENT_INSTRUCTIONS
    print(f"Flask app imported OK")
    print(f"Disease library: {len(DISEASE_LIBRARY)} conditions")
    print(f"Agent instructions: {len(AGENT_INSTRUCTIONS)} chars")

    physical = [d for d in DISEASE_LIBRARY if d["category"] == "physical"]
    mental   = [d for d in DISEASE_LIBRARY if d["category"] == "mental"]
    print(f"  Physical: {len(physical)}, Mental: {len(mental)}")

    with app.test_client() as c:
        pages = ['/', '/chat', '/dashboard', '/diseases', '/planner']
        for path in pages:
            resp = c.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
            print(f"  GET {path} -> 200 OK")

        resp = c.get('/disease/diabetes')
        assert resp.status_code == 200
        print(f"  GET /disease/diabetes -> 200 OK")

        resp = c.get('/disease/nonexistent')
        assert resp.status_code == 404
        print(f"  GET /disease/nonexistent -> 404 (expected)")

        resp = c.get('/api/diseases')
        data = json.loads(resp.data)
        assert len(data) == 35, f"Expected 35, got {len(data)}"
        print(f"  GET /api/diseases -> 200, {len(data)} items")

        resp = c.get('/api/diseases?q=diabetes')
        data = json.loads(resp.data)
        print(f"  GET /api/diseases?q=diabetes -> {len(data)} result(s)")

        resp = c.get('/api/health')
        data = json.loads(resp.data)
        print(f"  GET /api/health -> status={data['status']}, configured={data['orchestrate_configured']}")

    print("\nAll checks passed!")
    sys.exit(0)

except Exception as e:
    print(f"\nFAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
