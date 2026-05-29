import csv
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
csv_files = [f for f in base_dir.glob("*.csv") if "temp" in f.name or "output" in f.name]

min_rate = 999999.0
min_rate_row = None

for csv_path in csv_files:
    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                continue
            # Find Rate column index
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
                        if r_val > 0 and r_val < min_rate:
                            min_rate = r_val
                            min_rate_row = row
                    except ValueError:
                        pass
    except Exception as e:
        print(f"Error reading {csv_path.name}: {e}")

print(f"Minimum non-zero rate found: {min_rate}")
if min_rate_row:
    print(f"Row: {min_rate_row}")
