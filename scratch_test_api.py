import requests
import base64
from pathlib import Path

pdf_path = Path(r"C:\Users\User\Downloads\billgen\invoices\TMA - Hyderabad\Hyderabad Invoice_Jan_25\INV.344 - Copy.pdf")
with open(pdf_path, 'rb') as f:
    pdf_b64 = base64.b64encode(f.read()).decode('utf-8')

url = "http://127.0.0.1:5557/extract-pdf"
payload = {
    "pdfBase64": pdf_b64,
    "fileName": "INV.344.pdf"
}

print(f"Sending {pdf_path.name} to API...")
resp = requests.post(url, json=payload)
print(f"Status: {resp.status_code}")
print(resp.json())
