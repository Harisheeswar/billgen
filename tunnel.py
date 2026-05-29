from pyngrok import ngrok
import time

print("Starting tunnel to port 5557...")
try:
    public_url = ngrok.connect(5557)
    print("\n" + "="*50)
    print(f"✅ SUCCESS! Your public URL is:")
    print(f"   {public_url}")
    print("="*50 + "\n")
    print("Copy this URL into your Google Sheet.")
    print("Keep this window open to keep the tunnel alive...")
    
    # Keep the script running
    while True:
        time.sleep(1)
except Exception as e:
    print(f"Error starting tunnel: {e}")
