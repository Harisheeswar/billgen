import os
import re
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
files = [f for f in os.listdir(base_dir) if f.startswith("debug_") and f.endswith(".txt")]

for f in files:
    path = base_dir / f
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        content = file.read()
        matches = re.findall(r'Total\s*Item[s]?(?:\s*[:-]+)?\s*\d+', content, re.I)
        if matches:
            print(f"{f}: {matches}")
