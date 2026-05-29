import os
import re
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
files = [f for f in os.listdir(base_dir) if f.startswith("debug_") and f.endswith(".txt")]

pattern = re.compile(r'Total\s*[iIl|1]tem[s]?(?:\s*[:-]+)?\s*(\d+)', re.I)

for f in files:
    path = base_dir / f
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        content = file.read()
        matches = pattern.findall(content)
        if matches:
            print(f"{f}: {matches}")
