import urllib.request
import json

try:
    url = "http://127.0.0.1:5557/health"
    response = urllib.request.urlopen(url, timeout=2)
    data = json.loads(response.read().decode())
    print("Success connecting to 127.0.0.1:5557/health:")
    print(data)
except Exception as e:
    print(f"Error connecting to 127.0.0.1:5557/health: {e}")

try:
    url = "http://localhost:5557/health"
    response = urllib.request.urlopen(url, timeout=2)
    data = json.loads(response.read().decode())
    print("\nSuccess connecting to localhost:5557/health:")
    print(data)
except Exception as e:
    print(f"Error connecting to localhost:5557/health: {e}")
