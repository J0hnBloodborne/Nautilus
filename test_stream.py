import requests, time, json

start = time.time()
r = requests.get("http://127.0.0.1:8000/stream/movie/238", timeout=60)
elapsed = time.time() - start
d = r.json()
print(f"Time: {elapsed:.1f}s")
print(f"Status: {r.status_code}")
print(json.dumps(d, indent=2)[:500])
