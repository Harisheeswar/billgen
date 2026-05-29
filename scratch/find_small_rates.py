import csv
import sys
import os
from pathlib import Path

# Add project root to path
base_dir = Path("c:/Users/User/Downloads/billgen")
sys.path.insert(0, str(base_dir))

from extractor import is_valid_product

# Set stdout to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

csv_files = [f for f in base_dir.glob("*.csv") if "temp" in f.name or "output" in f.name]

small_rates = []

for csv_path in csv_files:
    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                continue
            rate_idx = -1
            for idx, h in enumerate(headers):
                if "RATE" in h.upper():
                    rate_idx = idx
                    break
            if rate_idx == -1:
                continue
                
            for row in reader:
                if len(row) > rate_idx:
                    try:
                        r_val = float(row[rate_idx].replace("'", "").strip())
                        prod_name = row[5] if len(row) > 5 else ""
                        if 1.0 <= r_val <= 200.0 and is_valid_product(prod_name):
                            small_rates.append((r_val, row))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"Error reading {csv_path.name}: {e}")

print(f"Found {len(small_rates)} rates between 1.0 and 200.0 for valid products:")
seen = set()
for r, row in sorted(small_rates, key=lambda x: x[0]):
    key = (r, row[0], row[1], row[2], row[5])
    if key not in seen:
        seen.add(key)
        print(f"Rate: {r} | Product: {row[5]} | Row: {row}")
