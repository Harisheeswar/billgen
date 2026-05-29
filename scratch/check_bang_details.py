import os
from pathlib import Path

base_dir = Path("c:/Users/User/Downloads/billgen")
path = base_dir / "debug_484_bangalore.txt"
if path.exists():
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            if any(w in line.lower() for w in ["item", "qty", "total"]):
                print(line.strip())
