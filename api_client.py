import requests, json, time
from .config import BACKEND_URL

def send_event(**payload):
    payload['ts'] = time.time()
    try:
        requests.post(f"{BACKEND_URL}/events", json=payload, timeout=1)
    except Exception as exc:
        print("⚠️ backend offline:", exc)
