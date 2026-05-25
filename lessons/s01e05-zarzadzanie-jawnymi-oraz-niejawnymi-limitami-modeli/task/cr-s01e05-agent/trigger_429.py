import os
import time
import httpx
from dotenv import load_dotenv

# Load env variables
load_dotenv()

api_url = os.getenv("AIDEVS_VERIFY")
api_key = os.getenv("AIDEVS_API_KEY")

print(f"URL: {api_url}")
print(f"API Key: {api_key}")

payload = {
    "apikey": api_key,
    "task": "railway",
    "answer": {
        "action": "help"
    }
}

headers = {"Content-Type": "application/json"}

print("Starting rapid request sequence to escalate rate-limit penalty...")
for i in range(1, 101):
    try:
        response = httpx.post(api_url, headers=headers, json=payload, timeout=10.0)
        print(f"Request #{i:03d} | Status: {response.status_code}")
        
        # Print relevant rate limit headers if present
        rl_headers = {k: v for k, v in response.headers.items() if "ratelimit" in k.lower() or "retry" in k.lower()}
        if rl_headers:
            print(f"  Headers: {rl_headers}")
            
        try:
            body = response.json()
            print(f"  Body: {body}")
        except Exception:
            print(f"  Body: {response.text}")
            
        # If we see any secret flag or the wait time reaches 240 seconds, let's highlight it!
        # Standard format is {FLG:...} or some text.
        body_str = response.text
        if "FLG:" in body_str or "COUNTRYROADS" in body_str:
            print("!!! FLAG DETECTED IN BODY !!!")
            
        # We don't sleep to keep violating the rate limit!
    except Exception as e:
        print(f"Request #{i:03d} | Error: {e}")
        
    # Micro sleep to prevent local socket exhaustion, but small enough to trigger penalty
    time.sleep(0.1)
